import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from loguru import logger
from core.config import CONFIG

_KWS_PHRASES = ["vector", "hey vector", "okay vector", "hey vecto"]  # Whisper KWS phrases


class WakeWordDetector:
    def __init__(self):
        self._model = None
        self._threshold = CONFIG.get("voice", {}).get("wake_threshold", 0.5)
        self._wake_phrase = CONFIG.get("voice", {}).get("wake_phrase", "hey_vector")
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
        self._frame_size = 512
        self._use_whisper_kws = False  # fallback when openwakeword unavailable
        self._active_model_name = ""
        self._init_model()

    def _init_model(self):
        # Stage 1: try openwakeword with the configured phrase
        try:
            import openwakeword
            from openwakeword.model import Model
            openwakeword.utils.download_models()
            try:
                self._model = Model(wakeword_models=[self._wake_phrase], inference_framework="onnx")
                self._active_model_name = self._wake_phrase
                logger.info(f"[VECTOR][wake] openWakeWord ready (phrase='{self._wake_phrase}')")
                return
            except Exception:
                pass  # custom model not available — fall through to built-in

            # Stage 2: try built-in "alexa" as placeholder
            self._model = Model(wakeword_models=[_BUILTIN_FALLBACK], inference_framework="onnx")
            self._active_model_name = _BUILTIN_FALLBACK
            logger.info(
                f"[VECTOR][wake] Custom wake word '{self._wake_phrase}' not found. "
                f"Using built-in '{_BUILTIN_FALLBACK}' as placeholder. "
                f"Train a custom model: https://github.com/dscripka/openWakeWord#training"
            )
        except Exception as e:
            logger.warning(f"[VECTOR][wake] openWakeWord unavailable: {e} — using Whisper KWS fallback")
            self._model = None
            self._use_whisper_kws = True

    def is_wake_word(self, audio_frame: np.ndarray) -> bool:
        """Per-frame check — only used in the openwakeword path."""
        if self._use_whisper_kws or self._model is None:
            return False
        try:
            if audio_frame.dtype != np.int16:
                audio_frame = (audio_frame * 32767).astype(np.int16)
            prediction = self._model.predict(audio_frame)
            score = prediction.get(self._active_model_name, 0.0)
            return float(score) > self._threshold
        except Exception as e:
            logger.error(f"[VECTOR][wake] is_wake_word error: {e}")
            return False

    async def listen_for_wake(self) -> bool:
        """Block until wake word/phrase detected. Returns True when triggered."""
        if self._use_whisper_kws:
            return await self._listen_whisper_kws()
        return await self._listen_openwakeword()

    async def _listen_openwakeword(self) -> bool:
        """Frame-by-frame openwakeword detection."""
        try:
            import sounddevice as sd
            logger.info(f"[VECTOR][wake] Listening ({self._active_model_name})...")
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._frame_size,
            ) as stream:
                while True:
                    frame, _ = await asyncio.to_thread(stream.read, self._frame_size)
                    if self.is_wake_word(frame.flatten()):
                        logger.info("[VECTOR][wake] Wake word detected!")
                        return True
                    await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"[VECTOR][wake] _listen_openwakeword error: {e}")
            return False

    async def _listen_whisper_kws(self) -> bool:
        """Whisper-based keyword spotting: record 2s chunks, transcribe, look for wake phrase."""
        try:
            import sounddevice as sd
            from core.voice.stt import WhisperSTT
            stt = WhisperSTT()
            chunk_sec = 2.0
            logger.info(f"[VECTOR][wake] Whisper KWS listening for {_KWS_PHRASES}...")
            while True:
                audio = await asyncio.to_thread(
                    sd.rec,
                    int(chunk_sec * self._sample_rate),
                    samplerate=self._sample_rate,
                    channels=1,
                    dtype="float32",
                )
                await asyncio.to_thread(sd.wait)
                audio_flat = audio.flatten()
                # Only transcribe if there's actual audio (not silence)
                rms = float(np.sqrt(np.mean(audio_flat ** 2)))
                if rms < 0.004:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    text = stt.transcribe(audio_flat, self._sample_rate)
                    if text and any(p in text.lower() for p in _KWS_PHRASES):
                        logger.info(f"[VECTOR][wake] KWS triggered: '{text}'")
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"[VECTOR][wake] _listen_whisper_kws error: {e}")
            return False


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    detector = WakeWordDetector()
    silent_frame = np.zeros(512, dtype=np.int16)
    result = detector.is_wake_word(silent_frame)
    model_ok = detector._model is not None or detector._use_whisper_kws
    method = "whisper_kws" if detector._use_whisper_kws else f"openwakeword({detector._active_model_name})"
    print(f"✅ wake_word OK (method={method})" if model_ok else "❌ FAILED — no detection method available")
