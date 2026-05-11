"""
V.E.C.T.O.R. OpenCLI package.
CLI tool registry for V.E.C.T.O.R. commands.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

from . import tool_registry

logger.info("[VECTOR] opencli package loaded")

__all__ = ["tool_registry"]