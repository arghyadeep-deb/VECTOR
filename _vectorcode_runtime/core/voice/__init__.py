"""
V.E.C.T.O.R. voice package.
STT (Whisper), TTS (Kokoro/TTS), voice pipeline.
Plus absorbed VectorCode speech backends (Cartesia, Deepgram, Kokoro, OpenAI).
"""
from loguru import logger

# Wire absorbed OJ speech backends (optional — gracefully no-ops if missing)
try:
    import vectorcode.src.speech  # noqa: F401 — triggers backend registration
    logger.info("[VECTOR][voice] speech backends available")
except Exception:
    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

logger.info("[VECTOR] voice package loaded")

__all__ = ["OmniVoiceEngine", "OmniVoiceConfig"]


def __getattr__(name: str):
    if name in {"OmniVoiceEngine", "OmniVoiceConfig"}:
        from core.voice.engines.omnivoice_engine import OmniVoiceConfig, OmniVoiceEngine
        return {"OmniVoiceEngine": OmniVoiceEngine, "OmniVoiceConfig": OmniVoiceConfig}[name]
    raise AttributeError(name)
