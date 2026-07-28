"""Regression coverage for KNOWN_ISSUES.md #1's stub-output bug in
TimeBlocker.run() — real data (energy window, queue) was always computed
but never surfaced under a key avatar/avatar_voice.py::_extract_text()
checks. Fixed 2026-07-22 (live-verified at the time) but never got an
automated test.
"""
from __future__ import annotations

import asyncio

from districts.time_calendar.time_blocker import TimeBlocker

_NARRATIVE_KEYS = ("response", "result", "content", "message", "text", "output")


class TestTimeBlockerRunNotAStub:
    def test_run_populates_a_narrative_key(self):
        blocker = TimeBlocker()
        result = asyncio.run(blocker.run({}))

        assert any(result.get(k) for k in _NARRATIVE_KEYS), (
            f"run() returned no narrative key from {_NARRATIVE_KEYS} — "
            f"this would render as the generic stub. Got: {result}"
        )
        assert "Current energy window" in result["response"]

    def test_run_reflects_empty_queue(self):
        blocker = TimeBlocker()
        result = asyncio.run(blocker.run({}))
        assert "No tasks queued" in result["response"]

    def test_run_reflects_queued_tasks(self):
        blocker = TimeBlocker()
        blocker.queue_task({"name": "write tests", "urgency": "medium"})
        blocker.queue_task({"name": "fix bug", "urgency": "critical"})

        result = asyncio.run(blocker.run({}))

        assert "task(s) queued" in result["response"]
        assert result["time_context"]["queued_count"] == 2
        assert len(result["queue"]) == 2

    def test_run_still_carries_structured_fields_too(self):
        """The narrative-key fix shouldn't have dropped the pre-existing structured data."""
        blocker = TimeBlocker()
        result = asyncio.run(blocker.run({}))
        assert "time_context" in result
        assert "current_window" in result["time_context"]


if __name__ == "__main__":
    async def _smoke():
        blocker = TimeBlocker()
        r = await blocker.run({})
        assert r.get("response"), "time_blocker stub regression!"
        print("response:", r["response"])

    asyncio.run(_smoke())
    print("test_time_blocker_regression.py OK")
