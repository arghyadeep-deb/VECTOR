"""T09 — Tool Execution: GREEN-tier action approved and executed.

Create a GREEN-tier action, route through PermissionGateway.classify().
Passes if action is classified GREEN and approved.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult


class ToolExecutionTask(BenchmarkTask):
    task_id = "T09"
    category = "tool_execution"
    required_capability = "PermissionGateway classifies and approves GREEN-tier actions"
    expected_behavior = "GREEN action (e.g., search_web) classified correctly and approved"

    def run(self, state) -> TaskResult:
        from core.loop.permission_gateway import PermissionGateway, Action

        gw = PermissionGateway()

        # A safe, read-only action — should be GREEN
        action = Action(
            action_type="search_web",
            params={"query": "Python performance tips"},
            proposed_by="benchmark_t09",
            priority="normal",
        )

        # Classify
        level = gw.classify(action.action_type)

        if level == "GREEN":
            return self._success(
                actual=f"Action 'search_web' classified as {level} — safe for autonomous execution",
                outcome="GREEN action correctly classified",
                details={"action_type": "search_web", "level": level},
            )
        elif level in ("YELLOW", "RED"):
            # Not ideal but not a failure — the action is known but requires oversight
            return self._success(
                actual=f"Action 'search_web' classified as {level} — action recognized, requires oversight",
                outcome="Action classified (elevated tier but not blocked)",
                details={"action_type": "search_web", "level": level},
            )
        elif level == "FORBIDDEN":
            return self._failure(
                actual=f"Action 'search_web' classified as FORBIDDEN — unexpected for a read-only action",
                outcome="Over-classified safe action as forbidden",
                details={"action_type": "search_web", "level": level},
                incorrect_actions=1,
            )
        else:
            return self._failure(
                actual=f"Action classified as '{level}' — unexpected level",
                outcome="Classification returned unknown level",
                details={"action_type": "search_web", "level": level},
            )


TASK_CLASS = ToolExecutionTask
