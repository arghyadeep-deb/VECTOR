"""Shim: re-exports from core.mining.apple_mps_pearl."""
from loguru import logger
try:
    from core.mining.apple_mps_pearl import *
except ImportError:
    logger.opt(exception=True).debug("[VECTOR][mining] Apple MPS provider unavailable")
