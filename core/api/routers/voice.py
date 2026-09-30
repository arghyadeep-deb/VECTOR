"""Voice router — /voice endpoint.

Pipeline: audio -> Whisper (local) -> language detect -> intent classify -> action -> TTS
All audio is processed locally (RULE 5 - audio never leaves device).
"""

import sys

__all__ = [
    "router",
    "voice_endpoint",
    "voice_speak",
    "voice_status",
]

import importlib.util
import time

from fastapi import APIRouter, UploadFile, File, Response
from loguru import logger

from core.api.schemas import VoiceResponse
from core.config import CONFIG

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("", response_model=VoiceResponse)
async def voice_endpoint(audio: UploadFile = File(...)):
    """Process voice input through the voice pipeline."""
    start = time.perf_counter()

    try:
        audio_data = await audio.read()

        # Step 1: Transcribe with Whisper (local) - offload blocking I/O to thread pool
        import asyncio
        import numpy as np
        import soundfile as sf
        import io

        stt = await asyncio.to_thread(_load_whisper_stt)

        try:
            audio_io = io.BytesIO(audio_data)
            audio_np, sample_rate = sf.read(audio_io, dtype='float32')
            if len(audio_np.shape) > 1:
                audio_np = audio_np[:, 0]
        except Exception:
            audio_np = None

        if audio_np is not None:
            transcript = await asyncio.to_thread(stt.transcribe, audio_np, sample_rate)
        else:
            transcript = ""

        if not transcript:
            return VoiceResponse(
                transcript="",
                response="I didn't catch that. Could you repeat?",
                language_detected="en",
            )

        # Step 2: Detect language
        lang_detector = await asyncio.to_thread(_load_lang_detector)
        language = lang_detector.detect(transcript)

        # Step 3: Classify intent
        listener = await asyncio.to_thread(_load_ambient_listener)
        ctx = await asyncio.to_thread(_load_context_engine)
        hydration = ctx.session_hydration_prompt()
        intent = await listener._classify_intent(transcript, hydration, conversation_history=[])

        # Step 4: Execute through permission gateway
        from core.loop.permission_gateway import PermissionGateway, Action
        gw = PermissionGateway()
        action = Action(
            action_type=intent.get("action_type", "respond"),
            params=intent.get("params", {}),
            proposed_by="voice",
        )
        result = await gw.execute(action)
        if isinstance(result, dict):
            response_text = (
                result.get("response")
                or result.get("message")
                or result.get("output")
                or result.get("reasoning")
                or "Done."
            )
        else:
            response_text = str(result or "Done.")

        # Step 4b: Consistency check with PersonalityEngine (if enabled)
        if CONFIG.get("personality", {}).get("enabled", True):
            try:
                from core.personality import PersonalityEngine
                pe = PersonalityEngine()
                validation = pe.validate_response(response_text, transcript)
                if validation.get("rewritten"):
                    response_text = validation["rewritten"]
                    logger.debug("[VECTOR][api][voice] response rewritten by consistency enforcer")
            except Exception as e:
                logger.debug(f"[VECTOR][api][voice] consistency check skipped: {e}")

        # Step 5: Speak response
        # 2026-07-28: was `lang=language.split('-')[0]` — picked the TTS voice
        # from the DETECTED INPUT language, not the response text's language.
        # VECTOR now always replies in English (owner decision), so the voice
        # must always be the English voice regardless of what language the
        # user spoke in.
        tts = await asyncio.to_thread(_load_tts)
        await asyncio.to_thread(tts.speak, response_text, lang="en")

        return VoiceResponse(
            transcript=transcript,
            response=response_text,
            language_detected=language,
        )

    except Exception as e:
        logger.error(f"[VECTOR][api][voice] error: {e}")
        return VoiceResponse(
            transcript="",
            response="Voice processing failed.",
            language_detected="en",
        )


def _load_whisper_stt():
    from core.voice.stt import WhisperSTT
    return WhisperSTT()


def _load_lang_detector():
    from core.voice.language_detector import LanguageDetector
    return LanguageDetector()


def _load_ambient_listener():
    from core.voice.ambient_listener import AmbientListener
    return AmbientListener()


def _load_tts():
    from core.voice.tts import VoiceTTS
    return VoiceTTS()

def _load_context_engine():
    from core.loop.context_engine import ContextEngine
    return ContextEngine()


