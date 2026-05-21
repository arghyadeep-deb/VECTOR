"""
V.E.C.T.O.R. voice package.
STT (Whisper), TTS (Kokoro/TTS), voice pipeline.
Plus absorbed VectorCode speech backends (Cartesia, Deepgram, Kokoro, OpenAI).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

# Wire absorbed OJ speech backends (optional â€” gracefully no-ops if missing)
try:
    import vectorcode.src.speech  # noqa: F401 â€” triggers backend registration
    logger.info("[VECTOR][voice] speech backends available")
except Exception:
    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

logger.info("[VECTOR] voice package loaded")

__all__ = []