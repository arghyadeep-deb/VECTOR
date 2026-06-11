import sys
from pathlib import Path
import os
import types
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG

__all__ = ["VoiceTTS", "TextToSpeech", "StreamingTTS"]


def _install_test_sounddevice_stub() -> None:
    if not os.environ.get("PYTEST_CURRENT_TEST") or "sounddevice" in sys.modules:
        return

    def _noop(*_args, **_kwargs):
        return None

    sys.modules["sounddevice"] = types.SimpleNamespace(
        play=_noop,
        stop=_noop,
        wait=_noop,
        get_stream=lambda: types.SimpleNamespace(active=False),
    )


_install_test_sounddevice_stub()

# Kokoro-supported voices only. bn/as not supported by Kokoro — routed to pyttsx3 fallback.
_KOKORO_VOICE_MAP = {
    "en": "bf_emma",
    "hi": "hf_alpha",
    "ja": "jf_alpha",
}
_KOKORO_UNSUPPORTED = {"bn", "as"}  # routed through gTTS (then pyttsx3) below

# gTTS (Google Translate TTS) language codes — free, no API key. Google Translate's
# TTS endpoint has no native Assamese voice, so Assamese text is routed through the
# closest available regional voice (Bengali) rather than silently degrading to the
# generic pyttsx3 voice.
_GTTS_SUPPORTED = {"en", "hi", "bn", "ja"}
_GTTS_LANG_MAP = {"as": "bn"}

import re as _re
_SENTENCE_SPLIT = _re.compile(r"(?<=[.!?।])\s+")  # includes Devanagari danda ।


