"""Shim: re-exports from core.mining.vllm_pearl."""
from loguru import logger
try:
    from core.mining.vllm_pearl import *
except ImportError:
    logger.opt(exception=True).debug("[VECTOR][mining] vLLM provider unavailable")
