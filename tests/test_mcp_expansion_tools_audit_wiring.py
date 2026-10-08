"""Regression coverage for expansion-tool MCP security wiring."""

from __future__ import annotations

import asyncio
import json

import pytest

from core.mcp_tools.memory_safety import MEMORY_CLEAR_CONFIRM


def _run(awaitable):
    return asyncio.run(awaitable)


def _result_json(result) -> dict:
    for content in result.content:
        text = getattr(content, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"FastMCP result had no JSON text content: {result!r}")


def _tool_schema(server) -> list[dict]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        for tool in _run(server.list_tools())
    ]


def _isolated_memory(monkeypatch, tmp_path):
    import core.memory.episodic as episodic

    db_path = tmp_path / "expansion-audit.db"
    monkeypatch.setenv("VECTOR_DB_PATH", str(db_path))
    monkeypatch.setitem(episodic.CONFIG, "db_path", str(db_path))
    episodic.close_db_connection()
    episodic.EpisodicMemory()
    return episodic


def test_all_expansion_tools_register_with_unchanged_schemas(monkeypatch):
    pytest.importorskip("fastmcp")
    from fastmcp import FastMCP
    from core.mcp_tools import expansion

    audited = expansion._audited
    monkeypatch.setattr(expansion, "_audited", lambda mcp, _district: mcp)
    baseline = FastMCP("expansion-schema-baseline")
    expansion.add_expansion_tools(baseline)
    baseline_schema = _tool_schema(baseline)

    monkeypatch.setattr(expansion, "_audited", audited)
    secured = FastMCP("expansion-schema-secured")
    expansion.add_expansion_tools(secured)
    secured_schema = _tool_schema(secured)

    assert secured_schema == baseline_schema
    names = {tool["name"] for tool in secured_schema}
    assert len(names) == len(secured_schema)
    assert {
        "agent_list", "browser_open", "config_get", "doc_generate", "file_delete",
        "git_commit", "graph_stats", "hook_list", "memory_clear", "neural_status",
        "perf_profile", "security_scan", "swarm_status", "task_delete",
        "test_run", "worker_list",
    } <= names


def test_blocked_calls_do_not_execute_and_use_correct_districts(
    monkeypatch, tmp_path
):
    pytest.importorskip("fastmcp")
    from fastmcp import FastMCP
    from core.loop import task_queue
    from core.mcp_tools import security as mcp_security
    from core.mcp_tools.expansion import add_expansion_tools
    from core.mcp_tools.expansion_modules import files

    episodic = _isolated_memory(monkeypatch, tmp_path)
    memory = episodic.EpisodicMemory()
    memory.store(event_type="unit", content="must survive", source="test")

    target = tmp_path / "must-survive.txt"
    target.write_text("sentinel", encoding="utf-8")
    monkeypatch.setattr(files, "_ROOT", tmp_path)

    class TaskQueueSentinel:
        cancel_called = False

        def cancel(self, _task_id):
            self.cancel_called = True
            return True

    queue = TaskQueueSentinel()
    monkeypatch.setattr(task_queue, "get_task_queue", lambda: queue)

    security_calls = []

    def block(tool_name, district, params):
        security_calls.append((tool_name, district, params))
        return False

    monkeypatch.setattr(mcp_security, "mcp_secure_call", block)
    server = FastMCP("expansion-audit-blocking")
    add_expansion_tools(server)

    memory_result = _result_json(_run(server.call_tool(
        "memory_clear", {"confirm": MEMORY_CLEAR_CONFIRM}
    )))
    file_result = _result_json(_run(server.call_tool(
        "file_delete", {"file_path": target.name}
    )))
    task_result = _result_json(_run(server.call_tool(
        "task_delete", {"task_id": "sentinel-task"}
    )))

    assert memory_result == {"error": "blocked by MCP security rate limit"}
    assert file_result == {"error": "blocked by MCP security rate limit"}
    assert task_result == {"error": "blocked by MCP security rate limit"}
    with episodic.get_temp_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM episodic_memory")
        assert cursor.fetchone()[0] == 1
    assert target.read_text(encoding="utf-8") == "sentinel"
    assert queue.cancel_called is False
    assert security_calls == [
        ("memory_clear", "memory", {"confirm": MEMORY_CLEAR_CONFIRM}),
        ("file_delete", "files", {"file_path": target.name}),
        ("task_delete", "tasks", {"task_id": "sentinel-task"}),
    ]
    episodic.close_db_connection()


def test_allowed_call_executes_underlying_memory_clear(monkeypatch, tmp_path):
    pytest.importorskip("fastmcp")
    from fastmcp import FastMCP
    from core.mcp_tools import security as mcp_security
    from core.mcp_tools.expansion import add_expansion_tools

    episodic = _isolated_memory(monkeypatch, tmp_path)
    memory = episodic.EpisodicMemory()
    memory.store(event_type="unit", content="delete me", source="test")
    calls = []

    def allow(tool_name, district, params):
        calls.append((tool_name, district, params))
        return True

    monkeypatch.setattr(mcp_security, "mcp_secure_call", allow)
    server = FastMCP("expansion-audit-allowed")
    add_expansion_tools(server)
    result = _result_json(_run(server.call_tool(
        "memory_clear", {"confirm": MEMORY_CLEAR_CONFIRM}
    )))

    assert result["cleared"] is True
    with episodic.get_temp_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM episodic_memory")
        assert cursor.fetchone()[0] == 0
    assert calls == [
        ("memory_clear", "memory", {"confirm": MEMORY_CLEAR_CONFIRM})
    ]
    episodic.close_db_connection()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
