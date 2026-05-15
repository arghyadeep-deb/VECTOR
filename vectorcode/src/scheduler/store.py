"""Scheduler store shim — re-exports from core.scheduler.store."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent.parent))
try:
    from core.scheduler.store import SchedulerStore
except ImportError:
    class SchedulerStore:
        """SchedulerStore stub — core.scheduler not found."""
        pass
