"""Scheduler shim — delegates to core.scheduler."""
try:
    from core.scheduler import *
except ImportError:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
