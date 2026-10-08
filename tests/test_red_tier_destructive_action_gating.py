"""Regression coverage for OD-22/OD-24/OD-25 destructive-action gates."""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.api.schemas import AgentAwardRequest
from core.loop.permission_gateway import GatewayResult, PermissionGateway


class _FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, fn=None, **_kwargs):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator(fn) if fn else decorator


class _Gateway:
    def __init__(self, approved: bool) -> None:
        self.approved = approved
        self.calls: list[tuple[str, dict, str]] = []

    async def evaluate_external(self, action_type: str, params: dict, source: str):
        self.calls.append((action_type, params, source))
        return GatewayResult(
            approved=self.approved,
            level="RED",
            executed=False,
            result={},
            reason="owner rejected" if not self.approved else "owner approved",
        )


def _install_gateway(monkeypatch, approved: bool) -> _Gateway:
    from core.loop.autonomous_loop import AutonomousLoop

    gateway = _Gateway(approved)
    loop = SimpleNamespace(_get_gateway=lambda: gateway)
    monkeypatch.setattr(AutonomousLoop, "get_instance", staticmethod(lambda: loop))
    return gateway


async def _call(tool, *args, **kwargs) -> dict:
    result = tool(*args, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return json.loads(result)


def test_all_new_action_types_are_red() -> None:
    gateway = PermissionGateway()
    action_types = {
        "memory_clear",
        "file_delete",
        "task_delete",
        "config_reset",
        "worker_reset",
        "agent_hp_award",
        "memory_restore",
    }
    assert {name: gateway._classify(name) for name in action_types} == {
        name: "RED" for name in action_types
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_memory_clear_gate_controls_real_delete(monkeypatch, tmp_path, approved):
    import core.memory.episodic as episodic
    from core.mcp_tools.expansion_modules import memory as memory_tools
    from core.mcp_tools.memory_safety import MEMORY_CLEAR_CONFIRM

    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("VECTOR_DB_PATH", str(db_path))
    monkeypatch.setitem(episodic.CONFIG, "db_path", str(db_path))
    episodic.close_db_connection()
    memory = episodic.EpisodicMemory()
    memory.store(event_type="test", content="must survive denial", source="test")

    mcp = _FakeMCP()
    memory_tools.add_memory_tools(mcp)
    gateway = _install_gateway(monkeypatch, approved)
    try:
        result = await _call(mcp.tools["memory_clear"], MEMORY_CLEAR_CONFIRM)
        with episodic.get_temp_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM episodic_memory")
            remaining = cursor.fetchone()[0]
    finally:
        episodic.close_db_connection()

    assert gateway.calls == [
        ("memory_clear", {"confirm": MEMORY_CLEAR_CONFIRM}, "mcp_memory")
    ]
    assert remaining == (0 if approved else 1)
    assert result.get("cleared") is approved
    if not approved:
        assert result["status"] == "blocked"
        assert result["level"] == "RED"


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_file_delete_gate_controls_real_unlink(monkeypatch, tmp_path, approved):
    from core.loop.permission_gateway import set_coding_grant
    from core.mcp_tools.expansion_modules import files as file_tools

    victim = tmp_path / "victim.txt"
    victim.write_text("keep on denial", encoding="utf-8")
    monkeypatch.setattr(file_tools, "_ROOT", tmp_path)
    mcp = _FakeMCP()
    file_tools.add_file_tools(mcp)
    gateway = _install_gateway(monkeypatch, approved)

    set_coding_grant(True)
    try:
        result = await _call(mcp.tools["file_delete"], "victim.txt")
    finally:
        set_coding_grant(False)

    assert gateway.calls == [
        ("file_delete", {"file_path": "victim.txt"}, "mcp_files")
    ]
    assert victim.exists() is (not approved)
    assert result.get("ok") is approved
    if not approved:
        assert result["status"] == "blocked"


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_agent_award_gate_controls_hp_change(monkeypatch, approved):
    from core.api.routers import agents

    gateway = _install_gateway(monkeypatch, approved)
    state = {"hp": 500, "calls": 0}

    def apply_award(agent_id: str, points: int, reason: str) -> dict:
        state["calls"] += 1
        state["hp"] += points
        return {
            "status": "ok",
            "agent": {"id": agent_id, "health_points": state["hp"]},
            "award": {"new_hp": state["hp"], "model_changed": False, "reason": reason},
        }

    monkeypatch.setattr(agents, "award_agent", apply_award)
    body = AgentAwardRequest(agent_id="agent-1", points=75, reason="owner decision")

    if approved:
        response = await agents.award_agent_endpoint(body)
        assert response.new_hp == 575
        assert state == {"hp": 575, "calls": 1}
    else:
        with pytest.raises(HTTPException) as exc_info:
            await agents.award_agent_endpoint(body)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["status"] == "blocked"
        assert state == {"hp": 500, "calls": 0}

    assert gateway.calls == [(
        "agent_hp_award",
        {"agent_id": "agent-1", "points": 75, "reason": "owner decision"},
        "api_agents_award",
    )]


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
async def test_memory_restore_gate_controls_restore(monkeypatch, approved):
    from core.api.routers import memory
    import core.memory.multi_db_manager as manager_module

    gateway = _install_gateway(monkeypatch, approved)
    state = {"rows": ["existing"], "calls": 0}

    class Manager:
        def restore(self, backup_path: str, overwrite: bool = False) -> dict:
            state["calls"] += 1
            if overwrite:
                state["rows"].clear()
            state["rows"].append(Path(backup_path).name)
            return {"tables_restored": 1, "rows_restored": 1}

    monkeypatch.setattr(manager_module, "get_manager", lambda: Manager())
    result = await memory.restore_memory("backups/memory.json", overwrite=True)

    assert gateway.calls == [(
        "memory_restore",
        {"backup_path": "backups/memory.json", "overwrite": True},
        "api_memory_restore",
    )]
    if approved:
        assert result["status"] == "ok"
        assert state == {"rows": ["memory.json"], "calls": 1}
    else:
        assert result == {
            "status": "blocked",
            "source": "api_memory_restore",
            "reason": "owner rejected",
            "level": "RED",
        }
        assert state == {"rows": ["existing"], "calls": 0}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
