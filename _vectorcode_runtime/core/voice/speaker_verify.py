"""SpeakerVerifier — "is this actually the owner talking?" (voice identity).

Closes the biggest voice-identity gap: before this module, anyone near the
microphone was treated as the owner. Now every finalized utterance in the
realtime duplex pipeline is embedded and compared against the enrolled owner
voiceprint; YELLOW/RED-style *action* commands are refused for unknown voices
(chat stays polite but neutral).

Engine selection (best available, never crashes):
  1. resemblyzer VoiceEncoder  — d-vector embeddings, the real deal.
     pip install resemblyzer    (CPU is fine; GPU faster)
  2. numpy spectral fallback   — coarse log-mel band statistics. WEAK: catches
     "different person, different room" but not a careful impersonator. Logged
     loudly so the owner knows verification is running degraded.

Enrollment:  python scripts/enroll_owner_voice.py   (records ~30s, saves
data/voice_profiles/owner_voiceprint.npz). Verification auto-enables when the
voiceprint file exists; delete the file to disable.

Config (CONFIG["voice"]):
  speaker_verify_enabled:    default True (no-op until enrolled)
  speaker_verify_threshold:  default 0.75 (resemblyzer) / 0.85 (fallback)
"""

from __future__ import annotations

__all__ = ["SpeakerVerifier", "get_verifier", "start_speaker_verify_prewarm"]

import asyncio
import json
from concurrent.futures import Future
from pathlib import Path
from time import perf_counter

import numpy as np
from loguru import logger

from core.config import CONFIG

_PROFILE_DIR = Path("data/voice_profiles")
_VOICEPRINT = _PROFILE_DIR / "owner_voiceprint.npz"


