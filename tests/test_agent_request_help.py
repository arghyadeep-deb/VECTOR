"""
Root-caused docs/repo_analysis/_MASTER_TODO.md §1b's other "noted-not-chased"
item: one WorkflowRunner.trigger_workflow AttributeError fallback log line.

Root cause: core/city/agent_base.py::request_agent_help() called
`WorkflowRunner().trigger_workflow(...)` — WorkflowRunner (core/loop/
workflow_runner.py) has never had a trigger_workflow method, only
`run(workflow, name)` returning a WorkflowResult, not a workflow_id. Every
call to request_agent_help() silently hit the except-Exception fallback
(confirmed: zero test coverage existed for this method before this pass).

Fixed: look the target agent up directly via the registry by name and
call its run() — simpler and more correct than building a single-task
WorkflowRunner DAG for what is fundamentally a direct agent-to-agent
request, and avoids inventing a workflow_id concept the runner never had.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_agent(name):
    from core.city.agent_base import AgentBase

    class _TestAgent(AgentBase):
        async def run(self, task):
            return {"status": "ok", "agent": self.name, "task": task}

    return _TestAgent(agent_id=f"id-{name}", name=name, district="test")


def test_request_agent_help_dispatches_to_real_agent_by_name(monkeypatch):
    from core.city.agent_registry import get_registry

    helper = _make_agent("HelperAgent")
    requester = _make_agent("RequesterAgent")
    registry = get_registry()
    registry.register(helper)

    async def _run():
        # 2026-09-26: help now goes through the governed A2A bus, so it needs a real task type ("respond" is GREEN).
        return await requester.request_agent_help("HelperAgent", {"type": "respond", "params": {"do": "research"}})

    result = asyncio.run(_run())
    assert result["status"] == "requested"
    assert result["target_agent"] == "HelperAgent"
    assert result["result"]["agent"] == "HelperAgent"
    assert result["result"]["task"]["params"] == {"do": "research"}
    assert result["a2a"]["delivered"] is True


def test_request_agent_help_without_a_task_type_is_refused_not_forwarded():
    requester = _make_agent("RequesterNoType")
    result = asyncio.run(requester.request_agent_help("HelperAgent", {"do": "research"}))
    assert result["status"] == "unavailable" and "task_type" in result["error"]


def test_request_agent_help_no_longer_bypasses_the_permission_tiers():
    """It used to call target.run() directly, so a RED task type ran with no approval at all."""
    from core.city.agent_registry import get_registry

    ran = []

    from core.city.agent_base import AgentBase

    class _Deleter(AgentBase):
        async def run(self, task):
            ran.append(task)
            return {"status": "ok"}

    victim = _Deleter(agent_id="id-deleter", name="DeleterAgent", district="test")
    get_registry().register(victim)
    requester = _make_agent("RequesterRed")
    result = asyncio.run(requester.request_agent_help("DeleterAgent", {"type": "delete_files", "params": {"path": "/tmp/x"}}))
    assert result["status"] == "unavailable"
    assert result["a2a"]["status"] == "requires_approval"
    assert ran == [], "a RED action must never reach the target agent through A2A"


def test_request_agent_help_returns_unavailable_when_target_not_found():
    from core.city.agent_base import AgentBase

    class _TestAgent(AgentBase):
        async def run(self, task):
            return {"status": "ok"}

    requester = _TestAgent(agent_id="id-x", name="Requester2", district="test")

    async def _run():
        return await requester.request_agent_help("NonexistentAgent12345", {"do": "x"})

    result = asyncio.run(_run())
    assert result["status"] == "unavailable"
    assert result["target_agent"] == "NonexistentAgent12345"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
