"""Task 02 — MCP memory tool safety.

Path guard confines import/export to an approved directory; memory_clear
requires an explicit destructive confirmation.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from core.mcp_server import _resolve_memory_path, _memory_export_dir, _MEMORY_CLEAR_CONFIRM


# ── path guard (deterministic unit tests) ────────────────────────────────────

def test_blank_path_defaults_into_approved_dir():
    resolved, err = _resolve_memory_path("", default_name="memory_export.json")
    assert err is None
    assert resolved.parent == _memory_export_dir()
    assert resolved.name == "memory_export.json"


def test_bare_filename_lands_in_approved_dir():
    resolved, err = _resolve_memory_path("snapshot.json", default_name="memory_export.json")
    assert err is None
    assert resolved.parent == _memory_export_dir()


def test_traversal_is_rejected():
    resolved, err = _resolve_memory_path("../../etc/passwd", default_name="x.json")
    assert resolved is None
    assert "outside approved" in err


def test_absolute_path_outside_is_rejected():
    outside = str(Path(tempfile.gettempdir()) / "evil_export.json")
    resolved, err = _resolve_memory_path(outside, default_name="x.json")
    assert resolved is None
    assert err


def test_absolute_path_inside_is_allowed():
    inside = str(_memory_export_dir() / "ok.json")
    resolved, err = _resolve_memory_path(inside, default_name="x.json")
    assert err is None
    assert resolved == (_memory_export_dir() / "ok.json").resolve()


def test_nested_traversal_back_inside_is_still_evaluated_on_real_target():
    # foo/../bar resolves to bar inside the dir → allowed
    resolved, err = _resolve_memory_path("foo/../bar.json", default_name="x.json")
    assert err is None
    assert resolved.parent == _memory_export_dir()


# ── tool behavior on an isolated DB ──────────────────────────────────────────

@pytest.fixture
def isolated_memory(monkeypatch):
    """Point episodic memory at a throwaway DB and reset the singleton.

    MUST use the VECTOR_DB_PATH env override — configured_db_path() checks it
    BEFORE CONFIG["db_path"], so mutating CONFIG alone left these tests running
    against the LIVE database (found 2026-07-08: seed/clear/export ran on 285k
    production rows; only a failing pre-assert kept memory_clear from wiping them).
    """
    import core.memory.episodic as ep
    tmp = Path(tempfile.mkdtemp()) / "mem.db"
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp))
    monkeypatch.setitem(ep.CONFIG, "db_path", str(tmp))
    ep.close_db_connection()
    ep.EpisodicMemory()  # creates the schema at the throwaway path
    # Hard guard: never run destructive tests against a DB that already has data
    with ep.get_temp_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM episodic_memory")
        count = cur.fetchone()[0]
    assert count == 0, f"isolated_memory redirect FAILED ({count} rows visible) — refusing to run destructive tests"
    yield ep
    ep.close_db_connection()


def _build_server():
    pytest.importorskip("fastmcp")
    from fastmcp import FastMCP
    from core.mcp_server import _add_expansion_tools
    mcp = FastMCP("test-memory-safety")
    _add_expansion_tools(mcp)  # registers memory_clear/export/import
    return mcp


def _text(res) -> str:
    out = str(res)
    for attr in ("content", "data", "structured_content"):
        v = getattr(res, attr, None)
        if v:
            out += str(v)
    return out


def _seed(ep, n=3):
    mem = ep.EpisodicMemory()
    for i in range(n):
        mem.store(event_type="unit", content=f"event {i}", tags=["t"], source="test")


def _count(ep) -> int:
    with ep.get_temp_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM episodic_memory")
        return cur.fetchone()[0]


def test_memory_clear_without_confirmation_keeps_rows(isolated_memory):
    ep = isolated_memory
    _seed(ep, 3)
    server = _build_server()
    no_text = _text(asyncio.run(server.call_tool("memory_clear", {})))
    assert "confirmation required" in no_text
    assert _count(ep) == 3  # nothing deleted


def test_memory_clear_with_confirmation_deletes(isolated_memory, monkeypatch):
    ep = isolated_memory
    from core.mcp_tools.expansion_modules import memory as memory_tools

    async def approve(*_args, **_kwargs):
        return type("Gate", (), {"approved": True, "level": "RED", "reason": "approved"})()

    monkeypatch.setattr(memory_tools, "evaluate_destructive_action", approve)
    _seed(ep, 3)
    server = _build_server()
    assert _count(ep) == 3
    yes_text = _text(asyncio.run(
        server.call_tool("memory_clear", {"confirm": _MEMORY_CLEAR_CONFIRM})))
    assert "cleared" in yes_text.lower()
    assert _count(ep) == 0


def test_memory_export_rejects_outside_path(isolated_memory):
    server = _build_server()
    outside = str(Path(tempfile.gettempdir()) / "leak.json")

    async def run():
        return _text(await server.call_tool("memory_export", {"path": outside}))

    out = asyncio.run(run())
    assert "outside approved" in out
    assert not Path(outside).exists()


def test_memory_export_then_import_inside_dir(isolated_memory):
    ep = isolated_memory
    _seed(ep, 2)
    server = _build_server()

    async def run():
        exp = _text(await server.call_tool("memory_export", {"path": "roundtrip.json"}))
        imp = _text(await server.call_tool("memory_import", {"path": "roundtrip.json"}))
        return exp, imp

    exp, imp = asyncio.run(run())
    assert '"ok": true' in exp.lower()
    # exported file is inside the approved dir
    assert (_memory_export_dir() / "roundtrip.json").exists()
    assert '"ok": true' in imp.lower()


def test_memory_import_missing_file_in_dir(isolated_memory):
    server = _build_server()

    async def run():
        return _text(await server.call_tool("memory_import", {"path": "does_not_exist.json"}))

    out = asyncio.run(run())
    assert "not found" in out.lower()
