"""Scheduler shim - re-exports from core.scheduler.scheduler."""
try:
    from core.scheduler.scheduler import TaskScheduler, ScheduledTask
except ImportError as exc:
    _SCHEDULER_IMPORT_ERROR = exc

    class TaskScheduler:
        """Unavailable scheduler shim."""

        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "core.scheduler.scheduler.TaskScheduler is unavailable"
            ) from _SCHEDULER_IMPORT_ERROR

    class ScheduledTask:
        """Unavailable scheduled task shim."""

        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "core.scheduler.scheduler.ScheduledTask is unavailable"
            ) from _SCHEDULER_IMPORT_ERROR
