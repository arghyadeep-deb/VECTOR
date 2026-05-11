"""
V.E.C.T.O.R. brain package.
Synthesis, self-evolution, council, red-team, hypothesis engine.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

logger.info("[VECTOR] brain package loaded")

__all__ = []