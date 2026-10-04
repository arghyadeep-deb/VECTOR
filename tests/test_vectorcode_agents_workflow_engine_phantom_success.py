"""Regression for vectorcode/src/agents/workflow_engine.py's WorkflowEngine.execute():

the top-level result always said {"status": "completed"} even when a step
raised and the loop broke early (the per-step entry correctly recorded
status="failed", but that never propagated to the workflow-level status) --
the "phantom success" bug class found 50+ times this cycle. Dormant today
(zero real callers anywhere in the repo, confirmed via grep), fixed anyway
per this cycle's established bar.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from agents.workflow_engine import WorkflowEngine


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
