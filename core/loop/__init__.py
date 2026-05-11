"""
V.E.C.T.O.R. loop package.
Autonomous loop: observe, think, act, reflect, sync.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

logger.info("[VECTOR] loop package loaded")

__all__ = []