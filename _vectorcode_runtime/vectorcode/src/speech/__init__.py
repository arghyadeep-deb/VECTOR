# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Speech subsystem — speech-to-text and text-to-speech backends."""

from loguru import logger
import importlib

# Optional STT backends — each registers itself via @SpeechRegistry.register()
for _mod in ("faster_whisper", "openai_whisper", "deepgram"):
    try:
        importlib.import_module(f".{_mod}", __name__)
    except ImportError:
        logger.opt(exception=True).debug(
            "[VECTOR][speech] optional STT backend {} unavailable", _mod
        )

# Optional TTS backends — each registers itself via @TTSRegistry.register()
for _mod in ("cartesia_tts", "kokoro_tts", "openai_tts"):
    try:
        importlib.import_module(f".{_mod}", __name__)
    except ImportError:
        logger.opt(exception=True).debug(
            "[VECTOR][speech] optional TTS backend {} unavailable", _mod
        )
