import sys
import os
import sysconfig
import types
from time import perf_counter
from pathlib import Path
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

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


def _add_cuda_dll_dirs() -> list[str]:
    """Prepend every pip-installed nvidia-*-cu12 package's bin/ dir to PATH.

    On Windows, onnxruntime's CUDAExecutionProvider loader uses plain
    LoadLibrary (not LoadLibraryEx with search flags), so neither
    os.add_dll_directory() nor the standard DLL search order finds DLLs
    sitting under site-packages/nvidia/<pkg>/bin/ — only the real PATH env
    var is consulted. Without this, Kokoro silently falls back to CPU
    (onnxruntime logs a warning, not an error) even with onnxruntime-gpu
    and all CUDA deps installed."""
    site_packages = sysconfig.get_paths()["purelib"]
    nvidia_root = os.path.join(site_packages, "nvidia")
    if not os.path.isdir(nvidia_root):
        return []
    added = []
    for pkg in sorted(os.listdir(nvidia_root)):
        bin_dir = os.path.join(nvidia_root, pkg, "bin")
        if os.path.isdir(bin_dir):
            added.append(bin_dir)
    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ["PATH"]
    return added


# Kokoro-supported voices only. bn/as not supported by Kokoro — routed to pyttsx3 fallback.
# en default is bm_george (calm British male); override via
# CONFIG['voice']['kokoro_voice'] / env VOICE__KOKORO_VOICE without code changes.
_KOKORO_VOICE_MAP = {
    "en": "bm_george",   # British male (owner: male voices ONLY, 2026-07-15)
    "hi": "hm_omega",    # Hindi male
    "ja": "jm_kumo",     # Japanese male
}


def _voice_for(lang: str) -> str:
    """Kokoro voice id for a language. The English voice is overridable via
    CONFIG['voice']['kokoro_voice'] (env: VOICE__KOKORO_VOICE) so it can be
    swapped without code changes; other languages use the fixed map."""
    if lang == "en":
        try:
            override = (CONFIG.get("voice", {}) or {}).get("kokoro_voice")
        except Exception:
            override = None
        if override:
            return override
    return _KOKORO_VOICE_MAP.get(lang, _KOKORO_VOICE_MAP["en"])
_KOKORO_UNSUPPORTED = {"bn", "as"}  # routed through gTTS (then pyttsx3) below

# How many times speak() re-probes Kokoro after a failed boot before accepting
# the fallback (prevents a reload attempt on every single utterance).
_KOKORO_MAX_RETRIES = 3

# gTTS (Google Translate TTS) language codes — free, no API key. Google Translate's
# TTS endpoint has no native Assamese voice, so Assamese text is routed through the
# closest available regional voice (Bengali) rather than silently degrading to the
# generic pyttsx3 voice.
_GTTS_SUPPORTED = {"en", "hi", "bn", "ja"}
_GTTS_LANG_MAP = {"as": "bn"}

import re as _re
_SENTENCE_SPLIT = _re.compile(r"(?<=[.!?।])\s+")  # includes Devanagari danda ।

# 2026-07-28 (owner-reported, live): spoken VECTOR replies sometimes came out
# sounding "AI-generated" — literal markdown syntax and/or spelled-out
# punctuation names reaching the TTS engine instead of natural spoken text.
# Root cause: none of the 4 independent LLM->TTS pipelines in this codebase
# (ambient_listener.py, core/voice/realtime.py's RealtimeConversation,
# api/routers/voice_ws.py's two handlers) ever sanitized model output before
# handing it to a synthesis engine — whatever markdown the model happened to
# produce (bold/italic asterisks, backticks, bullet markers, headers) went
# straight to Kokoro/pyttsx3/gTTS as literal text. Two of those 4 pipelines
# (core/voice/realtime.py::tts_wav, voice_ws.py::_tts_to_wav) call
# `VoiceTTS()._kokoro.create()` DIRECTLY, bypassing speak() entirely — so this
# can't be fixed by only patching speak(); every synthesis entry point needs
# to route through this first. Deliberately does NOT try to detect/strip
# spelled-out punctuation WORDS (e.g. a literal "comma" in the text) — that's
# handled at the prompt-instruction layer instead (VECTOR_PERSONALITY etc.),
# since a blind regex for common words like "comma" would wrongly mangle
# legitimate sentences that happen to use them.
_MD_BOLD_ITALIC_RE = _re.compile(r"\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*")
_MD_UNDERSCORE_EMPH_RE = _re.compile(r"(?<![A-Za-z0-9_])__(.+?)__(?![A-Za-z0-9_])")
_MD_CODE_FENCE_RE = _re.compile(r"```.*?```", _re.DOTALL)
_MD_INLINE_CODE_RE = _re.compile(r"`([^`]+)`")
_MD_HEADER_RE = _re.compile(r"^#{1,6}\s+", _re.MULTILINE)
_MD_BULLET_RE = _re.compile(r"^[ \t]*[-*•]\s+", _re.MULTILINE)
_MD_NUMBERED_RE = _re.compile(r"^[ \t]*\d+[.)]\s+", _re.MULTILINE)
_MD_LINK_RE = _re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_LEFTOVER_SYMBOLS_RE = _re.compile(r"[*_`#]")
_WHITESPACE_COLLAPSE_RE = _re.compile(r"[ \t]+")
_BLANK_LINES_RE = _re.compile(r"\n\s*\n+")