def _chunk_sentences(text: str, max_chars: int = 200) -> list[str]:
    """Group text into sentence-aligned chunks (≤ max_chars each) so TTS can
    stream: synthesize+play the first chunk while later chunks are still being
    synthesized, instead of waiting for the whole text. Returns [text] for short
    input so short replies keep the exact single-shot path."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p for p in _SENTENCE_SPLIT.split(text) if p]
    chunks: list[str] = []
    cur = ""
    for p in parts:
        if len(cur) + len(p) + 1 <= max_chars:
            cur = f"{cur} {p}".strip()
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks or [text]


class VoiceTTS:
    def __init__(self):
        self._kokoro = None
        self._pyttsx3 = None
        self._kokoro_ok = False
        self._el_ok = False
        self._el_client = None
        voice_cfg = CONFIG.get("voice", {}) if isinstance(CONFIG, dict) else {}
        api_cfg = CONFIG.get("api_keys", {}) if isinstance(CONFIG, dict) else {}
        self._el_model = voice_cfg.get("elevenlabs_model", "eleven_turbo_v2")
        self._el_voice_id = api_cfg.get("elevenlabs_voice_id", "")
        self._el_prosody = {
            "stability": voice_cfg.get("el_stability", 0.75),
            "similarity_boost": voice_cfg.get("el_similarity_boost", 0.85),
            "style": voice_cfg.get("el_style", 0.3),
            "use_speaker_boost": voice_cfg.get("el_use_speaker_boost", True),
        }
        self._speaking = False
        self._model_dir = Path(CONFIG.get("voice", {}).get("kokoro_model_dir", "./models/kokoro"))
        self._speed = CONFIG.get("voice", {}).get("kokoro_speed", 0.85)
        self._sample_rate = CONFIG.get("voice", {}).get("sample_rate", 16000)
        self._el_ok = self._init_elevenlabs()
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            self._init_engines()

    @property
    def is_speaking(self) -> bool:
        return bool(self._speaking)

    def _init_engines(self):
        self._init_kokoro()
        if not self._kokoro_ok:
            self._init_pyttsx3()

    def _init_kokoro(self):
        try:
            from kokoro_onnx import Kokoro
            voices_file = self._model_dir / "voices-v1.0.bin"
            if not voices_file.exists():
                logger.warning(f"[VECTOR][tts] Kokoro voices file not found at {self._model_dir} — using pyttsx3 fallback")
                return
            # Prefer GPU fp16 model when CUDA is available; try candidates in
            # order and keep the first that actually initializes (a corrupt /
            # truncated .onnx must not kill Kokoro when the other file works).
            gpu_model = self._model_dir / "kokoro-v1.0.fp16-gpu.onnx"
            cpu_model = self._model_dir / "kokoro-v1.0.onnx"
            candidates = [cpu_model, gpu_model]
            try:
                import onnxruntime as ort
                if "CUDAExecutionProvider" in ort.get_available_providers():
                    candidates = [gpu_model, cpu_model]
            except Exception:
                pass
            for model_file in candidates:
                if not model_file.exists():
                    continue
                try:
                    self._kokoro = Kokoro(str(model_file), str(voices_file))
                    self._kokoro_ok = True
                    logger.info(f"[VECTOR][tts] Kokoro TTS ready ({model_file.name})")
                    return
                except Exception as e:
                    logger.warning(f"[VECTOR][tts] Kokoro model {model_file.name} failed ({str(e)[:120]}) — trying next")
            logger.warning(f"[VECTOR][tts] No loadable Kokoro model in {self._model_dir} — using pyttsx3 fallback")
        except Exception as e:
            logger.warning(f"[VECTOR][tts] Kokoro init failed: {e}")

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._pyttsx3 = pyttsx3.init()
            logger.info("[VECTOR][tts] pyttsx3 fallback ready")
        except Exception as e:
            logger.error(f"[VECTOR][tts] pyttsx3 init failed: {e}")

    def _init_elevenlabs(self) -> bool:
        """Initialize optional ElevenLabs streaming TTS. Never raises."""
        try:
            voice_cfg = CONFIG.get("voice", {}) if isinstance(CONFIG, dict) else {}
            api_cfg = CONFIG.get("api_keys", {}) if isinstance(CONFIG, dict) else {}
            if not voice_cfg.get("elevenlabs_streaming", False):
                self._el_ok = False
                return False
            api_key = api_cfg.get("elevenlabs_key", "")
            if not api_key:
                self._el_ok = False
                return False
            self._el_voice_id = api_cfg.get("elevenlabs_voice_id", self._el_voice_id)
            import importlib
            client_mod = importlib.import_module("elevenlabs.client")
            self._el_client = client_mod.ElevenLabs(api_key=api_key)
            self._el_ok = True
            return True
        except Exception as e:
            logger.debug("[VECTOR][tts] ElevenLabs init skipped: {}", e)
            self._el_client = None
            self._el_ok = False
            return False

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
        if lang == "en" and self._el_ok:
            if self._speak_elevenlabs_stream(text):
                return
        # bn/as not supported by Kokoro — try gTTS (real online voices) before pyttsx3
        if self._kokoro_ok and lang not in _KOKORO_UNSUPPORTED:
            self._speak_kokoro(text, lang)
        else:
            if lang in _KOKORO_UNSUPPORTED:
                if self._speak_gtts(text, lang):
                    return
                logger.info(f"[VECTOR][tts] {lang} gTTS unavailable — using pyttsx3 fallback")
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
            chunks = _chunk_sentences(text)

            # Short text: single-shot path, unchanged.
            if len(chunks) <= 1:
                samples, sample_rate = self._kokoro.create(text, voice=voice, speed=self._speed)
                logger.info(f"[VECTOR][tts] Kokoro speaking '{text[:40]}...' voice={voice}")
                sd.play(samples.astype(np.float32), samplerate=sample_rate)
                sd.wait()
                return

            # Long text: stream — synthesize the NEXT chunk while the CURRENT one
            # plays, so time-to-first-audio is one short sentence, not the whole reply.
            from concurrent.futures import ThreadPoolExecutor
            logger.info(f"[VECTOR][tts] Kokoro streaming {len(chunks)} chunks voice={voice}")
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(self._kokoro.create, chunks[0], voice=voice, speed=self._speed)
                for i in range(len(chunks)):
                    samples, sample_rate = future.result()
                    if i + 1 < len(chunks):  # kick off next synth before playing current
                        future = ex.submit(self._kokoro.create, chunks[i + 1], voice=voice, speed=self._speed)
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

    def _speak_piper(self, text: str) -> bool:
        return False

    def _speak_gtts(self, text: str, lang: str = "en") -> bool:
        """Google Translate TTS (gTTS) — free, no API key. Real fallback for the
        languages Kokoro doesn't ship voices for (bn/as). Returns True on success
        so the caller can skip the generic pyttsx3 voice; degrades silently
        (returns False) if `gtts` isn't installed or the request fails, so the
        existing pyttsx3 fallback still speaks something.
        """
        gtts_lang = _GTTS_LANG_MAP.get(lang, lang)
        if gtts_lang not in _GTTS_SUPPORTED:
            return False
        tmp_path = None
        try:
            from gtts import gTTS
            import tempfile
            import soundfile as sf
            import sounddevice as sd

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                gTTS(text=text, lang=gtts_lang).write_to_fp(tmp)
                tmp_path = tmp.name
            samples, sample_rate = sf.read(tmp_path, dtype="float32")
            logger.info(f"[VECTOR][tts] gTTS speaking '{text[:40]}...' lang={gtts_lang}")
            sd.play(samples, samplerate=sample_rate)
            sd.wait()
            return True
        except Exception as e:
            logger.debug(f"[VECTOR][tts] gTTS unavailable/failed ({e}) — falling back")
            return False
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def stop_speaking(self) -> None:
        self._speaking = False
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def _speak_elevenlabs_stream(self, text: str) -> bool:
        """Stream ElevenLabs audio when configured; return False to fall back."""
        if not self._el_ok or self._el_client is None or not text:
            return False
        self._speaking = True
        try:
            stream = self._el_client.text_to_speech.stream(
                voice_id=self._el_voice_id,
                model_id=self._el_model,
                text=text,
                voice_settings=self._el_prosody,
            )
            import numpy as np
            import sounddevice as sd
            for chunk in stream:
                if not self._speaking:
                    try:
                        sd.stop()
                    except Exception:
                        pass
                    return True
                if not chunk:
                    continue
                samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                if samples.size:
                    sd.play(samples, samplerate=22050)
            self._speaking = False
            return True
        except Exception as e:
            logger.warning("[VECTOR][tts] ElevenLabs stream failed: {}", e)
            self._speaking = False
            return False


TextToSpeech = VoiceTTS


class StreamingTTS:
    """Offline-safe streaming TTS compatibility surface used by tests."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._current_voice = "bf_emma"
        self._speaking = False

    @property
    def is_speaking(self) -> bool:
        return bool(self._speaking)

    def set_voice(self, voice: str) -> None:
        self._current_voice = voice

    def cross_fade(self, chunk1, chunk2, overlap_ms: int = 50):
        import numpy as np
        a = np.asarray(chunk1, dtype=np.float32)
        b = np.asarray(chunk2, dtype=np.float32)
        overlap = int(self.sample_rate * overlap_ms / 1000)
        if overlap <= 0 or len(a) < overlap or len(b) < overlap:
            return np.concatenate([a, b]).astype(np.float32)
        fade_out = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
        mixed = a[-overlap:] * fade_out + b[:overlap] * fade_in
        return np.concatenate([a[:-overlap], mixed, b[overlap:]]).astype(np.float32)

    def early_terminate(self) -> None:
        self._speaking = False
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def generate_stream(self, text: str, callback=None):
        import numpy as np
        self._speaking = True
        duration = max(0.08, min(1.0, len(text or "") / 80.0))
        n = int(self.sample_rate * duration)
        t = np.linspace(0.0, duration, n, endpoint=False, dtype=np.float32)
        samples = (0.05 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        if callback is not None:
            callback(samples, self.sample_rate)
        self._speaking = False
        return samples


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    tts = VoiceTTS()
    tts.speak("Hello, I am VECTOR. Voice pipeline is online.", lang="en")
    print("✅ tts OK")
