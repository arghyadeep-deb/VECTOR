"""
V.E.C.T.O.R. voice package.
STT (Whisper), TTS (Kokoro/TTS), voice pipeline.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

logger.info("[VECTOR] voice package loaded")

__all__ = []