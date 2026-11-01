"""Scheduler shim — delegates to core.scheduler."""

from loguru import logger
try:
    from core.scheduler import *
except ImportError:
    logger.opt(exception=True).debug("[VECTOR][scheduler] core scheduler unavailable")
