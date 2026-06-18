"""
V.E.C.T.O.R. core package.
Core systems: config, memory, inference, loop, voice, city, sensing, control, brain.
"""
import sys
from loguru import logger

logger.info("[VECTOR] core package loaded")

for _pkg in ("mcp", "fastmcp"):
    try:
        __import__(_pkg)
    except ImportError:
        __import__("logging").getLogger(__name__).warning("optional dep import failed", exc_info=True)
if "mcp" in sys.modules and not hasattr(sys.modules["mcp"], "server"):
    logger.warning("[VECTOR] mcp module may be shadowed by vectorcode/src/mcp/")

__all__ = [
    "config", "memory", "inference", "loop", "voice",
    "city", "sensing", "control", "brain",
]