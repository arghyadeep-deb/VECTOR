import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG

# Kokoro-supported voices only. bn/as not supported by Kokoro — routed to pyttsx3 fallback.
_KOKORO_VOICE_MAP = {
    "en": "bf_emma",
    "hi": "hf_alpha",
    "ja": "jf_alpha",
}
_KOKORO_UNSUPPORTED = {"bn", "as"}  # gTTS fallback for regional languages


# LRU cache for gTTS audio: maps (text, lang) → raw MP3 bytes
_GTTS_CACHE: dict[tuple[str, str], bytes] = {}
_GTTS_CACHE_MAX = 50


class VoiceTTS:
    def __init__(self):
        self._kokoro = None
        self._pyttsx3 = None
        self._kokoro_ok = False
        self._speaking = False  # barge-in flag
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
            voices_file = self._model_dir / "voices-v1.0.bin"
            # Prefer GPU fp16 model if onnxruntime-gpu is present, fall back to CPU model
            gpu_model = self._model_dir / "kokoro-v1.0.fp16-gpu.onnx"
            cpu_model = self._model_dir / "kokoro-v1.0.onnx"
            if gpu_model.exists() and voices_file.exists():
                try:
                    import onnxruntime as ort
                    if "CUDAExecutionProvider" in ort.get_available_providers():
                        model_file = gpu_model
                        logger.info("[VECTOR][tts] Using GPU fp16 Kokoro model")
                    else:
                        model_file = cpu_model
                except Exception:
                    model_file = cpu_model
            else:
                model_file = cpu_model
            if not model_file.exists() or not voices_file.exists():
                logger.warning(f"[VECTOR][tts] Kokoro model files not found at {self._model_dir} — using pyttsx3 fallback")
                return
            self._kokoro = Kokoro(str(model_file), str(voices_file))
            self._kokoro_ok = True
            logger.info(f"[VECTOR][tts] Kokoro TTS ready ({model_file.name})")
        except Exception as e:
            logger.warning(f"[VECTOR][tts] Kokoro init failed: {e}")

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._pyttsx3 = pyttsx3.init()
            logger.info("[VECTOR][tts] pyttsx3 fallback ready")
        except Exception as e:
            logger.error(f"[VECTOR][tts] pyttsx3 init failed: {e}")

    def stop_speaking(self) -> None:
        """Interrupt TTS mid-playback (barge-in support)."""
        self._speaking = False
        try:
            import sounddevice as sd
            sd.stop()
            logger.debug("[VECTOR][tts] Playback interrupted (barge-in)")
        except Exception as e:
            logger.debug(f"[VECTOR][tts] stop_speaking: {e}")
        try:
            if self._pyttsx3 is not None:
                self._pyttsx3.stop()
        except Exception:
            pass

    def speak(self, text: str, lang: str = "en") -> None:
        if not text:
            return
        if self._kokoro_ok and lang not in _KOKORO_UNSUPPORTED:
            self._speak_kokoro(text, lang)
        else:
            if lang in _KOKORO_UNSUPPORTED:
                logger.info(f"[VECTOR][tts] {lang} not in Kokoro — using gTTS fallback")
                self._speak_gtts(text, lang)
            else:
                self._speak_pyttsx3(text)

    def _speak_kokoro(self, text: str, lang: str) -> None:
        try:
            import re
            import time
            import sounddevice as sd
            import numpy as np
            voice = _KOKORO_VOICE_MAP.get(lang, _KOKORO_VOICE_MAP["en"])
            # Split into sentences so playback starts on the first sentence
            # while subsequent sentences are still generating
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
            if not sentences:
                sentences = [text]
            self._speaking = True
            logger.info("[VECTOR][tts] Kokoro streaming {} sentence(s) voice={}", len(sentences), voice)
            for sentence in sentences:
                if not self._speaking:
                    break
                samples, sample_rate = self._kokoro.create(sentence, voice=voice, speed=self._speed)
                if not self._speaking:
                    break
                sd.play(samples.astype(np.float32), samplerate=sample_rate)
                while sd.get_stream().active:
                    if not self._speaking:
                        sd.stop()
                        logger.debug("[VECTOR][tts] Kokoro cut by barge-in")
                        return
                    time.sleep(0.05)
            self._speaking = False
        except Exception as e:
            self._speaking = False
            logger.warning(f"[VECTOR][tts] Kokoro speak failed: {e} — falling back to pyttsx3")
            self._speak_pyttsx3(text)

    def _speak_gtts(self, text: str, lang: str) -> None:
        try:
            import io
            import tempfile
            import os

            try:
                from playsound import playsound
            except ImportError:
                logger.warning("[VECTOR][tts] playsound not installed, skipping gTTS audio playback")
                return

            cache_key = (text, lang)
            if cache_key in _GTTS_CACHE:
                # Cache hit — no HTTP call needed
                mp3_bytes = _GTTS_CACHE[cache_key]
                logger.debug(f"[VECTOR][tts] gTTS cache hit for '{text[:30]}'")
            else:
                from gtts import gTTS
                logger.info(f"[VECTOR][tts] gTTS fetching '{text[:40]}' in {lang}")
                buf = io.BytesIO()
                gTTS(text=text, lang=lang).write_to_fp(buf)
                mp3_bytes = buf.getvalue()
                # Evict oldest entry if cache full
                if len(_GTTS_CACHE) >= _GTTS_CACHE_MAX:
                    oldest = next(iter(_GTTS_CACHE))
                    del _GTTS_CACHE[oldest]
                _GTTS_CACHE[cache_key] = mp3_bytes

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_file.write(mp3_bytes)
            temp_file.close()
            try:
                playsound(temp_file.name)
            finally:
                try:
                    os.unlink(temp_file.name)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[VECTOR][tts] gTTS speak failed: {e} — falling back to pyttsx3")
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
