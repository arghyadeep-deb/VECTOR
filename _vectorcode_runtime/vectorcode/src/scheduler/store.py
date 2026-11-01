"""Scheduler store shim — re-exports from core.scheduler.store."""
try:
    from core.scheduler.store import SchedulerStore
except ImportError:
    class SchedulerStore:
        """SchedulerStore stub — core.scheduler not found."""
        pass
