"""Shim: re-exports from core.mining.apple_mps_pearl."""
from loguru import logger
try:
    from core.mining.apple_mps_pearl import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
