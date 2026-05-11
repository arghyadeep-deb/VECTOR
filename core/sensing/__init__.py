"""
V.E.C.T.O.R. sensing package.
Ambient listening, screen sensing, phone bridge, wearable integration.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

logger.info("[VECTOR] sensing package loaded")

__all__ = []