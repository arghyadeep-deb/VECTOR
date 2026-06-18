"""Scheduler shim — delegates to core.scheduler."""

from loguru import logger
try:
    from core.scheduler import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
