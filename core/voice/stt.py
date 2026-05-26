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

__all__ = [
    "DeepgramSTT",
    "FasterWhisperSTT",
    "STT",
    "WhisperSTT",
]

from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from loguru import logger

from core.config import CONFIG


# ── Whisper (local, default) ─────────────────────────────────────────────────


class WhisperSTT:
    """OpenAI Whisper, local — no API key.

    VRAM requirements: large-v3 ~10 GB fp32 (falls back to medium when insufficient).
    """

    name = "whisper"

    # VRAM floor (GB) required to load each model size at fp32.
    _VRAM_REQUIREMENTS: dict = {"large-v3": 10.0, "large": 10.0, "medium": 5.0, "small": 2.0}

    def __init__(self):
        self._model = None
        self._model_name = CONFIG.get("voice", {}).get("whisper_model", "large-v3")

    def _select_model(self) -> str:
        """Return model name, downgrading to 'medium' when GPU VRAM is insufficient."""
        name = self._model_name
        required_gb = self._VRAM_REQUIREMENTS.get(name, 0.0)
        if required_gb > 0.0:
            try:
                import torch
                if torch.cuda.is_available():
                    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
                    if vram_gb < required_gb:
                        logger.warning(
                            "[VECTOR][stt:whisper] '{}' needs ~{:.0f} GB VRAM; "
                            "{:.1f} GB available — falling back to 'medium'",
                            name, required_gb, vram_gb,
                        )
                        return "medium"
            except Exception:
                pass
        return name

    def _load(self):
        if self._model is None:
            try:
                import whisper
                effective = self._select_model()
                logger.info(f"[VECTOR][stt:whisper] Loading model '{effective}'")
                self._model = whisper.load_model(effective)
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

    def record_until_silence(
        self,
        sample_rate: int | None = None,
        silence_rms: float = 0.01,
        post_silence_s: float = 0.6,
        max_s: float = 8.0,
    ) -> "np.ndarray":
        """VAD recording: stream 100ms chunks, stop 600ms after speech ends. Max 8s."""
        import queue as _q
        import numpy as np
        import sounddevice as sd
        sr = sample_rate or CONFIG.get("voice", {}).get("sample_rate", 16000)
        chunk = int(sr * 0.1)
        q: _q.Queue = _q.Queue()
        frames: list = []
        speech_started = False
        silence_frames = 0
        max_frames = int(max_s / 0.1)
        silence_threshold = int(post_silence_s / 0.1)

        def _cb(indata, *_):
            q.put(indata.copy())

        logger.info("[VECTOR][stt:whisper] VAD recording (max {}s)...", max_s)
        with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                            blocksize=chunk, callback=_cb):
            while len(frames) < max_frames:
                frame = q.get().flatten()
                frames.append(frame)
                rms = float(np.sqrt(np.mean(frame ** 2)))
                if rms > silence_rms:
                    speech_started = True
                    silence_frames = 0
                elif speech_started:
                    silence_frames += 1
                    if silence_frames >= silence_threshold:
                        break

        audio = np.concatenate(frames) if frames else np.zeros(chunk, dtype="float32")
        logger.info("[VECTOR][stt:whisper] VAD captured {}s", round(len(audio) / sr, 1))
        return audio

    def record_and_transcribe(self, duration_sec: float | None = None) -> str:
        """Record with VAD (dynamic end-of-speech), falling back to fixed duration."""
        try:
            import numpy as np
            sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
            audio = self.record_until_silence(sample_rate=sample_rate)
            return self.transcribe(audio, sample_rate)
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
        return WhisperSTT.record_and_transcribe(self, duration_sec)  # type: ignore[arg-type]

    async def transcribe_stream(self, audio_stream, callback: callable) -> str:
        try:
            self._load()
            if self._model is None:
                return ""
            all_chunks = []
            async for chunk in audio_stream:
                all_chunks.append(chunk)
                if chunk.dtype != np.float32:
                    chunk = chunk.astype(np.float32) / 32768.0
                segments, _info = self._model.transcribe(chunk, beam_size=5)
                partial = " ".join(s.text.strip() for s in segments)
                if partial:
                    callback(partial)
            if not all_chunks:
                return ""
            full_audio = np.concatenate(all_chunks)
            if full_audio.dtype != np.float32:
                full_audio = full_audio.astype(np.float32) / 32768.0
            segments, _info = self._model.transcribe(full_audio, beam_size=5)
            final = " ".join(s.text.strip() for s in segments)
            logger.info(f"[VECTOR][stt:faster_whisper] stream final: '{final}'")
            return final
        except Exception as e:
            logger.error(f"[VECTOR][stt:faster_whisper] stream failed: {e}")
            return ""


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
