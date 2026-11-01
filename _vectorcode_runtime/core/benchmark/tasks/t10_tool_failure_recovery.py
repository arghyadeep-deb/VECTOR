"""T10 — Tool Failure Recovery: action execution failure handled gracefully.

Create an action that would fail during execution. Verify PermissionGateway
catches the failure and returns a proper GatewayResult without crashing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult


class ToolFailureRecoveryTask(BenchmarkTask):
    task_id = "T10"
    category = "tool_failure_recovery"
    required_capability = "PermissionGateway handles execution failures gracefully without crashing"
    expected_behavior = "Failed action returns GatewayResult with approved=False, no exception propagates"

    def run(self, state) -> TaskResult:
        from core.loop.permission_gateway import PermissionGateway, Action, GatewayResult

        gw = PermissionGateway()

        # An action that targets a nonexistent handler — will fail at execution
        action = Action(
            action_type="nonexistent_tool_xyz",
            params={"data": "test"},
            proposed_by="benchmark_t10",
            priority="normal",
        )

        # Classify first — should be UNKNOWN or some level
        level = gw.classify(action.action_type)

        # Try execute — should NOT crash, should return a result
        result = None
        execution_failed = False
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(gw.execute(action))
            loop.close()
        except Exception as e:
            execution_failed = True
            error_msg = str(e)

        if execution_failed:
            return self._failure(
                actual=f"Gateway.execute() crashed with: {error_msg}",
                outcome="Gateway did not handle failure gracefully",
                incorrect_actions=1,
            )

        # Result should exist and indicate failure (not approved or not executed)
        if result is not None:
            is_failure_result = (
                not result.approved or not result.executed
                or result.level in ("FORBIDDEN", "UNKNOWN")
            )
            if is_failure_result:
                return self._success(
                    actual=(
                        f"Action 'nonexistent_tool_xyz' classified as '{level}', "
                        f"execute returned: approved={result.approved}, "
                        f"executed={result.executed}, level={result.level}. "
                        f"Gateway handled gracefully."
                    ),
                    outcome="Tool failure recovery verified — no crash, proper result",
                    details={
                        "classification": level,
                        "approved": result.approved,
                        "executed": result.executed,
                        "level": result.level,
                    },
                    recovery_attempts=1,
                )
            else:
                return self._failure(
                    actual=f"Unexpected result: approved={result.approved}, executed={result.executed}",
                    outcome="Gateway result inconsistent for failing action",
                )
        else:
            return self._failure(
                actual="execute() returned None without raising",
                outcome="Gateway returned no result",
            )


TASK_CLASS = ToolFailureRecoveryTask
