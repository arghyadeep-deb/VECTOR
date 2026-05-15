"""Scheduler shim — delegates to core.scheduler."""
try:
    from core.scheduler import *
except ImportError:
    pass
