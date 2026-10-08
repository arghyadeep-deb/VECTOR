"""Regression for vectorcode/src/agents/workflow_engine.py's WorkflowEngine.execute():

the top-level result always said {"status": "completed"} even when a step
raised and the loop broke early (the per-step entry correctly recorded
status="failed", but that never propagated to the workflow-level status) --
the "phantom success" bug class found 50+ times this cycle. Dormant today
(zero real callers anywhere in the repo, confirmed via grep), fixed anyway
per this cycle's established bar.
"""
import asyncio
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from agents.workflow_engine import WorkflowEngine


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _RecordingGateway:
    def __init__(self, approved: bool, reason: str = "Owner decision"):
        self.approved = approved
        self.reason = reason
        self.calls = []

    async def evaluate_external(self, action_type, params, source):
        self.calls.append((action_type, params, source))
        return SimpleNamespace(
            approved=self.approved,
            level="RED",
            reason=self.reason,
        )


def test_execute_reports_failed_when_a_step_raises():
    engine = WorkflowEngine()
    workflow = {
        "id": "wf-1",
        "steps": [
            {"action": "delay", "seconds": 0},
            {"action": "bash", "command": "this-binary-does-not-exist-xyz"},
        ],
    }
    result = _run(engine.execute(workflow))
    assert result["status"] == "failed"
    assert engine._workflows["wf-1"]["status"] == "failed"


def test_execute_reports_completed_when_all_steps_succeed():
    engine = WorkflowEngine()
    workflow = {"id": "wf-2", "steps": [{"action": "delay", "seconds": 0}]}
    result = _run(engine.execute(workflow))
    assert result["status"] == "completed"


def test_bash_denial_blocks_without_starting_subprocess(monkeypatch):
    gateway = _RecordingGateway(False, "Rejected by owner")

    def forbidden_run(*args, **kwargs):
        raise AssertionError("subprocess must not run after gateway denial")

    monkeypatch.setattr(subprocess, "run", forbidden_run)
    result = _run(
        WorkflowEngine(permission_gateway=gateway).execute(
            {"id": "denied", "steps": [{"action": "bash", "command": [sys.executable, "-c", "print('no')"]}]}
        )
    )

    assert result["status"] == "blocked"
    assert result["results"] == [
        {"step": 0, "status": "blocked", "reason": "Rejected by owner"}
    ]
    assert gateway.calls[0][0] == "workflow_bash_execute"
    assert gateway.calls[0][2] == "workflow_engine"


def test_approved_bash_preserves_stdout_result_shape(monkeypatch):
    gateway = _RecordingGateway(True)
    monkeypatch.setenv("OD56_SENSITIVE_SENTINEL", "must-not-leak")
    result = _run(
        WorkflowEngine(permission_gateway=gateway).execute(
            {
                "id": "approved",
                "steps": [{
                    "action": "bash",
                    "command": [
                        sys.executable,
                        "-c",
                        "import os; assert 'OD56_SENSITIVE_SENTINEL' not in os.environ; print('safe-output')",
                    ],
                }],
            }
        )
    )

    assert result == {
        "id": "approved",
        "status": "completed",
        "results": [{"step": 0, "status": "ok", "result": "safe-output\n"}],
    }


def test_bash_rejects_cwd_outside_runtime_roots(tmp_path):
    gateway = _RecordingGateway(True)
    outside = tmp_path.resolve()
    result = _run(
        WorkflowEngine(permission_gateway=gateway).execute(
            {"id": "outside", "steps": [{"action": "bash", "command": [sys.executable, "-c", "print('no')"], "cwd": str(outside)}]}
        )
    )

    assert result["status"] == "failed"
    assert "outside allowed roots" in result["results"][0]["error"]
    assert gateway.calls == []


def test_bash_rejects_executable_not_in_allowlist():
    gateway = _RecordingGateway(True)
    result = _run(
        WorkflowEngine(permission_gateway=gateway).execute(
            {"id": "blocked-executable", "steps": [{"action": "bash", "command": ["curl", "https://example.invalid"]}]}
        )
    )

    assert result["status"] == "failed"
    assert "not allowlisted" in result["results"][0]["error"]
    assert gateway.calls == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
