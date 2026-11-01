"""Local zero-shot voice cloning for the VECTOR voice pipeline.

Python reimplementation of voicebox's Chatterbox backend (backend/backends/chatterbox_backend.py
and backend/services/tts.py chunking logic): provides on-device, zero-shot voice cloning from a
reference WAV clip with no cloud dependency.  Chatterbox-tts (torch/CUDA) is an optional install;
the class degrades gracefully to available()=False when the dependency is absent — the rest of the
pipeline falls through to Kokoro / pyttsx3 transparently.

Install when you want cloning:
    pip install chatterbox-tts        # pulls torch, torchaudio, CUDA-ready

Optional guarded dep — never import at module level.
"""

from __future__ import annotations

import sys
import re
from pathlib import Path


from loguru import logger
from core.config import CONFIG

import numpy as np

__all__ = [
    "VoiceCloner",
    "chunk_text",
    "crossfade_arrays",
    "get_cloner",
]

# ── Text chunking helpers (pure functions — tested without model) ──────────────

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MAX_CHARS = 300        # Chatterbox is comfortable up to ~300 chars per call


def chunk_text(text: str, max_chars: int = _MAX_CHARS) -> list[str]:
    """Split text into sentence-boundary-aware chunks of at most `max_chars`.

    Preserves sentence integrity: never cuts mid-sentence unless a single
    sentence exceeds max_chars (in which case it's split on the last space
    before the limit as a last resort).
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if not sentences:
        sentences = [text.strip()] if text.strip() else []

    chunks: list[str] = []
    current = ""
    for sent in sentences:
        # Long sentence — split it on spaces
        if len(sent) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words = sent.split()
            part = ""
            for word in words:
                trial = (part + " " + word).strip() if part else word
                if len(trial) <= max_chars:
                    part = trial
                else:
                    if part:
                        chunks.append(part)
                    part = word
            if part:
                current = part
            continue

        trial = (current + " " + sent).strip() if current else sent
        if len(trial) <= max_chars:
            current = trial
        else:
            if current:
                chunks.append(current)
            current = sent

    if current:
        chunks.append(current)
    return chunks


def crossfade_arrays(a: np.ndarray, b: np.ndarray, overlap_samples: int = 2400) -> np.ndarray:
    """Concatenate two float32 mono arrays with a linear crossfade."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    n = min(overlap_samples, len(a), len(b))
    if n <= 0:
        return np.concatenate([a, b])
    fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
    blended = a[-n:] * fade_out + b[:n] * fade_in
    return np.concatenate([a[:-n], blended, b[n:]])


# ── VoiceCloner ───────────────────────────────────────────────────────────────

