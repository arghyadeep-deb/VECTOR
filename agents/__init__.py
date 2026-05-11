"""
V.E.C.T.O.R. agents package.
All VECTOR agents and districts.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

logger.info("[VECTOR] agents package loaded")

__all__ = []