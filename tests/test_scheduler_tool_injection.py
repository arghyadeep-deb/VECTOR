"""Regression tests for production scheduler dependency injection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_system_builder_injects_scheduler_into_all_scheduler_tools():
    from core.scheduler.tools import (
        CancelScheduledTaskTool,
        ListScheduledTasksTool,
        PauseScheduledTaskTool,
        ResumeScheduledTaskTool,
        ScheduleTaskTool,
    )
    from vectorcode.src.vc_system.builder import SystemBuilder

    tools = [
        ScheduleTaskTool(),
        ListScheduledTasksTool(),
        PauseScheduledTaskTool(),
        ResumeScheduledTaskTool(),
        CancelScheduledTaskTool(),
    ]
    scheduler = SimpleNamespace(name="runtime-scheduler")

    SystemBuilder._inject_scheduler_deps(tools, scheduler)

    assert all(tool._scheduler is scheduler for tool in tools)


def test_scheduler_tool_returns_success_after_injection():
    from core.scheduler.tools import ScheduleTaskTool
    from vectorcode.src.vc_system.builder import SystemBuilder

    class Scheduler:
        def create_task(self, **kwargs):
            return SimpleNamespace(id="task-1", next_run="later", status="active")

    tool = ScheduleTaskTool()
    SystemBuilder._inject_scheduler_deps([tool], Scheduler())

    result = tool.execute(
        prompt="check status",
        schedule_type="once",
        schedule_value="2026-10-10T12:00:00+00:00",
    )

    assert result.success is True
    assert "task-1" in result.content


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
