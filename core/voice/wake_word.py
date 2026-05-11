import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from loguru import logger
from core.config import CONFIG

# NOTE: Uses hey_jarvis pre-trained model as placeholder until "Hey VECTOR"
# custom training is complete (openwakeword requires custom training for new phrases)


class WakeWordDetector:
    def __init__(self):
        self._model = None
        self._threshold = CONFIG.get("voice", {}).get("wake_threshold", 0.5)
        self._wake_phrase = CONFIG.get("voice", {}).get("wake_phrase", "hey_jarvis")
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
        self._frame_size = 512
        self._init_model()

    def _init_model(self):
        try:
            import openwakeword
            from openwakeword.model import Model
            openwakeword.utils.download_models()
            self._model = Model(wakeword_models=[self._wake_phrase], inference_framework="onnx")
            logger.info(f"[VECTOR][wake] openWakeWord ready (phrase='{self._wake_phrase}')")
        except Exception as e:
            logger.warning(f"[VECTOR][wake] openWakeWord init failed: {e}")
            self._model = None

    def is_wake_word(self, audio_frame: np.ndarray) -> bool:
        try:
            if self._model is None:
                return False
            if audio_frame.dtype != np.int16:
                audio_frame = (audio_frame * 32767).astype(np.int16)
            prediction = self._model.predict(audio_frame)
            score = prediction.get(self._wake_phrase, 0.0)
            return float(score) > self._threshold
        except Exception as e:
            logger.error(f"[VECTOR][wake] is_wake_word error: {e}")
            return False

    async def listen_for_wake(self) -> bool:
        try:
            import sounddevice as sd
            logger.info("[VECTOR][wake] Listening for wake word...")
            with sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._frame_size,
            ) as stream:
                while True:
                    frame, _ = await asyncio.to_thread(stream.read, self._frame_size)
                    frame_np = frame.flatten()
                    if self.is_wake_word(frame_np):
                        logger.info("[VECTOR][wake] Wake word detected!")
                        return True
                    await asyncio.sleep(0)  # yield to event loop each frame
        except Exception as e:
            logger.error(f"[VECTOR][wake] listen_for_wake error: {e}")
            return False


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    detector = WakeWordDetector()
    # Smoke test: feed a silent frame — should return False (not a wake word)
    silent_frame = np.zeros(512, dtype=np.int16)
    result = detector.is_wake_word(silent_frame)
    model_ok = detector._model is not None
    print(f"✅ wake_word OK (model_loaded={model_ok}, silent_frame_is_wake={result})" if model_ok else "❌ FAILED (model not loaded)")
