"""
V.E.C.T.O.R. control package.
Control loops, autonomous operation, security guard.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

logger.info("[VECTOR] control package loaded")

__all__ = []