def _fallback_embed(audio: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Numpy-only voice embedding: per-band log-spectral mean+std over frames.

    Crude (64-dim) — only used when resemblyzer isn't installed. Good enough
    to separate clearly different speakers; NOT impersonation-resistant.
    """
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    frame, hop, bands = 512, 256, 32
    if len(audio) < frame:
        audio = np.pad(audio, (0, frame - len(audio)))
    n = 1 + (len(audio) - frame) // hop
    window = np.hanning(frame)
    spec = np.empty((n, bands), dtype=np.float64)
    edges = np.linspace(0, frame // 2, bands + 1, dtype=int)
    for i in range(n):
        seg = audio[i * hop:i * hop + frame] * window
        mag = np.abs(np.fft.rfft(seg)) + 1e-9
        spec[i] = [np.log(mag[edges[b]:edges[b + 1]].mean()) for b in range(bands)]
    emb = np.concatenate([spec.mean(axis=0), spec.std(axis=0)])
    norm = np.linalg.norm(emb)
    return (emb / norm) if norm else emb


class SpeakerVerifier:
    """Embeds utterances and compares against the enrolled owner voiceprint."""

    def __init__(self):
        voice_cfg = CONFIG.get("voice", {})
        self._enabled_cfg = bool(voice_cfg.get("speaker_verify_enabled", True))
        self._encoder = None          # resemblyzer VoiceEncoder (lazy)
        self._engine = "unloaded"     # "resemblyzer" | "fallback"
        self._owner_emb: np.ndarray | None = None
        self._threshold_cfg = voice_cfg.get("speaker_verify_threshold", None)
        self._load_voiceprint()

    # ── engine ────────────────────────────────────────────────────────────────

    def _get_engine(self):
        global _SPEAKER_VERIFY_FUTURE
        if _SPEAKER_VERIFY_FUTURE is not None:
            try:
                return _SPEAKER_VERIFY_FUTURE.result()
            except Exception:
                _SPEAKER_VERIFY_FUTURE = None
                logger.warning("[VECTOR][speaker] encoder prewarm failed; retrying on first use")
        if self._engine != "unloaded":
            return self._engine
        return _construct_speaker_verify_engine_sync()

    def _construct_engine(self):
        try:
            import torch
            from resemblyzer import VoiceEncoder
            # Explicit CPU, not resemblyzer's own cuda-if-available default.
            # Real startup measured the default encoder's first dummy
            # inference taking 16.4s -- almost the entire observed voice
            # cold-start latency -- concurrent with Kokoro's own CUDA init
            # (both competing for the same GPU/CUDA context at once).
            #
            # Moving to CPU alone was not enough: PyTorch defaults to using
            # every available core (24 on this machine) for a single
            # inference call via torch.get_num_threads(). Under genuine
            # concurrent load from the autonomous loop's own startup work,
            # that oversubscription made the SAME dummy inference take 19.3s
            # on CPU -- worse than the original GPU number. This tiny model
            # doesn't benefit from intra-op parallelism; explicitly capping
            # it to 1 thread measured 2.1s for the identical call under the
            # same live, loaded server.
            torch.set_num_threads(1)
            self._encoder = VoiceEncoder(device="cpu", verbose=False)
            self._engine = "resemblyzer"
            logger.info("[VECTOR][speaker] resemblyzer encoder ready")
        except Exception as e:
            self._engine = "fallback"
            logger.warning(
                "[VECTOR][speaker] resemblyzer unavailable ({}) — using WEAK "
                "numpy fallback. pip install resemblyzer for real verification.", e)
        return self._engine

    @property
    def threshold(self) -> float:
        if self._threshold_cfg is not None:
            return float(self._threshold_cfg)
        return 0.75 if self._engine == "resemblyzer" else 0.85

    def embed(self, audio: np.ndarray, sr: int = 16000) -> np.ndarray:
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32) / (32768.0 if audio.dtype == np.int16 else 1.0)
        if self._get_engine() == "resemblyzer":
            from resemblyzer import preprocess_wav
            return self._encoder.embed_utterance(preprocess_wav(audio, source_sr=sr))
        return _fallback_embed(audio, sr)

    # ── enrollment ────────────────────────────────────────────────────────────

    def enroll(self, clips: list[np.ndarray], sr: int = 16000) -> dict:
        """Average embeddings over several owner clips; persist voiceprint."""
        embs = [self.embed(c, sr) for c in clips if c is not None and len(c) >= sr]
        if not embs:
            return {"status": "error", "reason": "need >=1s clips"}
        emb = np.mean(np.stack(embs), axis=0)
        norm = np.linalg.norm(emb)
        if norm:
            emb = emb / norm
        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        np.savez(_VOICEPRINT, embedding=emb,
                 meta=json.dumps({"engine": self._engine, "clips": len(embs), "sr": sr}))
        self._owner_emb = emb
        logger.info("[VECTOR][speaker] owner voiceprint enrolled ({} clips, engine={})",
                    len(embs), self._engine)
        return {"status": "ok", "clips": len(embs), "engine": self._engine,
                "path": str(_VOICEPRINT)}

    def _load_voiceprint(self) -> None:
        try:
            if _VOICEPRINT.exists():
                data = np.load(_VOICEPRINT, allow_pickle=False)
                self._owner_emb = data["embedding"]
                logger.info("[VECTOR][speaker] owner voiceprint loaded")
        except Exception as e:
            logger.warning("[VECTOR][speaker] voiceprint load failed: {}", e)
            self._owner_emb = None

    @property
    def enrolled(self) -> bool:
        return self._owner_emb is not None

    @property
    def active(self) -> bool:
        """Verification only gates anything when enabled AND enrolled."""
        return self._enabled_cfg and self.enrolled

    # ── verification ──────────────────────────────────────────────────────────

    def verify(self, audio: np.ndarray, sr: int = 16000) -> tuple[bool, float]:
        """Return (is_owner, similarity).

        Verification is a no-op until it is enabled and enrolled.  Once active,
        however, an internal verification failure must not authenticate the
        speaker.  Callers use this boolean to gate owner-only actions.
        """
        if not self.active:
            return True, 1.0
        # Too little speech to judge ⇒ fail OPEN. A d-vector from <1s of audio is
        # noise: silence/short clips scored 0.40-0.56 against the owner (vs an
        # impostor's 0.44), i.e. indistinguishable — and refusing the real owner
        # is far worse than not gating a one-word utterance (2026-07-17).
        min_s = float(CONFIG.get("voice", {}).get("speaker_verify_min_seconds", 1.0))
        if audio is None or getattr(audio, "size", 0) < int(min_s * sr):
            secs = (getattr(audio, "size", 0) / sr) if audio is not None else 0.0
            logger.debug("[VECTOR][speaker] {:.2f}s < {:.2f}s minimum — not judged (fail open)",
                         secs, min_s)
            return True, 1.0
        try:
            emb = self.embed(audio, sr)
            owner = self._owner_emb
            if emb.shape != owner.shape:
                # Engine changed since enrollment (e.g. resemblyzer installed
                # later).  The stale voiceprint cannot establish identity.
                logger.warning("[VECTOR][speaker] voiceprint engine mismatch — "
                               "re-run scripts/enroll_owner_voice.py")
                return False, 0.0
            sim = float(np.dot(emb, owner) /
                        ((np.linalg.norm(emb) * np.linalg.norm(owner)) or 1.0))
            return sim >= self.threshold, sim
        except Exception as e:
            logger.warning("[VECTOR][speaker] verify failed ({}) — failing closed", e)
            return False, 0.0


_VERIFIER: SpeakerVerifier | None = None
_SPEAKER_VERIFY_FUTURE: Future | None = None
_SPEAKER_VERIFY_TASK: asyncio.Task | None = None


def _construct_speaker_verify_engine_sync():
    verifier = get_verifier()
    engine = verifier._construct_engine()
    if engine == "resemblyzer":
        started = perf_counter()
        try:
            from resemblyzer import preprocess_wav
            # Quiet noise survives preprocess_wav's silence trimming and reaches
            # the same encoder forward pass used for real utterances.
            dummy_audio = (np.random.default_rng(0).standard_normal(16000) * 0.001).astype(np.float32)
            verifier._encoder.embed_utterance(preprocess_wav(dummy_audio, source_sr=16000))
            logger.info("[VECTOR][speaker] encoder inference pre-warm took {:.3f}s",
                        perf_counter() - started)
        except Exception as exc:
            logger.warning("[VECTOR][speaker] encoder inference pre-warm failed after {:.3f}s: {}",
                           perf_counter() - started, exc)
    return engine


async def _construct_speaker_verify_engine():
    return await asyncio.to_thread(_construct_speaker_verify_engine_sync)


def start_speaker_verify_prewarm() -> asyncio.Task:
    """Reserve the singleton encoder, then construct it off the event loop."""
    global _SPEAKER_VERIFY_FUTURE, _SPEAKER_VERIFY_TASK
    get_verifier()
    future = _SPEAKER_VERIFY_FUTURE
    if future is None:
        future = Future()
        _SPEAKER_VERIFY_FUTURE = future
        _SPEAKER_VERIFY_TASK = None
    if _SPEAKER_VERIFY_TASK is not None:
        return _SPEAKER_VERIFY_TASK

    async def _run():
        if future.done():
            return
        try:
            engine = await _construct_speaker_verify_engine()
            future.set_result(engine)
            logger.info("[VECTOR][speaker] encoder prewarm ready")
        except Exception as exc:
            logger.warning("[VECTOR][speaker] encoder prewarm failed: {}", exc)
            future.set_exception(exc)

    _SPEAKER_VERIFY_TASK = asyncio.create_task(_run())
    return _SPEAKER_VERIFY_TASK


def get_verifier() -> SpeakerVerifier:
    global _VERIFIER
    if _VERIFIER is None:
        _VERIFIER = SpeakerVerifier()
    return _VERIFIER


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    rng = np.random.default_rng(7)
    sr = 16000
    # two synthetic "voices": band-limited noise with different spectral tilt
    t = np.arange(sr * 2) / sr
    voice_a = (np.sin(2 * np.pi * 140 * t) + 0.3 * rng.standard_normal(sr * 2)).astype(np.float32)
    voice_b = (np.sin(2 * np.pi * 290 * t) + 0.3 * rng.standard_normal(sr * 2)).astype(np.float32)
    ea, eb = _fallback_embed(voice_a, sr), _fallback_embed(voice_b, sr)
    ea2 = _fallback_embed(voice_a + 0.05 * rng.standard_normal(sr * 2).astype(np.float32), sr)
    same = float(np.dot(ea, ea2))
    diff = float(np.dot(ea, eb))
    assert same > diff, f"fallback embed failed: same={same:.3f} diff={diff:.3f}"
    print(f"OK speaker_verify.py (fallback embed: same={same:.3f} > diff={diff:.3f})")
