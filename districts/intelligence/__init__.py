"""
VECTOR Intelligence District — social simulation, knowledge graphs, swarm intelligence.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from .social_sim_agent import SocialSimAgent

__all__ = ["SocialSimAgent"]

logger.info("[VECTOR][intelligence] Intelligence district loaded")
