"""Scheduler shim — re-exports from core.scheduler.scheduler."""
import sys, os
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent.parent))
try:
    from core.scheduler.scheduler import TaskScheduler, ScheduledTask
except ImportError:
    class TaskScheduler:
        """TaskScheduler stub — core.scheduler not found."""
        pass
    class ScheduledTask:
        """ScheduledTask stub."""
        pass
