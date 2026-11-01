"""
VECTOR ElevenLabs TTS — high-quality voice synthesis for content creation.

Use case: content district (YouTube scripts, social media narration, audio blogs).
NOT the primary VECTOR voice — that remains Kokoro (local, private).
ElevenLabs is for content-grade audio where quality > privacy.

Requires: pip install elevenlabs
API key: set ELEVENLABS_API_KEY in .env
"""
from __future__ import annotations

__all__ = [
    "CONTENT_VOICES",
    "ElevenLabsTTS",
    "get_elevenlabs",
    "speak_content",
]


import os
from pathlib import Path

from loguru import logger
from core.config import CONFIG

_API_KEY = CONFIG.get("elevenlabs_key", "")

# VECTOR-personalized voice profile
_VECTOR_VOICE_ID = CONFIG.get("api_keys", {}).get("elevenlabs_voice_id", "pNInz6obpgDQGcFmaJgB")  # Adam — deep, authoritative
_VECTOR_VOICE_SETTINGS = {
    "stability": 0.75,           # Consistent, professional
    "similarity_boost": 0.85,    # Close to voice character
    "style": 0.3,                # Subtle expressiveness
    "use_speaker_boost": True,
}

CONTENT_VOICES = {
    "vector_default": "pNInz6obpgDQGcFmaJgB",     # Adam — VECTOR's content voice
    "vector_female": "EXAVITQu4vr4xnSDxMaL",      # Bella — alternate female voice
    "vector_narrator": "VR6AewLTigWG4xSOukaG",    # Arnold — documentary style
    "vector_friendly": "yoZ06aMxZJJ28mfd3POQ",    # Sam — conversational
}


class ElevenLabsTTS:
    """
    ElevenLabs TTS client for VECTOR content creation.

    Usage:
        tts = ElevenLabsTTS()
        audio = tts.synthesize("Welcome to today's AI briefing.")
        tts.save(audio, "output/briefing.mp3")

        # Async
        audio = await tts.asynthesize("...")
    """

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model: str = "eleven_multilingual_v2",
    ) -> None:
        self._api_key = api_key or _API_KEY
        self._voice_id = voice_id or _VECTOR_VOICE_ID
        self._model = model
        self._client = None

        if not self._api_key:
            logger.warning(
                "[VECTOR][elevenlabs] No API key — set ELEVENLABS_API_KEY in .env. "
                "ElevenLabs is for content creation only; VECTOR runtime uses Kokoro."
            )

    def _get_client(self):
        if self._client is None:
            try:
                from elevenlabs.client import ElevenLabs
                self._client = ElevenLabs(api_key=self._api_key)
            except ImportError:
                raise ImportError("Run: pip install elevenlabs")
        return self._client

    def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        output_format: str = "mp3_44100_128",
        *,
        prefer_local: bool | None = None,
    ) -> bytes:
        """
        Synthesize text to audio bytes.

        Args:
            text:          Text to speak (max ~5000 chars per call)
            voice_id:      Override voice (use CONTENT_VOICES dict for options)
            output_format: "mp3_44100_128" | "pcm_44100" | "opus_48000_32"

        Returns:
            Audio bytes (MP3 by default — or WAV when local cloner is used)
        """
        _prefer = prefer_local if prefer_local is not None else bool(
            (CONFIG.get("voice", {}) or {}).get("prefer_local_voice", True)
        )
        if _prefer:
            try:
                from core.voice.cloning import VoiceCloner, get_cloner
                from core.voice.voice_profiles import get_profile_store
                from core.voice.effects import AudioEffects
                import io, wave, numpy as np
                if VoiceCloner.available():
                    store = get_profile_store()
                    profile = store.get_default()
                    if profile is not None:
                        ref_bytes = store.get_reference_bytes(profile.name) if profile.reference_key else None
                        arr, sr = get_cloner().synthesize_long(text, reference_wav=ref_bytes)
                        if profile.effects:
                            arr = AudioEffects().apply(arr, sr, profile.effects)
                        buf = io.BytesIO()
                        with wave.open(buf, "wb") as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(sr)
                            wf.writeframes((arr * 32767).astype(np.int16).tobytes())
                        logger.info("[VECTOR][elevenlabs] local clone used for synthesize()")
                        return buf.getvalue()
            except Exception as e:
                logger.debug("[VECTOR][elevenlabs] local synthesize failed, using cloud: {}", e)

        if not self._api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")

        client = self._get_client()
        vid = voice_id or self._voice_id

        try:
            audio = client.text_to_speech.convert(
                voice_id=vid,
                text=text,
                model_id=self._model,
                voice_settings=_VECTOR_VOICE_SETTINGS,
                output_format=output_format,
            )
            # elevenlabs SDK returns a generator — collect bytes
            if hasattr(audio, "__iter__"):
                return b"".join(audio)
            return audio
        except Exception as e:
            logger.error("[VECTOR][elevenlabs] synthesis failed: {}", e)
            raise

    async def asynthesize(self, text: str, voice_id: str | None = None) -> bytes:
        """Async wrapper around synthesize."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.synthesize, text, voice_id)

    def save(self, audio: bytes, path: str | Path) -> Path:
        """Save audio bytes to file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(audio)
        logger.info("[VECTOR][elevenlabs] saved audio: {} ({:.1f} KB)", p, len(audio) / 1024)
        return p

    def synthesize_and_save(self, text: str, path: str | Path, **kwargs) -> Path:
        """Convenience: synthesize and save in one call."""
        audio = self.synthesize(text, **kwargs)
        return self.save(audio, path)

    def list_voices(self) -> list[dict]:
        """List available voices from ElevenLabs account."""
        try:
            client = self._get_client()
            response = client.voices.get_all()
            return [{"id": v.voice_id, "name": v.name, "category": v.category}
                    for v in response.voices]
        except Exception as e:
            logger.error("[VECTOR][elevenlabs] list_voices failed: {}", e)
            return []

    def clone_voice(self, name: str, audio_files: list[str], description: str = "") -> str:
        """
        Clone a voice from audio samples. Returns new voice_id.
        Use for creating a VECTOR-specific personalized voice.
        """
        try:
            client = self._get_client()
            files = [open(f, "rb") for f in audio_files]
            response = client.clone(
                name=name,
                description=description or f"VECTOR personalized voice: {name}",
                files=files,
            )
            for f in files:
                f.close()
            logger.info("[VECTOR][elevenlabs] voice cloned: {} ({})", name, response.voice_id)
            return response.voice_id
        except Exception as e:
            logger.error("[VECTOR][elevenlabs] voice cloning failed: {}", e)
            raise


