"""Regression coverage for the ACP/memory correctness audit."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType


SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _install_acp_schema_stub(monkeypatch):
    """Provide the small legacy ACP schema surface these modules import."""
    import acp

    class SchemaValue:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    schema = ModuleType("acp.schema")
    for name in (
        "AllowedOutcome",
        "PermissionOption",
        "ToolCallLocation",
        "ToolCallStart",
        "ToolCallProgress",
    ):
        setattr(schema, name, type(name, (SchemaValue,), {}))
    schema.ToolKind = str
    monkeypatch.setitem(sys.modules, "acp.schema", schema)
    monkeypatch.setattr(acp, "Client", object, raising=False)
    monkeypatch.setattr(acp, "start_tool_call", lambda *args, **kwargs: object(), raising=False)
    for module_name in ("acp_adapter.permissions", "acp_adapter.tools", "acp_adapter.events"):
        monkeypatch.delitem(sys.modules, module_name, raising=False)
    return schema


async def test_sqlite_backend_store_uses_a_real_timestamp(tmp_path: Path) -> None:
    from memory.backends import SQLiteBackend

    backend = SQLiteBackend(tmp_path / "memory.db")
    before = time.time()
    await backend.store("test", "key", {"ok": True})
    row = backend._conn.execute(
        "SELECT created_at, updated_at FROM memories WHERE namespace=? AND key=?",
        ("test", "key"),
    ).fetchone()
    assert row is not None
    assert row[0] >= before
    assert row[1] >= before
    backend._conn.close()


async def test_permission_callback_denies_unknown_allowed_option(monkeypatch) -> None:
    import asyncio
    schema = _install_acp_schema_stub(monkeypatch)
    from acp_adapter.permissions import make_approval_callback

    async def request_permission(**_kwargs):
        return SimpleNamespace(outcome=schema.AllowedOutcome(option_id="not-offered"))

    callback = make_approval_callback(
        request_permission, asyncio.get_running_loop(), "session", timeout=1
    )
    result = await asyncio.to_thread(callback, "command", "description")
    assert result == "deny"


def test_step_callback_preserves_falsy_tool_result(monkeypatch) -> None:
    from collections import deque
    _install_acp_schema_stub(monkeypatch)
    from acp_adapter import events

    captured = []
    monkeypatch.setattr(events, "_send_update", lambda *_args: captured.append(_args[-1]))
    monkeypatch.setattr(
        events,
        "build_tool_complete",
        lambda *_args, **kwargs: kwargs,
    )
    callback = events.make_step_cb(
        object(), "session", object(), {"tool": deque(["tc-1"])}, {"tc-1": {}}
    )
    callback(1, [{"name": "tool", "result": 0, "output": "wrong"}])
    assert captured == [{"result": "0", "function_args": None, "snapshot": None}]


def test_swarm_retention_counts_all_tables_and_preserves_epoch(tmp_path: Path, monkeypatch) -> None:
    import memory.swarm_db as swarm_db

    monkeypatch.setattr(swarm_db, "_DB_ROOT", tmp_path)
    db = swarm_db.SwarmDatabase("audit")
    db.record_task("old", "task", "agent", outcome="completed", started_at=0)
    assert db.get_task("old")["started_at"] == 0
    db._conn.execute("UPDATE tasks SET completed_at = 0 WHERE id = 'old'")
    db._conn.execute(
        "INSERT INTO metrics (ts, swarm_id, active, idle, busy, topology) VALUES (0, 'audit', 0, 0, 0, '')"
    )
    db._conn.execute(
        "INSERT INTO decisions (id, created_at) VALUES ('old-decision', 0)"
    )
    db._conn.commit()
    assert db.purge_old_records(older_than_days=1) == 3
    db.close()


def test_builtin_memory_write_replaces_existing_file_atomically(tmp_path: Path) -> None:
    from memory.provider import VectorBuiltinMemoryProvider

    provider = VectorBuiltinMemoryProvider()
    provider.initialize("session", vector_home=str(tmp_path))
    provider._write_memory({"Commands": ["pytest"]})
    content = (tmp_path / "memory.md").read_text(encoding="utf-8")
    assert "- pytest" in content
    assert not list(tmp_path.glob(".memory.md.*.tmp"))


def test_faiss_json_dump_replaces_existing_file_atomically(tmp_path: Path) -> None:
    from memory.faiss_index import _atomic_json_dump

    target = tmp_path / "vectors.json"
    target.write_text("old", encoding="utf-8")
    _atomic_json_dump(str(target), {"zero": 0})
    assert json.loads(target.read_text(encoding="utf-8")) == {"zero": 0}
    assert not list(tmp_path.glob(".vectors.json.*.tmp"))