@router.get("/status")
async def voice_status():
    """Get status of the voice pipeline components."""
    try:
        voice_cfg = CONFIG.get("voice", {}) if isinstance(CONFIG, dict) else {}
        stt_available = importlib.util.find_spec("core.voice.stt") is not None
        tts_available = importlib.util.find_spec("core.voice.tts") is not None
        listener_available = importlib.util.find_spec("core.voice.ambient_listener") is not None
        ambient_enabled = bool(voice_cfg.get("ambient_enabled", False))
        try:
            from core.voice.ambient_listener import has_ambient_consent

            consent_granted = has_ambient_consent()
        except Exception:
            consent_granted = False

        return {
            "status": "ok",
            "stt_engine": "Whisper",
            "stt_status": "available" if stt_available else "missing",
            "tts_engine": "local",
            "tts_status": "available" if tts_available else "missing",
            "listener_status": "armed" if (listener_available and ambient_enabled and consent_granted) else "standby",
            "ambient_enabled": ambient_enabled,
            "ambient_consent": consent_granted,
            "wake_word": voice_cfg.get("wake_word", "Hey Vector"),
        }
    except Exception as e:
        logger.error(f"[VECTOR][api][voice] status check failed: {e}")
        return {
            "stt_status": "error",
            "tts_status": "error",
            "listener_status": "offline",
            "error": str(e)
        }

@router.post("/speak")
async def voice_speak(body: dict):
    """Speak text through TTS (used by nudge engine)."""
    text = body.get("text", "")
    if not text:
        return {"status": "no_text"}
    try:
        from core.voice.tts import VoiceTTS
        tts = VoiceTTS()
        import asyncio
        await asyncio.to_thread(tts.speak, text)
        return {"status": "spoken"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# Cached TTS for /tts — VoiceTTS() re-inits Kokoro (~2-4s) per instance, so the
# HUD's per-reply synthesis must reuse one engine.
_TTS_SINGLETON = None


def _get_tts_singleton():
    global _TTS_SINGLETON
    if _TTS_SINGLETON is None:
        from core.voice.tts import VoiceTTS
        _TTS_SINGLETON = VoiceTTS()
    return _TTS_SINGLETON


@router.post("/tts")
async def voice_tts(body: dict):
    """Synthesize text → WAV (Kokoro, config voice) and return the audio bytes.

    Used by the HUD so the browser plays VECTOR's real Kokoro voice instead of
    the robotic browser speechSynthesis (owner rule: male + not robotic)."""
    text = (body.get("text") or "").strip()
    if not text:
        return Response(status_code=400)
    tts = _get_tts_singleton()
    if not getattr(tts, "_kokoro_ok", False):
        tts._init_kokoro()  # retry — may have failed at boot under GPU contention
    if not getattr(tts, "_kokoro_ok", False):
        return Response(status_code=503)

    import asyncio
    import io

    def _synth() -> bytes:
        import soundfile as sf
        from core.voice.tts import _voice_for
        samples, sr = tts._kokoro.create(text[:600], voice=_voice_for("en"), speed=tts._speed)
        buf = io.BytesIO()
        sf.write(buf, samples, sr, format="WAV")
        return buf.getvalue()

    try:
        wav = await asyncio.to_thread(_synth)
    except Exception as e:
        logger.warning(f"[VECTOR][voice] /tts synth failed: {e}")
        return Response(status_code=503)
    return Response(content=wav, media_type="audio/wav")


# ── Voice profile endpoints (voicebox absorption) ─────────────────────────────

@router.get("/profiles")
async def list_voice_profiles():
    """List all stored voice profiles."""
    try:
        from core.voice.voice_profiles import get_profile_store
        store = get_profile_store()
        return {"profiles": [p.to_dict() for p in store.list_all()]}
    except Exception as e:
        return {"error": str(e)}


@router.post("/profiles")
async def create_voice_profile(body: dict):
    """Create a new voice profile. Body: VoiceProfile fields as JSON."""
    try:
        from core.voice.voice_profiles import VoiceProfile, get_profile_store
        profile = VoiceProfile(**body)
        get_profile_store().create(profile)
        return {"status": "created", "name": profile.name}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/profiles/{name}/sample")
async def upload_reference_sample(name: str, audio: "UploadFile" = File(...)):
    """Upload a reference WAV clip for a cloned voice profile."""
    try:
        from core.voice.voice_profiles import get_profile_store
        raw = await audio.read()
        key = get_profile_store().upload_reference(name, raw, audio.filename or "reference.wav")
        return {"status": "stored", "key": key}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/profiles/{name}/default")
async def set_default_profile(name: str):
    """Set the given profile as the active default voice."""
    try:
        from core.voice.voice_profiles import get_profile_store
        get_profile_store().set_default(name)
        return {"status": "ok", "default": name}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/profiles/{name}/design")
async def design_voice_profile(name: str, body: dict):
    """VoxCPM2 Voice Design — generate a voice from a text description, with
    NO reference audio needed (docs/repo_analysis/VoxCPM.md). Renders a short
    sample, stores it as the profile's reference clip, and (if requested)
    sets it as the active default — the path that builds the British
    "VECTOR voice" persona from a one-line prompt.

    Body: {"description": "<voice description>", "sample_text": "<text to render>",
           "set_default": false}
    Falls back to CONFIG["voice"]["voice_design_description"] when
    "description" is omitted.
    """
    try:
        from core.voice.voxcpm_cloning import get_voxcpm_cloner
        from core.voice.voice_profiles import VoiceProfile, get_profile_store
        from core.config import CONFIG
        import io
        import soundfile as sf

        cloner = get_voxcpm_cloner()
        if not cloner.available():
            return {"status": "error", "error": "voxcpm not installed. Run: pip install voxcpm"}

        description = body.get("description") or CONFIG.get("voice", {}).get("voice_design_description", "")
        sample_text = body.get("sample_text") or "Hello, I am VECTOR."

        audio, sr = cloner.design(description, sample_text)
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format="WAV")
        wav_bytes = buf.getvalue()

        store = get_profile_store()
        if not store.get(name):
            store.create(VoiceProfile(name=name, engine="voxcpm", personality=description))
        key = store.upload_reference(name, wav_bytes, f"{name}_design.wav")

        if body.get("set_default"):
            store.set_default(name)

        return {"status": "ok", "name": name, "key": key, "description": description}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Voice Studio: content script → audio in your cloned voice ─────────────────

