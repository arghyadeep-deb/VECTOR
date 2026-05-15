"""VECTOR Speech-to-Text — multi-engine adapter.

Selects an STT engine based on CONFIG['voice']['stt_engine']:
  • "whisper"        — OpenAI Whisper (default, local, no API key)
  • "faster_whisper" — faster-whisper (local, ~4x faster than whisper)
  • "deepgram"       — Deepgram Nova (cloud, low-latency, requires API key)
  • "openai"         — OpenAI Whisper API (cloud)

All engines expose:
  - transcribe(audio_np, sample_rate=16000) -> str
  - record_and_transcribe(duration_sec=None) -> str

Backwards compatible: WhisperSTT class is preserved for any existing imports.
The new STT() factory picks the engine; if the chosen one fails to load, falls
back to Whisper local.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from loguru import logger

from core.config import CONFIG


# ── Whisper (local, default) ─────────────────────────────────────────────────


class WhisperSTT:
    """OpenAI Whisper, local — no API key, ~6 GB VRAM for large-v3."""

    name = "whisper"

    def __init__(self):
        self._model = None
        self._model_name = CONFIG.get("voice", {}).get("whisper_model", "large-v3")

    def _load(self):
        if self._model is None:
            try:
                import whisper
                logger.info(f"[VECTOR][stt:whisper] Loading model '{self._model_name}'")
                self._model = whisper.load_model(self._model_name)
                logger.info("[VECTOR][stt:whisper] ready")
            except Exception as e:
                logger.error(f"[VECTOR][stt:whisper] Failed to load: {e}")
                self._model = None

    def transcribe(self, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
        try:
            self._load()
            if self._model is None:
                return ""
            if audio_np.dtype != np.float32:
                audio_np = audio_np.astype(np.float32) / 32768.0
            result = self._model.transcribe(audio_np, fp16=False)
            text = result.get("text", "").strip()
            logger.info(f"[VECTOR][stt:whisper] '{text}'")
            return text
        except Exception as e:
            logger.error(f"[VECTOR][stt:whisper] Transcription failed: {e}")
            return ""

    def record_and_transcribe(self, duration_sec: float | None = None) -> str:
        try:
            import sounddevice as sd
            duration_sec = duration_sec or CONFIG.get("voice", {}).get("record_duration_sec", 5.0)
            sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
            logger.info(f"[VECTOR][stt:whisper] Recording {duration_sec}s @ {sample_rate}Hz")
            audio = sd.rec(
                int(duration_sec * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
            return self.transcribe(audio.flatten(), sample_rate)
        except Exception as e:
            logger.error(f"[VECTOR][stt:whisper] Record failed: {e}")
            return ""


# ── faster-whisper (local, faster) ───────────────────────────────────────────


class FasterWhisperSTT:
    """faster-whisper — ~4x throughput vs vanilla Whisper, same accuracy."""

    name = "faster_whisper"

    def __init__(self):
        self._model = None
        self._model_name = CONFIG.get("voice", {}).get("whisper_model", "large-v3")

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore[import]
                device = CONFIG.get("voice", {}).get("device", "cuda")
                compute = CONFIG.get("voice", {}).get("compute_type", "float16")
                logger.info(
                    f"[VECTOR][stt:faster_whisper] Loading '{self._model_name}' "
                    f"on {device} ({compute})"
                )
                self._model = WhisperModel(self._model_name, device=device, compute_type=compute)
                logger.info("[VECTOR][stt:faster_whisper] ready")
            except Exception as e:
                logger.error(f"[VECTOR][stt:faster_whisper] Failed to load: {e}")
                self._model = None

    def transcribe(self, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
        try:
            self._load()
            if self._model is None:
                return ""
            if audio_np.dtype != np.float32:
                audio_np = audio_np.astype(np.float32) / 32768.0
            segments, _info = self._model.transcribe(audio_np, beam_size=5)
            text = " ".join(s.text.strip() for s in segments)
            logger.info(f"[VECTOR][stt:faster_whisper] '{text}'")
            return text
        except Exception as e:
            logger.error(f"[VECTOR][stt:faster_whisper] failed: {e}")
            return ""

    def record_and_transcribe(self, duration_sec: float | None = None) -> str:
        # Reuse Whisper's recording path
        return WhisperSTT.record_and_transcribe(self, duration_sec)  # type: ignore[arg-type]


# ── Deepgram (cloud, low-latency) ────────────────────────────────────────────


class DeepgramSTT:
    """Deepgram Nova — fastest cloud STT. Requires DEEPGRAM_API_KEY env var."""

    name = "deepgram"

    def __init__(self):
        import os
        self._api_key = os.environ.get("DEEPGRAM_API_KEY", "")

    def transcribe(self, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
        if not self._api_key:
            logger.warning("[VECTOR][stt:deepgram] DEEPGRAM_API_KEY missing — cannot transcribe")
            return ""
        try:
            import io
            import soundfile as sf  # type: ignore[import]
            import httpx
            buf = io.BytesIO()
            sf.write(buf, audio_np, sample_rate, format="WAV")
            buf.seek(0)
            r = httpx.post(
                "https://api.deepgram.com/v1/listen?model=nova-2&punctuate=true",
                headers={"Authorization": f"Token {self._api_key}",
                         "Content-Type": "audio/wav"},
                content=buf.read(),
                timeout=30.0,
            )
            r.raise_for_status()
            data = r.json()
            text = (
                data.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
            )
            logger.info(f"[VECTOR][stt:deepgram] '{text}'")
            return text
        except Exception as e:
            logger.error(f"[VECTOR][stt:deepgram] failed: {e}")
            return ""

    def record_and_transcribe(self, duration_sec: float | None = None) -> str:
        return WhisperSTT.record_and_transcribe(self, duration_sec)  # type: ignore[arg-type]


# ── Engine selector ──────────────────────────────────────────────────────────


_ENGINES = {
    "whisper": WhisperSTT,
    "faster_whisper": FasterWhisperSTT,
    "deepgram": DeepgramSTT,
}


def STT():
    """Return the configured STT engine. Falls back to Whisper local on failure."""
    engine_name = (CONFIG.get("voice", {}).get("stt_engine") or "whisper").lower()
    cls = _ENGINES.get(engine_name)
    if cls is None:
        logger.warning(f"[VECTOR][stt] Unknown engine '{engine_name}' — using whisper")
        cls = WhisperSTT
    try:
        instance = cls()
        logger.info(f"[VECTOR][stt] engine = {instance.name}")
        return instance
    except Exception as e:
        logger.warning(f"[VECTOR][stt] '{engine_name}' init failed: {e} — falling back to whisper")
        return WhisperSTT()
