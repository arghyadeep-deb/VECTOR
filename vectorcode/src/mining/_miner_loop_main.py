"""Shim: re-exports from core.mining._miner_loop_main."""
from loguru import logger
try:
    from core.mining._miner_loop_main import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
