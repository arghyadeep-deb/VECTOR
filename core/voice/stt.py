import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from loguru import logger
from core.config import CONFIG


class WhisperSTT:
    def __init__(self):
        self._model = None
        self._model_name = CONFIG.get("voice", {}).get("whisper_model", "base")

    def _load(self):
        if self._model is None:
            try:
                import whisper
                logger.info(f"[VECTOR][stt] Loading Whisper model '{self._model_name}'")
                self._model = whisper.load_model(self._model_name)
                logger.info("[VECTOR][stt] Whisper ready")
            except Exception as e:
                logger.error(f"[VECTOR][stt] Failed to load Whisper: {e}")
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
            logger.info(f"[VECTOR][stt] Transcribed: '{text}'")
            return text
        except Exception as e:
            logger.error(f"[VECTOR][stt] Transcription failed: {e}")
            return ""

    def record_and_transcribe(self, duration_sec: float = None) -> str:
        try:
            import sounddevice as sd
            duration_sec = duration_sec or CONFIG.get("voice", {}).get("record_duration_sec", 5.0)
            sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
            logger.info(f"[VECTOR][stt] Recording {duration_sec}s at {sample_rate}Hz")
            audio = sd.rec(
                int(duration_sec * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()
            audio_np = audio.flatten()
            return self.transcribe(audio_np, sample_rate)
        except Exception as e:
            logger.error(f"[VECTOR][stt] Record failed: {e}")
            return ""


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    stt = WhisperSTT()
    silent = np.zeros(16000, dtype=np.float32)
    result = stt.transcribe(silent)
    print("✅ stt OK" if isinstance(result, str) else "❌ FAILED")
