"""
V.E.C.T.O.R. memory package.
Semantic, episodic, causal, counterfactual memory systems.
"""
from loguru import logger

from .episodic import EpisodicMemory
from .obsidian_sync import ObsidianSync
from .unified import UnifiedMemory, get_memory

logger.info("[VECTOR] memory package loaded")

__all__ = [
    "EpisodicMemory",
    "ObsidianSync",
    "UnifiedMemory",
    "get_memory",
]