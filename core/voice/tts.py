import sys

__all__ = [
    "StreamingTTS",
    "TextToSpeech",
    "VoiceTTS",
]

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG

# Kokoro-supported voices only. bn/as not supported by Kokoro â€” routed to pyttsx3 fallback.
_KOKORO_VOICE_MAP = {
    "en": "bf_emma",
    "hi": "hf_alpha",
    "ja": "jf_alpha",
}
_KOKORO_UNSUPPORTED = {"bn", "as"}  # gTTS fallback for regional languages


# LRU cache for gTTS audio: maps (text, lang) â†’ raw MP3 bytes
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
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000))
        # ElevenLabs streaming (C4) — opt-in via CONFIG["voice"]["elevenlabs_streaming"]
        self._el_ok = False
        self._el_client = None
        self._el_voice_id = ""
        self._el_model = "eleven_turbo_v2"
        self._el_prosody: dict = {
            "stability":        CONFIG.get("voice", {}).get("el_stability", 0.75),
            "similarity_boost": CONFIG.get("voice", {}).get("el_similarity_boost", 0.85),
            "style":            CONFIG.get("voice", {}).get("el_style", 0.3),
            "use_speaker_boost": True,
        }
        self._init_engines()

    def _init_engines(self):
        # ElevenLabs streaming (opt-in cloud TTS — disabled by default, privacy-safe)
        self._el_ok = self._init_elevenlabs()
        # Phase 5A: Priority order: Piper > Kokoro > pyttsx3
        self._init_piper()
        if not self._kokoro_ok:
            self._init_kokoro()
        if not self._kokoro_ok:
            self._init_pyttsx3()

    def _init_piper(self):
        """Try Piper TTS (piper-tts package) â€” fast, local, high quality."""
        try:
            from piper import PiperVoice  # type: ignore
            import wave, io
            # Look for voice model in models/piper/
            piper_dir = Path(CONFIG.get("voice", {}).get("piper_model_dir", "./models/piper"))
            onnx_files = list(piper_dir.glob("*.onnx")) if piper_dir.exists() else []
            if not onnx_files:
                return  # no Piper model installed
            model_path = onnx_files[0]
            config_path = model_path.with_suffix(".onnx.json")
            if not config_path.exists():
                return
            self._piper = PiperVoice.load(str(model_path), config_path=str(config_path))
            self._kokoro_ok = True  # reuse flag to mean "primary TTS ready"
            self._tts_engine = "piper"
            logger.info(f"[VECTOR][tts] Piper TTS ready ({model_path.name})")
        except ImportError:
            pass  # piper-tts not installed
        except Exception as e:
            logger.debug(f"[VECTOR][tts] Piper init failed: {e}")

    def _init_kokoro(self):
        try:
            from kokoro_onnx import Kokoro
            voices_file = self._model_dir / "voices-v1.0.bin"
            cpu_model = self._model_dir / "kokoro-v1.0.onnx"
            fp16_model = self._model_dir / "kokoro-v1.0.fp16-gpu.onnx"
            model_file = fp16_model if fp16_model.exists() else cpu_model
            if not model_file.exists() or not voices_file.exists():
                logger.warning(f"[VECTOR][tts] Kokoro model files not found at {self._model_dir} â€” using pyttsx3 fallback")
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
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

    def speak(self, text: str, lang: str = "en") -> None:
        if not text:
            return
        # Phase 5A: Piper > Kokoro > gTTS > pyttsx3
        if self._kokoro_ok and getattr(self, '_tts_engine', 'kokoro') == 'piper' and lang == "en":
            self._speak_piper(text)
        elif self._kokoro_ok and lang not in _KOKORO_UNSUPPORTED:
            self._speak_kokoro(text, lang)
        else:
            if lang in _KOKORO_UNSUPPORTED:
                logger.info(f"[VECTOR][tts] {lang} not in Kokoro â€” using gTTS fallback")
                self._speak_gtts(text, lang)
            else:
                self._speak_pyttsx3(text)

    def _speak_piper(self, text: str) -> None:
        """Speak using Piper TTS (Phase 5A)."""
        try:
            import sounddevice as sd
            import numpy as np
            import io, wave
            self._speaking = True
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                self._piper.synthesize(text, wf)
            buf.seek(0)
            with wave.open(buf, 'rb') as wf:
                sr = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(audio, samplerate=sr)
            sd.wait()
            self._speaking = False
        except Exception as e:
            logger.warning(f"[VECTOR][tts] Piper speak failed: {e} â€” falling back to pyttsx3")
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
            logger.warning(f"[VECTOR][tts] Kokoro speak failed: {e} â€” falling back to pyttsx3")
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
                # Cache hit â€” no HTTP call needed
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
                    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        except Exception as e:
            logger.error(f"[VECTOR][tts] gTTS speak failed: {e} â€” falling back to pyttsx3")
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


