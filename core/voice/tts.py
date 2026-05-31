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
_KOKORO_UNSUPPORTED = {"bn", "as"}  # Google Cloud TTS eventually; pyttsx3 for now


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

    def speak(self, text: str, lang: str = "en", agent=None, profile_name: str | None = None) -> None:
        """Synthesize and play text.

        agent: optional AgentBase instance — if provided, its get_voice_style()
               is logged as context.
        profile_name: optional voice profile name. If the profile has a reference
               sample and local cloning (chatterbox-tts) is available, speech is
               rendered in that cloned voice. Falls back to Kokoro/pyttsx3 otherwise.
               profile_name=None keeps current behaviour exactly unchanged.
        """
        if not text:
            return
        if agent is not None:
            try:
                style = agent.get_voice_style()
                logger.debug("[VECTOR][tts] voice_style for {}: {}", agent.name, style[:60])
            except Exception:
                pass
        # Cloned-voice path — only when a profile with a reference sample is requested
        if profile_name and self._speak_clone(text, profile_name):
            return
        # bn/as not supported by Kokoro — use pyttsx3 (Google Cloud TTS in future)
        if self._kokoro_ok and lang not in _KOKORO_UNSUPPORTED:
            self._speak_kokoro(text, lang)
        else:
            if lang in _KOKORO_UNSUPPORTED:
                logger.info(f"[VECTOR][tts] {lang} not in Kokoro — using pyttsx3 (Google TTS TODO)")
            self._speak_pyttsx3(text)

    def _speak_clone(self, text: str, profile_name: str) -> bool:
        """Render `text` in a cloned voice profile and play it. Returns True on success.

        Looks up the profile's reference WAV, synthesizes via the local VoiceCloner
        (chatterbox-tts), and plays it. Returns False if cloning is unavailable so
        the caller can fall back to Kokoro/pyttsx3.
        """
        try:
            from core.voice.cloning import get_cloner
            cloner = get_cloner()
            if not cloner.available():
                logger.info("[VECTOR][tts] cloning unavailable (chatterbox-tts not installed) — falling back")
                return False
            from core.voice.voice_profiles import get_profile_store
            store = get_profile_store()
            ref_bytes = store.get_reference_bytes(profile_name)
            if not ref_bytes:
                logger.info("[VECTOR][tts] profile '{}' has no reference sample — falling back", profile_name)
                return False
            import sounddevice as sd
            audio, sr = cloner.synthesize_long(text, reference_wav=ref_bytes)
            logger.info("[VECTOR][tts] cloned-voice speak '{}...' profile={}", text[:40], profile_name)
            sd.play(audio, samplerate=sr)
            sd.wait()
            return True
        except Exception as e:
            logger.warning("[VECTOR][tts] cloned-voice speak failed: {} — falling back", e)
            return False

    def synthesize_to_file(self, text: str, out_path: str, profile_name: str | None = None) -> dict:
        """Render `text` to a WAV file. If profile_name has a reference sample and
        cloning is available, renders in that cloned voice. Returns a result dict.
        Used by the content district (script → audio) and the Voice Studio panel.
        """
        from pathlib import Path as _P
        _P(out_path).parent.mkdir(parents=True, exist_ok=True)
        # Cloned-voice path
        if profile_name:
            try:
                from core.voice.cloning import get_cloner
                from core.voice.voice_profiles import get_profile_store
                cloner = get_cloner()
                if cloner.available():
                    ref = get_profile_store().get_reference_bytes(profile_name)
                    if ref:
                        import soundfile as sf
                        audio, sr = cloner.synthesize_long(text, reference_wav=ref)
                        sf.write(out_path, audio, sr)
                        logger.info("[VECTOR][tts] wrote cloned audio → {} (profile={})", out_path, profile_name)
                        return {"status": "ok", "path": out_path, "engine": "clone", "profile": profile_name}
            except Exception as e:
                logger.warning("[VECTOR][tts] file clone failed: {} — falling back to Kokoro", e)
        # Kokoro fallback to file
        try:
            if self._kokoro_ok:
                import soundfile as sf
                voice = _KOKORO_VOICE_MAP.get("en", _KOKORO_VOICE_MAP["en"])
                samples, sr = self._kokoro.create(text, voice=voice, speed=self._speed)
                sf.write(out_path, samples, sr)
                logger.info("[VECTOR][tts] wrote Kokoro audio → {}", out_path)
                return {"status": "ok", "path": out_path, "engine": "kokoro"}
        except Exception as e:
            logger.warning("[VECTOR][tts] Kokoro file render failed: {}", e)
        return {"status": "error", "error": "no file-capable TTS engine available (need chatterbox-tts or kokoro)"}

    def _speak_kokoro(self, text: str, lang: str) -> None:
        try:
            import sounddevice as sd
            import numpy as np
            voice = _KOKORO_VOICE_MAP.get(lang, _KOKORO_VOICE_MAP["en"])
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
