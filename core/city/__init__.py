"""
V.E.C.T.O.R. city package.
Agent base, evolution engine, point system, task router, meta-cognition.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

from .agent_base import AgentBase

logger.info("[VECTOR] city package loaded")

__all__ = [
    "AgentBase",
]