def sanitize_for_speech(text: str) -> str:
    """Strip markdown/formatting syntax before text reaches ANY TTS engine.

    Every function in this codebase that turns model output into audio should
    call this first — see the module comment above for why this can't live
    only inside VoiceTTS.speak(). Idempotent and cheap; safe to call on text
    that's already clean."""
    if not text:
        return text
    t = _MD_CODE_FENCE_RE.sub(lambda m: m.group(0).strip("`"), text)
    t = _MD_INLINE_CODE_RE.sub(r"\1", t)
    t = _MD_LINK_RE.sub(r"\1", t)
    t = _MD_HEADER_RE.sub("", t)
    t = _MD_BULLET_RE.sub("", t)
    t = _MD_NUMBERED_RE.sub("", t)
    t = _MD_UNDERSCORE_EMPH_RE.sub(r"\1", t)
    # Bold/italic asterisks: repeat once to also catch nested/adjacent runs
    # (e.g. "**a** and **b**") that a single non-overlapping pass can miss.
    for _ in range(2):
        t = _MD_BOLD_ITALIC_RE.sub(lambda m: next(g for g in m.groups() if g is not None), t)
    t = _MD_LEFTOVER_SYMBOLS_RE.sub("", t)
    t = _BLANK_LINES_RE.sub(" ", t)
    t = _WHITESPACE_COLLAPSE_RE.sub(" ", t).strip()
    return t


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


class _KokoroIOBindingSession:
    """Adapt session.run while preserving Kokoro's audio processing.

    Per-call bindings support variable shapes and concurrent synthesis. Internal
    CPU/CUDA partition copies remain; playback still needs audio on the CPU.
    No CUDA graphs: CPU nodes and data-dependent audio shapes prevent capture.
    """

    def __init__(self, session, ort, device_id: int):
        self._session = session
        self._ort = ort
        self._device_id = device_id
        self._enabled = True

    def __getattr__(self, name):
        return getattr(self._session, name)

    def run(self, output_names, input_feed, *args, **kwargs):
        # Only intercept the simple signature used by kokoro_onnx.
        if self._enabled and not args and not kwargs:
            try:
                import numpy as np
                binding = self._session.io_binding()
                values = []  # Keep device allocations alive through output copy.
                for name, value in input_feed.items():
                    array = np.asarray(value)
                    if not array.flags.c_contiguous:
                        array = np.ascontiguousarray(array)
                    device_value = self._ort.OrtValue.ortvalue_from_numpy(
                        array, "cuda", self._device_id
                    )
                    values.append(device_value)
                    binding.bind_ortvalue_input(name, device_value)
                names = output_names or [o.name for o in self._session.get_outputs()]
                for name in names:
                    # ORT allocates the data-dependent output shape.
                    binding.bind_output(name, "cuda", self._device_id)
                graph_started = perf_counter()
                self._session.run_with_iobinding(binding)
                graph_done = perf_counter()
                outputs = binding.copy_outputs_to_cpu()
                copy_done = perf_counter()
                logger.info(
                    "[VECTOR][tts][phase0] model_graph={:.1f}ms output_copy={:.1f}ms",
                    (graph_done - graph_started) * 1000.0,
                    (copy_done - graph_done) * 1000.0,
                )
                return outputs
            except Exception as e:
                self._enabled = False
                logger.warning("[VECTOR][tts] Kokoro IOBinding failed; using session.run: {}", e)
        graph_started = perf_counter()
        outputs = self._session.run(output_names, input_feed, *args, **kwargs)
        logger.info("[VECTOR][tts][phase0] model_graph={:.1f}ms backend=session.run", (perf_counter() - graph_started) * 1000.0)
        return outputs