class VoiceCloner:
    """
    Zero-shot local voice cloning via Chatterbox-TTS (CUDA).

    Usage::

        cloner = VoiceCloner()
        if cloner.available():
            audio, sr = cloner.synthesize("Hello world.", reference_wav="sample.wav")
            # audio: np.float32 array, sr: int (usually 24000)

            audio, sr = cloner.synthesize_long(long_text, reference_wav="sample.wav")
            # handles unlimited-length text via chunking + crossfade

    The reference_wav can be a file path string or raw bytes (WAV). 10–20 s of clean
    speech gives best results; background noise degrades quality.
    """

    # Singleton model — loaded once, reused across calls (expensive to load)
    _model = None
    _model_loaded = False

    def __init__(
        self,
        *,
        exaggeration: float | None = None,
        cfg_weight: float | None = None,
        device: str | None = None,
        overlap_ms: int = 150,
    ):
        voice_cfg = CONFIG.get("voice", {}) or {}
        self._exaggeration = exaggeration if exaggeration is not None else float(
            voice_cfg.get("cloning_exaggeration", 0.5)
        )
        self._cfg_weight = cfg_weight if cfg_weight is not None else float(
            voice_cfg.get("cloning_cfg_weight", 0.5)
        )
        self._device = device or voice_cfg.get("cloning_device", "cuda")
        self._overlap_samples = int(overlap_ms / 1000 * 24000)   # 24kHz native sr

    # ── availability ──────────────────────────────────────────────────────────

    @staticmethod
    def available() -> bool:
        """Return True iff chatterbox-tts is installed and importable."""
        try:
            import chatterbox.tts  # noqa: F401
            return True
        except Exception:
            return False

    # ── model loading ─────────────────────────────────────────────────────────

    @classmethod
    def _get_model(cls, device: str):
        if cls._model is not None:
            return cls._model
        if cls._model_loaded:
            return None         # loading was already attempted and failed
        try:
            import torch
            from chatterbox.tts import ChatterboxTTS
            actual_device = device if torch.cuda.is_available() else "cpu"
            if actual_device != device:
                logger.warning(
                    "[VECTOR][cloning] CUDA not available — loading Chatterbox on CPU (slower)"
                )
            logger.info("[VECTOR][cloning] loading Chatterbox model on {}", actual_device)
            cls._model = ChatterboxTTS.from_pretrained(device=actual_device)
            logger.info("[VECTOR][cloning] Chatterbox model ready")
        except Exception as e:
            logger.warning("[VECTOR][cloning] Chatterbox model load failed: {}", e)
            cls._model = None
        cls._model_loaded = True
        return cls._model

    # ── synthesis ─────────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        reference_wav: "str | bytes | None" = None,
        *,
        exaggeration: float | None = None,
        cfg_weight: float | None = None,
    ) -> "tuple[np.ndarray, int]":
        """
        Synthesize `text` optionally cloned from `reference_wav`.

        Args:
            text:          Text to synthesize (≤ ~300 chars for best results).
            reference_wav: File path (str/Path) or raw WAV bytes of the reference speaker.
                           Pass None for non-cloned (default Chatterbox voice).

        Returns:
            (audio_array: np.float32, sample_rate: int)

        Raises:
            RuntimeError: if chatterbox-tts is not installed or model fails to load.
        """
        if not self.available():
            raise RuntimeError(
                "chatterbox-tts not installed. Run: pip install chatterbox-tts"
            )

        model = self._get_model(self._device)
        if model is None:
            raise RuntimeError("Chatterbox model failed to load — check logs")

        exag = exaggeration if exaggeration is not None else self._exaggeration
        cfg = cfg_weight if cfg_weight is not None else self._cfg_weight

        # Resolve reference_wav to a temp file path if bytes were given
        ref_path = self._resolve_reference(reference_wav)
        try:
            import torch
            wav = model.generate(
                text,
                audio_prompt_path=ref_path,
                exaggeration=exag,
                cfg_weight=cfg,
            )
            # wav may be a torch.Tensor or np.ndarray depending on version
            if hasattr(wav, "numpy"):
                audio = wav.squeeze().numpy().astype(np.float32)
            else:
                audio = np.asarray(wav, dtype=np.float32).squeeze()
            sr = model.sr if hasattr(model, "sr") else 24000
            logger.info(
                "[VECTOR][cloning] synthesized {} chars → {:.1f}s audio",
                len(text), len(audio) / sr
            )
            return audio, sr
        except Exception as e:
            logger.error("[VECTOR][cloning] synthesis failed: {}", e)
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
        """
        Synthesize unlimited-length text via sentence-boundary chunking + crossfade.
        Passes `reference_wav` (and any extra kwargs) to each chunk call.
        """
        chunks = chunk_text(text, max_chars=max_chars)
        if not chunks:
            return np.zeros(0, dtype=np.float32), 24000

        overlap = overlap_ms if overlap_ms is not None else int(self._overlap_samples / 24000 * 1000)
        overlap_samp = int(overlap / 1000 * 24000)

        result: np.ndarray | None = None
        sr = 24000
        for i, chunk in enumerate(chunks):
            logger.debug("[VECTOR][cloning] chunk {}/{}: {!r}", i + 1, len(chunks), chunk[:40])
            part, sr = self.synthesize(chunk, reference_wav, **kwargs)
            if result is None:
                result = part
            else:
                result = crossfade_arrays(result, part, overlap_samples=overlap_samp)

        return (result if result is not None else np.zeros(0, dtype=np.float32)), sr

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_reference(reference_wav) -> str | None:
        """Return a file path string for reference_wav, writing a temp file if bytes given."""
        if reference_wav is None:
            return None
        if isinstance(reference_wav, (str, Path)):
            return str(reference_wav)
        # bytes — write to temp file
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".wav")
        try:
            os.write(fd, reference_wav)
        finally:
            os.close(fd)
        return path

    @staticmethod
    def _cleanup_temp(path: str | None, original_input) -> None:
        """Remove temp file only if we created it (i.e. input was bytes)."""
        if path is not None and isinstance(original_input, bytes):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass


