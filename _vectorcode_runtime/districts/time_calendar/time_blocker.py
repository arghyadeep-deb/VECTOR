import sys
import uuid
import datetime

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


# Urgency → minimum window required to execute
_URGENCY_WINDOW_MAP = {
    "critical":   {"peak", "low", "moderate", "critical_only", "off"},  # always execute
    "high":       {"peak", "moderate"},
    "medium":     {"peak"},
    "low":        set(),  # never execute during low/off — queue only
}

# Human-readable recommended actions per window
_WINDOW_RECOMMENDATIONS = {
    "peak":          "work",
    "low":           "rest",
    "moderate":      "review",
    "critical_only": "critical_tasks_only",
    "off":           "rest",
}


class TimeBlocker(AgentBase):
    """
    Routes tasks to correct energy windows.
    Queues tasks during low/off windows so they run at the right time.

    Energy windows (mirrors DeadlineManager):
      peak          10AM-1PM  — hardest tasks
      low           2PM-4PM   — light tasks, rest preferred
      moderate      7PM-10PM  — review + planning
      critical_only 10PM+     — only critical
      off           0AM-10AM  — rest, queue everything
    """

    ENERGY_WINDOWS = [
        (10, 13, "peak"),
        (14, 16, "low"),
        (19, 22, "moderate"),
        (22, 24, "critical_only"),
        (0, 10, "off"),
    ]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "TimeBlocker", "time_calendar")
        self.capabilities = ["calendar", "peak", "schedule", "time", "time_block"]
        if ghost:
            self.inherit_ghost(ghost)
        self._queue: list[dict] = []
        logger.info("[VECTOR][time_blocker] TimeBlocker initialized")

    def _get_current_window(self) -> str:
        hour = datetime.datetime.now().hour
        for start, end, label in self.ENERGY_WINDOWS:
            if start <= hour < end:
                return label
        return "off"

    def should_execute_now(self, task_urgency: str) -> bool:
        """
        Decide if a task with the given urgency should run now.

        critical → always True
        high     → only in peak or moderate windows
        medium   → only in peak window
        low      → never during off or low windows (queue it)
        """
        urgency = task_urgency.lower().strip()
        if urgency == "critical":
            return True
        current_window = self._get_current_window()
        allowed_windows = _URGENCY_WINDOW_MAP.get(urgency, set())
        return current_window in allowed_windows

    def queue_task(self, task: dict) -> None:
        """
        Add task to the deferred queue with a timestamp.
        Task dict should include at minimum: {name, urgency}.
        """
        entry = {
            **task,
            "queued_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "window_at_queue": self._get_current_window(),
        }
        self._queue.append(entry)
        logger.info(
            f"[VECTOR][time_blocker] Queued task '{task.get('name', 'unnamed')}' "
            f"(urgency={task.get('urgency', 'unknown')}) — window={entry['window_at_queue']}"
        )
        self.award_points(5, "task_queued")

    def get_queued_for_window(self, window: str) -> list[dict]:
        """
        Return tasks from the queue that are appropriate for the given energy window.
        Clears returned tasks from the queue (they are now ready to execute).
        """
        result = []
        remaining = []
        for task in self._queue:
            urgency = task.get("urgency", "low").lower()
            allowed = _URGENCY_WINDOW_MAP.get(urgency, set())
            if window in allowed:
                result.append(task)
            else:
                remaining.append(task)
        if result:
            self._queue = remaining
            logger.info(
                f"[VECTOR][time_blocker] Released {len(result)} tasks for window={window}"
            )
            self.award_points(len(result) * 5, "tasks_released_for_window")
        return result

    def drain_critical(self) -> list[dict]:
        """Return and remove all critical-urgency tasks regardless of window."""
        critical = [t for t in self._queue if t.get("urgency", "").lower() == "critical"]
        self._queue = [t for t in self._queue if t.get("urgency", "").lower() != "critical"]
        if critical:
            logger.info(f"[VECTOR][time_blocker] Drained {len(critical)} critical tasks")
        return critical

    def get_time_context(self) -> dict:
        """
        Return compact time/energy context for session hydration and observers.
        """
        current_window = self._get_current_window()
        recommendation = _WINDOW_RECOMMENDATIONS.get(current_window, "rest")
        pending_by_urgency: dict[str, int] = {}
        for task in self._queue:
            u = task.get("urgency", "unknown")
            pending_by_urgency[u] = pending_by_urgency.get(u, 0) + 1

        return {
            "current_window": current_window,
            "queued_count": len(self._queue),
            "pending_by_urgency": pending_by_urgency,
            "recommended_action": recommendation,
            "current_hour": datetime.datetime.now().hour,
        }

    def get_queue_snapshot(self) -> list[dict]:
        """Return a copy of all queued tasks without removing them."""
        return list(self._queue)


    async def run(self, task: dict) -> dict:
        ctx = self.get_time_context()
        snapshot = self.get_queue_snapshot()
        # 2026-07-22: real data was always computed here (ctx, snapshot) but
        # never surfaced as narrative text — "time_context"/"queue" aren't
        # among the keys avatar/avatar_voice.py::_extract_text() checks, so
        # this rendered as a bare "Task completed — status: ok." stub
        # despite genuinely useful content being present (KNOWN_ISSUES.md
        # #1 pattern). Added a `response` summary built from that same data.
        if snapshot:
            queue_line = f"{ctx['queued_count']} task(s) queued ({', '.join(f'{u}:{n}' for u, n in ctx['pending_by_urgency'].items())})."
        else:
            queue_line = "No tasks queued."
        response = (
            f"Current energy window: {ctx['current_window']} (hour {ctx['current_hour']}) — "
            f"recommended action: {ctx['recommended_action']}. {queue_line}"
        )
        return {"status": "ok", "response": response, "time_context": ctx, "queue": snapshot}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    blocker = TimeBlocker()

    # Critical always runs
    assert blocker.should_execute_now("critical") is True, "critical should always execute"

    # Queue some tasks
    blocker.queue_task({"name": "write tests", "urgency": "medium"})
    blocker.queue_task({"name": "reply slack", "urgency": "low"})
    blocker.queue_task({"name": "fix bug", "urgency": "critical"})

    context = blocker.get_time_context()
    assert isinstance(context, dict), "get_time_context must return dict"
    assert "current_window" in context
    assert "queued_count" in context
    assert "recommended_action" in context
    assert context["queued_count"] == 3

    # Drain critical
    critical_tasks = blocker.drain_critical()
    assert len(critical_tasks) == 1
    assert context["current_window"] in ("peak", "low", "moderate", "critical_only", "off")

    print(
        f"✅ time_blocker OK — window={context['current_window']}, "
        f"queued={context['queued_count']}, "
        f"recommendation={context['recommended_action']}"
    )