class StreamingTTS:
    def __init__(self):
        import numpy as np
        self._np = np
        self._kokoro = None
        self._pyttsx3 = None
        self._kokoro_ok = False
        self._speaking = False
        self._model_dir = Path(CONFIG.get("voice", {}).get("kokoro_model_dir", "./models/kokoro"))
        self._speed = CONFIG.get("voice", {}).get("kokoro_speed", 0.85)
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
        self._current_voice = "bf_emma"
        self._init_engines()

    def _init_engines(self):
        try:
            from kokoro_onnx import Kokoro
            voices_file = self._model_dir / "voices-v1.0.bin"
            gpu_model = self._model_dir / "kokoro-v1.0.fp16-gpu.onnx"
            cpu_model = self._model_dir / "kokoro-v1.0.onnx"
            model_file = gpu_model if gpu_model.exists() else cpu_model
            if model_file.exists() and voices_file.exists():
                self._kokoro = Kokoro(str(model_file), str(voices_file))
                self._kokoro_ok = True
                logger.info(f"[VECTOR][tts:streaming] Kokoro ready ({model_file.name})")
        except Exception as e:
            logger.warning(f"[VECTOR][tts:streaming] Kokoro init failed: {e}")
        if not self._kokoro_ok:
            try:
                import pyttsx3
                self._pyttsx3 = pyttsx3.init()
                logger.info("[VECTOR][tts:streaming] pyttsx3 fallback ready")
            except Exception as e:
                logger.error(f"[VECTOR][tts:streaming] pyttsx3 init failed: {e}")

    def set_voice(self, voice_name: str) -> None:
        self._current_voice = voice_name
        logger.info(f"[VECTOR][tts:streaming] voice set to {voice_name}")

    def generate_stream(self, text: str, callback: callable) -> None:
        import re
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if not sentences:
            sentences = [text]
        self._speaking = True
        for sentence in sentences:
            if not self._speaking:
                break
            if self._kokoro_ok:
                try:
                    samples, sample_rate = self._kokoro.create(
                        sentence, voice=self._current_voice, speed=self._speed
                    )
                    callback(samples, sample_rate)
                except Exception as e:
                    logger.debug(f"[VECTOR][tts:streaming] Kokoro sentence failed: {e}")
            else:
                callback(self._np.zeros(int(self._sample_rate * 0.5), dtype=self._np.float32), self._sample_rate)

    def cross_fade(self, chunk1, chunk2, overlap_ms: int = 50):
        overlap_samples = int(self._sample_rate * overlap_ms / 1000)
        if len(chunk1) < overlap_samples or len(chunk2) < overlap_samples:
            return self._np.concatenate([chunk1, chunk2])
        fade_out = self._np.linspace(1.0, 0.0, overlap_samples, dtype=self._np.float32)
        fade_in = self._np.linspace(0.0, 1.0, overlap_samples, dtype=self._np.float32)
        chunk1_end = chunk1[-overlap_samples:] * fade_out
        chunk2_start = chunk2[:overlap_samples] * fade_in
        blended = chunk1_end + chunk2_start
        return self._np.concatenate([chunk1[:-overlap_samples], blended, chunk2[overlap_samples:]])

    def early_terminate(self) -> None:
        self._speaking = False
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

    @property
    def is_speaking(self) -> bool:
        return self._speaking


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    tts = VoiceTTS()
    tts.speak("Hello, I am VECTOR. Voice pipeline is online.", lang="en")
    st = StreamingTTS()
    st.set_voice("bf_emma")
    print(f"âœ… tts OK (streaming_tts_kokoro={st._kokoro_ok})")