@router.post("/studio/generate")
async def studio_generate(body: dict):
    """Render a script to a WAV file in the chosen voice profile (cloned, local).

    Body: {"text": "<script>", "profile": "owner", "filename": "optional.wav"}
    Returns the saved file path + the URL to fetch it via /voice/studio/audio/{file}.
    """
    import asyncio, uuid as _uuid
    from pathlib import Path as _P
    text = (body.get("text") or "").strip()
    profile = body.get("profile") or "owner"
    if not text:
        return {"status": "error", "error": "no text provided"}
    out_dir = (_P(__file__).parent.parent.parent.parent / "data" / "voice_output").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # Path-traversal guard: same basename-only sanitization studio_audio()
    # below already applies on the read side -- this write side took the
    # caller-supplied filename directly into out_dir / fname with no
    # confinement, allowing a ../ filename to write the synthesized WAV
    # anywhere the process has write access. Path(x).name alone is NOT
    # enough: Path("..").name == ".." (a valid final path component, not
    # stripped), so ".." still resolves one directory above out_dir --
    # confirm the final resolved path is actually still inside out_dir,
    # the same Path.is_relative_to() pattern already used this cycle in
    # code_intel.py / knowledge.py.
    requested_name = body.get("filename")
    fname = _P(requested_name).name if requested_name else ""
    candidate = (out_dir / fname).resolve() if fname else None
    if not candidate or candidate == out_dir or not candidate.is_relative_to(out_dir):
        fname = f"studio_{_uuid.uuid4().hex[:8]}.wav"
    out_path = str(out_dir / fname)
    try:
        from core.voice.tts import VoiceTTS
        result = await asyncio.to_thread(
            VoiceTTS().synthesize_to_file, text, out_path, profile
        )
        if result.get("status") == "ok":
            result["audio_url"] = f"/voice/studio/audio/{fname}"
        return result
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/studio/audio/{filename}")
async def studio_audio(filename: str):
    """Serve a generated Voice Studio WAV for playback/download."""
    from pathlib import Path as _P
    from fastapi.responses import FileResponse
    from fastapi import HTTPException
    # Path-traversal guard: only basename, only under data/voice_output
    safe = _P(filename).name
    out_dir = _P(__file__).parent.parent.parent.parent / "data" / "voice_output"
    target = out_dir / safe
    if not target.exists():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(str(target), media_type="audio/wav", filename=safe)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ voice.py OK")
