"""
V.E.C.T.O.R. districts package.
All VECTOR district agents.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from loguru import logger

logger.info("[VECTOR] districts package loaded")

__all__ = []