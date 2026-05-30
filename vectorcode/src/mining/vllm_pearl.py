"""Shim: re-exports from core.mining.vllm_pearl."""
from loguru import logger
try:
    from core.mining.vllm_pearl import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