# ── Convenience functions ──────────────────────────────────────────────────────

_default_tts: ElevenLabsTTS | None = None


def get_elevenlabs() -> ElevenLabsTTS:
    """Get or create the default ElevenLabs TTS instance."""
    global _default_tts
    if _default_tts is None:
        _default_tts = ElevenLabsTTS()
    return _default_tts


def speak_content(
    text: str,
    output_path: str | Path | None = None,
    voice: str = "vector_default",
    *,
    prefer_local: bool | None = None,
) -> bytes | Path:
    """
    High-level content TTS. Local cloning first when available; ElevenLabs cloud as fallback.

    prefer_local: override CONFIG["voice"]["prefer_local_voice"] (default True).
    """
    _prefer = prefer_local if prefer_local is not None else bool(
        (CONFIG.get("voice", {}) or {}).get("prefer_local_voice", True)
    )

    # Try local cloning first when enabled
    if _prefer:
        try:
            from core.voice.cloning import VoiceCloner, get_cloner
            from core.voice.voice_profiles import get_profile_store
            from core.voice.effects import AudioEffects
            import io, wave
            if VoiceCloner.available():
                store = get_profile_store()
                profile = store.get_default()
                if profile is not None:
                    ref_bytes = store.get_reference_bytes(profile.name) if profile.reference_key else None
                    cloner = get_cloner()
                    audio_arr, sr = cloner.synthesize_long(text, reference_wav=ref_bytes)
                    if profile.effects:
                        audio_arr = AudioEffects().apply(audio_arr, sr, profile.effects)
                    # Encode to WAV bytes
                    import numpy as np
                    buf = io.BytesIO()
                    with wave.open(buf, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(sr)
                        wf.writeframes((audio_arr * 32767).astype(np.int16).tobytes())
                    audio_bytes = buf.getvalue()
                    if output_path:
                        p = Path(output_path)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(audio_bytes)
                        logger.info("[VECTOR][elevenlabs] local clone saved: {}", p)
                        return p
                    return audio_bytes
        except Exception as e:
            logger.debug("[VECTOR][elevenlabs] local clone failed, falling back to ElevenLabs: {}", e)

    # ElevenLabs cloud fallback
    tts = get_elevenlabs()
    voice_id = CONTENT_VOICES.get(voice, voice)
    audio = tts.synthesize(text, voice_id=voice_id)
    if output_path:
        return tts.save(audio, output_path)
    return audio


if __name__ == "__main__":
    # Test import without API key
    tts = ElevenLabsTTS(api_key="test")
    assert tts._voice_id == _VECTOR_VOICE_ID
    assert len(CONTENT_VOICES) >= 4
    print(f"OK elevenlabs_tts.py — {len(CONTENT_VOICES)} content voices configured")
    print("Note: Set ELEVENLABS_API_KEY in .env to enable synthesis")
