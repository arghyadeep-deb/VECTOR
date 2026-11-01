"""Shim: re-exports from core.mining._miner_loop_main."""
from loguru import logger
try:
    from core.mining._miner_loop_main import *
except ImportError:
    logger.opt(exception=True).debug("[VECTOR][mining] optional miner loop unavailable")
