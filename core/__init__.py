"""
V.E.C.T.O.R. core package.
Core systems: config, memory, inference, loop, voice, city, sensing, control, brain.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger

logger.info("[VECTOR] core package loaded")

__all__ = [
    "config",
    "memory",
    "inference",
    "loop",
    "voice",
    "city",
    "sensing",
    "control",
    "brain",
]