"""Shim: re-exports from core.mining.cpu_pearl."""
from loguru import logger
try:
    from core.mining.cpu_pearl import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
