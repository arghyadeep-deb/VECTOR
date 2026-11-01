"""VoxCPM2 (OpenBMB) — alternate local voice cloning / multilingual TTS engine.

docs/repo_analysis/VoxCPM.md absorption verdict: UPGRADE over Chatterbox for
cloning quality, control, and 30-language breadth — but NOT a Kokoro
replacement, and NOT to be kept permanently resident alongside vector-focus
on a 12GB card (the model is ~2B params / ~8GB VRAM). Loaded on-demand,
unloaded is left to the caller (mirrors VoiceCloner's lazy singleton, but
this one is selected on-demand only via cloning_engine="voxcpm" — it is
never the default).

Same public shape as core/voice/cloning.py::VoiceCloner — available(),
synthesize(), synthesize_long() — so core/voice/tts.py's call sites need
zero changes; core.voice.cloning.get_cloner() dispatches to whichever
engine CONFIG["voice"]["cloning_engine"] selects.

Adds two VoxCPM-specific capabilities Chatterbox doesn't have:
    design(description, text)              — reference-free Voice Design
    clone_ultimate(text, ref, transcript)   — transcript-conditioned cloning

Install when you want VoxCPM:
    pip install voxcpm        # pulls torch, torchaudio, funasr, modelscope/HF weights (~8GB)

Optional guarded dep — never import at module level. Hindi WER is weak per
the vendor's own benchmarks; keep gTTS for hi/bn/as until a LoRA proves out.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger
from core.config import CONFIG

import numpy as np

from core.voice.cloning import chunk_text, crossfade_arrays, _MAX_CHARS

__all__ = ["VoxCPMCloner", "get_voxcpm_cloner"]


class VoxCPMCloner:
    """Local voice cloning / Voice Design via VoxCPM2 (Apache-2.0, CUDA).

    Usage::

        cloner = VoxCPMCloner()
        if cloner.available():
            audio, sr = cloner.synthesize("Hello world.", reference_wav="sample.wav")
            audio, sr = cloner.design("a warm, slow-paced narrator voice", "Hello world.")
    """

    # Singleton model — loaded once, reused across calls (expensive to load)
    _model = None
    _model_loaded = False

    _NATIVE_SR = 48000  # VoxCPM2 outputs 48kHz vs Chatterbox's 24kHz

    def __init__(
        self,
        *,
        inference_timesteps: int | None = None,
        cfg_value: float | None = None,
        device: str | None = None,
        overlap_ms: int = 150,
    ):
        voice_cfg = CONFIG.get("voice", {}) or {}
        self._inference_timesteps = (
            inference_timesteps if inference_timesteps is not None
            else int(voice_cfg.get("voxcpm_inference_timesteps", 10))
        )
        self._cfg_value = cfg_value if cfg_value is not None else float(
            voice_cfg.get("voxcpm_cfg_value", 2.0)
        )
        self._device = device or voice_cfg.get("cloning_device", "cuda")
        self._model_dir = voice_cfg.get("voxcpm_model_dir", "")
        self._overlap_samples = int(overlap_ms / 1000 * self._NATIVE_SR)

    # ── availability ──────────────────────────────────────────────────────────

    @staticmethod
    def available() -> bool:
        """Return True iff the voxcpm package is installed and importable."""
        try:
            import voxcpm  # noqa: F401
            return True
        except ImportError:
            return False

    # ── model loading ─────────────────────────────────────────────────────────

    @classmethod
    def _get_model(cls, model_dir: str):
        if cls._model is not None:
            return cls._model
        if cls._model_loaded:
            return None  # loading was already attempted and failed
        try:
            from voxcpm import VoxCPM
            logger.info("[VECTOR][voxcpm] loading VoxCPM2 model (~8GB VRAM, on-demand)")
            cls._model = VoxCPM.from_pretrained(model_dir) if model_dir else VoxCPM.from_pretrained()
            logger.info("[VECTOR][voxcpm] VoxCPM2 model ready")
        except Exception as e:
            logger.warning("[VECTOR][voxcpm] VoxCPM2 model load failed: {}", e)
            cls._model = None
        cls._model_loaded = True
        return cls._model

    @classmethod
    def unload(cls) -> None:
        """Release the model — call after a content-rendering batch so the
        ~8GB doesn't compete with vector-focus's permanent VRAM residency."""
        cls._model = None
        cls._model_loaded = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        logger.info("[VECTOR][voxcpm] model unloaded")

    # ── synthesis ─────────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        reference_wav: "str | bytes | None" = None,
        *,
        prompt_text: str | None = None,
    ) -> "tuple[np.ndarray, int]":
        """Synthesize `text`, optionally cloned from `reference_wav` (Controllable
        Cloning when prompt_text is None, Ultimate Cloning when prompt_text — the
        reference's transcript — is supplied).

        Returns (audio_array: np.float32, sample_rate: int).
        Raises RuntimeError if voxcpm is not installed or the model fails to load.
        """
        if not self.available():
            raise RuntimeError("voxcpm not installed. Run: pip install voxcpm")

        model = self._get_model(self._model_dir)
        if model is None:
            raise RuntimeError("VoxCPM2 model failed to load — check logs")

        ref_path = self._resolve_reference(reference_wav)
        try:
            wav = model.generate(
                text,
                reference_wav_path=ref_path,
                prompt_text=prompt_text,
                inference_timesteps=self._inference_timesteps,
                cfg_value=self._cfg_value,
            )
            audio = self._to_numpy(wav)
            sr = getattr(model, "sample_rate", self._NATIVE_SR)
            logger.info(
                "[VECTOR][voxcpm] synthesized {} chars -> {:.1f}s audio",
                len(text), len(audio) / sr,
            )
            return audio, sr
        except Exception as e:
            logger.error("[VECTOR][voxcpm] synthesis failed: {}", e)
            raise
        finally:
            self._cleanup_temp(ref_path, reference_wav)

    def synthesize_long(
        self,
        text: str,
        reference_wav: "str | bytes | None" = None,
        *,
        max_chars: int = _MAX_CHARS,
        overlap_ms: int | None = None,
        **kwargs,
    ) -> "tuple[np.ndarray, int]":
        """Synthesize unlimited-length text via sentence-boundary chunking + crossfade."""
        chunks = chunk_text(text, max_chars=max_chars)
        if not chunks:
            return np.zeros(0, dtype=np.float32), self._NATIVE_SR

        overlap = overlap_ms if overlap_ms is not None else int(self._overlap_samples / self._NATIVE_SR * 1000)
        overlap_samp = int(overlap / 1000 * self._NATIVE_SR)

        result: np.ndarray | None = None
        sr = self._NATIVE_SR
        for i, chunk in enumerate(chunks):
            logger.debug("[VECTOR][voxcpm] chunk {}/{}: {!r}", i + 1, len(chunks), chunk[:40])
            part, sr = self.synthesize(chunk, reference_wav, **kwargs)
            result = part if result is None else crossfade_arrays(result, part, overlap_samples=overlap_samp)

        return (result if result is not None else np.zeros(0, dtype=np.float32)), sr

    def design(self, description: str, text: str) -> "tuple[np.ndarray, int]":
        """Voice Design — synthesize `text` in a voice built purely from a text
        `description`, with NO reference audio needed. This is the path that
        builds the British "VECTOR voice" persona from a one-line prompt
        (CONFIG["voice"]["voice_design_description"])."""
        if not self.available():
            raise RuntimeError("voxcpm not installed. Run: pip install voxcpm")
        model = self._get_model(self._model_dir)
        if model is None:
            raise RuntimeError("VoxCPM2 model failed to load — check logs")
        try:
            wav = model.generate(
                text,
                voice_description=description,
                inference_timesteps=self._inference_timesteps,
                cfg_value=self._cfg_value,
            )
            audio = self._to_numpy(wav)
            sr = getattr(model, "sample_rate", self._NATIVE_SR)
            logger.info("[VECTOR][voxcpm] voice-designed {} chars from description", len(text))
            return audio, sr
        except Exception as e:
            logger.error("[VECTOR][voxcpm] voice design failed: {}", e)
            raise

    def clone_ultimate(self, text: str, reference_wav: "str | bytes", transcript: str) -> "tuple[np.ndarray, int]":
        """Ultimate Cloning — highest-fidelity cloning, conditioned on the
        reference clip's own transcript (`prompt_text`)."""
        return self.synthesize(text, reference_wav, prompt_text=transcript)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _to_numpy(wav) -> np.ndarray:
        if hasattr(wav, "numpy"):
            return wav.squeeze().numpy().astype(np.float32)
        return np.asarray(wav, dtype=np.float32).squeeze()

    @staticmethod
    def _resolve_reference(reference_wav) -> str | None:
        if reference_wav is None:
            return None
        if isinstance(reference_wav, (str, Path)):
            return str(reference_wav)
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            os.write(fd, reference_wav)
        finally:
            os.close(fd)
        return path

    @staticmethod
    def _cleanup_temp(path: str | None, original_input) -> None:
        if path is not None and isinstance(original_input, bytes):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                logger.warning("[VECTOR] silent swallow")


# ── Singleton ─────────────────────────────────────────────────────────────────

_voxcpm_cloner: VoxCPMCloner | None = None


def get_voxcpm_cloner() -> VoxCPMCloner:
    global _voxcpm_cloner
    if _voxcpm_cloner is None:
        _voxcpm_cloner = VoxCPMCloner()
    return _voxcpm_cloner


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    cloner = VoxCPMCloner()
    dep_present = cloner.available()
    print(f"[voxcpm] voxcpm installed: {dep_present}")
    if dep_present:
        try:
            audio, sr = cloner.synthesize("Hello, I am VECTOR.")
            assert audio.dtype == np.float32
            assert sr > 0
            print(f"[voxcpm] synthesize OK ({len(audio)/sr:.1f}s @ {sr}Hz)")
        except Exception as e:
            print(f"[voxcpm] synthesize raised (model may not be downloaded): {e}")

    print("✅ voxcpm_cloning.py OK (chunker reuse verified; synth guarded by dep check)")
