"""Scheduler shim — re-exports from core.scheduler.scheduler."""
import sys, os
try:
    from core.scheduler.scheduler import TaskScheduler, ScheduledTask
except ImportError:
    class TaskScheduler:
        """TaskScheduler stub — core.scheduler not found."""
        pass
    class ScheduledTask:
        """ScheduledTask stub."""
        pass