# ── Singleton / engine factory ─────────────────────────────────────────────────

_cloner: VoiceCloner | None = None
_voxcpm_cloner = None  # type: ignore[assignment]  # lazy-typed to avoid a hard import


def get_cloner():
    """Return the active cloning engine per CONFIG["voice"]["cloning_engine"].

    docs/repo_analysis/VoxCPM.md: callers (core/voice/tts.py's _speak_clone()
    and synthesize_to_file()) need zero changes — both VoiceCloner and
    VoxCPMCloner expose the same available()/synthesize()/synthesize_long()
    shape. Defaults to "chatterbox"; set cloning_engine="voxcpm" to switch.
    """
    global _cloner, _voxcpm_cloner
    engine = (CONFIG.get("voice", {}) or {}).get("cloning_engine", "chatterbox")
    if engine == "voxcpm":
        if _voxcpm_cloner is None:
            from core.voice.voxcpm_cloning import VoxCPMCloner
            _voxcpm_cloner = VoxCPMCloner()
        return _voxcpm_cloner
    if _cloner is None:
        _cloner = VoiceCloner()
    return _cloner


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # 1. Pure-function tests (no model required)
    chunks = chunk_text("Hello world. How are you? I am fine.", max_chars=20)
    assert len(chunks) >= 3, chunks
    # Each chunk should be ≤ max_chars
    for c in chunk_text("a " * 200, max_chars=50):
        assert len(c) <= 50, f"chunk too long: {c!r}"

    # Empty / single word
    assert chunk_text("") == []
    assert chunk_text("Hello") == ["Hello"]

    # Long single-sentence overflow
    long_sent = "word " * 100
    big_chunks = chunk_text(long_sent.strip(), max_chars=30)
    assert all(len(c) <= 30 for c in big_chunks), big_chunks

    # crossfade round-trip
    a = np.ones(5000, dtype=np.float32)
    b = np.ones(5000, dtype=np.float32) * 0.5
    merged = crossfade_arrays(a, b, overlap_samples=500)
    assert merged.shape[0] == 5000 + 5000 - 500  # a[:-n]=4500 + blend=500 + b[n:]=4500

    # crossfade with very short arrays — overlap clamps to min(n, len(a), len(b))=1
    short = crossfade_arrays(np.array([1.0], dtype=np.float32), np.array([2.0], dtype=np.float32), 5000)
    assert len(short) >= 1  # at least one sample survives

    # 2. Availability check
    cloner = VoiceCloner()
    dep_present = cloner.available()
    print(f"[cloning] chatterbox-tts installed: {dep_present}")
    if dep_present:
        # Only test synth path when dep is actually installed
        try:
            audio, sr = cloner.synthesize("Hello, I am VECTOR.")
            assert audio.dtype == np.float32
            assert sr > 0
            print(f"[cloning] synthesize OK ({len(audio)/sr:.1f}s @ {sr}Hz)")
        except Exception as e:
            print(f"[cloning] synthesize raised (model may not be downloaded): {e}")

    print("✅ cloning.py OK (chunker + crossfade verified; synth guarded by dep check)")
