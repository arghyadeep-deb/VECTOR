"""
VECTOR Intelligence District — social simulation, knowledge graphs, swarm intelligence.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from .mirofish_agent import MiroFishAgent

__all__ = ["MiroFishAgent"]

logger.info("[VECTOR][intelligence] Intelligence district loaded")