class VoiceTTS:
    def __init__(self):
        self._kokoro = None
        self._pyttsx3 = None
        self._kokoro_ok = False
        self._kokoro_retries = 0   # see speak(): capped re-probe after a bad boot
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
            cuda_available = False
            try:
                _add_cuda_dll_dirs()
                import onnxruntime as ort
                if "CUDAExecutionProvider" in ort.get_available_providers():
                    candidates = [gpu_model, cpu_model]
                    cuda_available = True
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
            for model_file in candidates:
                if not model_file.exists():
                    continue
                try:
                    if cuda_available and model_file == gpu_model:
                        # kokoro_onnx.Kokoro(model_path, voices_path)'s own
                        # provider auto-detection checks
                        # importlib.util.find_spec("onnxruntime-gpu"), which is
                        # always False -- both the `onnxruntime` and
                        # `onnxruntime-gpu` PyPI distributions install into the
                        # same importable `onnxruntime` module name, so that
                        # check can never succeed regardless of which is
                        # installed. Left to its own logic, Kokoro() silently
                        # defaults to CPUExecutionProvider even when CUDA is
                        # fully available and _add_cuda_dll_dirs() has already
                        # made it discoverable. Build the session ourselves
                        # with explicit providers and bypass that heuristic
                        # entirely via Kokoro.from_session().
                        import onnxruntime as ort
                        session = ort.InferenceSession(
                            str(model_file),
                            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                        )
                        self._kokoro = Kokoro.from_session(session, str(voices_file))
                    else:
                        self._kokoro = Kokoro(str(model_file), str(voices_file))
                    try:
                        import onnxruntime as ort
                        session = self._kokoro.sess
                        if "CUDAExecutionProvider" in session.get_providers():
                            options = session.get_provider_options()["CUDAExecutionProvider"]
                            self._kokoro.sess = _KokoroIOBindingSession(
                                session, ort, int(options.get("device_id", 0))
                            )
                    except Exception as e:
                        logger.warning("[VECTOR][tts] Kokoro IOBinding unavailable: {}", e)
                    # Synchronous: readiness is published only after this returns.
                    # A sentence avoids punctuation-only empty phonemization.
                    # One shape cannot warm every possible CUDA algorithm path.
                    started = perf_counter()
                    try:
                        self._kokoro.create(
                            "Hello from Vector.", voice=_voice_for("en"), speed=self._speed
                        )
                    except Exception as e:
                        logger.warning("[VECTOR][tts] Kokoro pre-warm failed; keeping engine available: {}", e)
                    finally:
                        logger.info("[VECTOR][tts] Kokoro pre-warm took {:.3f}s", perf_counter() - started)
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
            # Owner rule: male voices only — pick a male SAPI voice (David on
            # Windows) instead of the default, which is usually female (Zira).
            try:
                for v in self._pyttsx3.getProperty("voices") or []:
                    ident = f"{getattr(v, 'name', '')} {getattr(v, 'id', '')}".lower()
                    if "david" in ident or "male" in ident:
                        self._pyttsx3.setProperty("voice", v.id)
                        break
            except Exception:
                pass  # default voice is still better than no voice
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
        text = sanitize_for_speech(text)
        if not text:
            return
        if agent is not None:
            try:
                style = agent.get_voice_style()
                logger.debug("[VECTOR][tts] voice_style for {}: {}", agent.name, style[:60])
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
        # Cloned-voice path — only when a profile with a reference sample is requested
        if profile_name and self._speak_clone(text, profile_name):
            return
        if lang == "en" and self._el_ok:
            if self._speak_elevenlabs_stream(text):
                return
        # Optional Supertonic live-engine swap (docs/repo_analysis/supertonic.md)
        # — bn/as are never routed here even if live_engine="supertonic",
        # they stay on the gTTS path below regardless of this setting.
        if lang not in _KOKORO_UNSUPPORTED and self._speak_supertonic(text, lang):
            return
        # Kokoro may have failed to init at boot (GPU contention) — re-probe a
        # few times so one bad boot doesn't strand the whole session on the
        # robotic pyttsx3 fallback (owner rule: never robotic). Capped: when
        # Kokoro is genuinely absent, retrying on EVERY utterance would reload-
        # spam the log and add latency to every reply (2026-07-17).
        if not self._kokoro_ok and self._kokoro_retries < _KOKORO_MAX_RETRIES:
            self._kokoro_retries += 1
            self._init_kokoro()
        # bn/as not supported by Kokoro — try gTTS (real online voices) before pyttsx3
        if self._kokoro_ok and lang not in _KOKORO_UNSUPPORTED:
            self._speak_kokoro(text, lang)
        else:
            if lang in _KOKORO_UNSUPPORTED:
                if self._speak_gtts(text, lang):
                    return
                logger.info(f"[VECTOR][tts] {lang} gTTS unavailable — using pyttsx3 fallback")
            self._speak_pyttsx3(text)

    def _speak_supertonic(self, text: str, lang: str) -> bool:
        """Try the optional Supertonic live engine. Returns False (never
        raises) when live_engine isn't "supertonic" or the package/lang
        isn't available, so the caller falls through to Kokoro unchanged."""
        try:
            from core.voice.supertonic_tts import get_live_tts
            engine_name, engine = get_live_tts()
            if engine_name != "supertonic" or engine is None or not engine.available():
                return False
            import sounddevice as sd
            samples, sr = engine.create(text, lang=lang, speed=self._speed)
            logger.info("[VECTOR][tts] supertonic speak '{}...' lang={}", text[:40], lang)
            sd.play(samples, samplerate=sr)
            sd.wait()
            return True
        except Exception as e:
            logger.warning("[VECTOR][tts] supertonic speak failed: {} — falling back to Kokoro", e)
            return False

    def _speak_clone(self, text: str, profile_name: str = "default") -> bool:
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
        text = sanitize_for_speech(text)
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
                voice = _voice_for("en")
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
            voice = _voice_for(lang)
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
            logger.warning("[VECTOR] silent swallow")
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
                        logger.warning("[VECTOR] silent swallow")
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
        self._current_voice = "bm_george"
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
            logger.warning("[VECTOR] silent swallow")
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
