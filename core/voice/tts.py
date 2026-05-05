import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG

_VOICE_MAP = {
    "en": "bf_emma",
    "hi": "hf_alpha",
    "bn": "bn",
    "as": "as",
    "ja": "jf_alpha",
}


class VoiceTTS:
    def __init__(self):
        self._kokoro = None
        self._pyttsx3 = None
        self._kokoro_ok = False
        self._model_dir = Path(CONFIG.get("voice", {}).get("kokoro_model_dir", "./models/kokoro"))
        self._speed = CONFIG.get("voice", {}).get("kokoro_speed", 0.85)
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
        self._init_engines()

    def _init_engines(self):
        self._init_kokoro()
        if not self._kokoro_ok:
            self._init_pyttsx3()

    def _init_kokoro(self):
        try:
            from kokoro_onnx import Kokoro
            model_file = self._model_dir / "kokoro-v1.0.onnx"
            voices_file = self._model_dir / "voices-v1.0.bin"
            if not model_file.exists() or not voices_file.exists():
                logger.warning(f"[VECTOR][tts] Kokoro model files not found at {self._model_dir} — using pyttsx3 fallback")
                return
            self._kokoro = Kokoro(str(model_file), str(voices_file))
            self._kokoro_ok = True
            logger.info("[VECTOR][tts] Kokoro TTS ready")
        except Exception as e:
            logger.warning(f"[VECTOR][tts] Kokoro init failed: {e}")

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._pyttsx3 = pyttsx3.init()
            logger.info("[VECTOR][tts] pyttsx3 fallback ready")
        except Exception as e:
            logger.error(f"[VECTOR][tts] pyttsx3 init failed: {e}")

    def speak(self, text: str, lang: str = "en") -> None:
        if not text:
            return
        if self._kokoro_ok:
            self._speak_kokoro(text, lang)
        else:
            self._speak_pyttsx3(text)

    def _speak_kokoro(self, text: str, lang: str) -> None:
        try:
            import sounddevice as sd
            import numpy as np
            voice = _VOICE_MAP.get(lang, _VOICE_MAP["en"])
            samples, sample_rate = self._kokoro.create(text, voice=voice, speed=self._speed)
            logger.info(f"[VECTOR][tts] Kokoro speaking '{text[:40]}...' voice={voice}")
            sd.play(samples.astype(np.float32), samplerate=sample_rate)
            sd.wait()
        except Exception as e:
            logger.warning(f"[VECTOR][tts] Kokoro speak failed: {e} — falling back to pyttsx3")
            self._speak_pyttsx3(text)

    def _speak_pyttsx3(self, text: str) -> None:
        try:
            if self._pyttsx3 is None:
                self._init_pyttsx3()
            if self._pyttsx3 is None:
                logger.error("[VECTOR][tts] No TTS engine available")
                return
            logger.info(f"[VECTOR][tts] pyttsx3 speaking '{text[:40]}'")
            self._pyttsx3.say(text)
            self._pyttsx3.runAndWait()
        except Exception as e:
            logger.error(f"[VECTOR][tts] pyttsx3 speak failed: {e}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    tts = VoiceTTS()
    tts.speak("Hello, I am VECTOR. Voice pipeline is online.", lang="en")
    print("✅ tts OK")
