"""
V.E.C.T.O.R. memory package.
Semantic, episodic, causal, counterfactual memory systems.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger

from .episodic import EpisodicMemory
from .obsidian_sync import ObsidianSync

logger.info("[VECTOR] memory package loaded")

__all__ = [
    "EpisodicMemory",
    "ObsidianSync",
]