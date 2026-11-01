"""
V.E.C.T.O.R. city package.
Agent base, evolution engine, point system, task router, meta-cognition.
"""
from loguru import logger

from .agent_base import AgentBase

logger.info("[VECTOR] city package loaded")

__all__ = [
    "AgentBase",
]