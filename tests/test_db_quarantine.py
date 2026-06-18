"""Tests for the quarantine kill-switch: MCP tools + auto-quarantine on threat."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── helpers ──────────────────────────────────────────────────────────────────

def _fresh_manager():
    """Return the singleton MultiDBManager with quarantine state cleared."""
    from core.memory.multi_db_manager import get_manager
    mgr = get_manager()
    mgr._quarantined.clear()
    mgr._quarantine_reasons.clear()
    return mgr


def _register_tools():
    """Register db_control tools on a fake MCP and return the tool map."""
    from core.mcp_tools.db_control import add_db_control_tools

    class FakeMCP:
        tools = {}
        def tool(self, fn):
            self.tools[fn.__name__] = fn
            return fn

    fake = FakeMCP()
    add_db_control_tools(fake)
    return fake.tools


# ── MCP tool tests ────────────────────────────────────────────────────────────

class TestDbStatusTool:
    def test_returns_all_backends(self):
        _fresh_manager()
        tools = _register_tools()
        result = json.loads(tools["db_status"]())
        assert "backends" in result
        for b in ("supabase", "turso", "d1"):
            assert b in result["backends"]

    def test_reflects_quarantine(self):
        mgr = _fresh_manager()
        mgr.quarantine("turso", "unit-test")
        tools = _register_tools()
        result = json.loads(tools["db_status"]())
        assert result["backends"]["turso"]["quarantined"] is True
        assert "turso" in result["quarantined"]
        assert result["backends"]["supabase"]["quarantined"] is False


class TestDbQuarantineTool:
    def test_quarantine_valid_backend(self):
        _fresh_manager()
        tools = _register_tools()
        result = json.loads(tools["db_quarantine"]("supabase", "test-reason"))
        assert result["quarantined"] is True
        assert result["backend"] == "supabase"

    def test_quarantine_local_blocked(self):
        _fresh_manager()
        tools = _register_tools()
        result = json.loads(tools["db_quarantine"]("local"))
        assert result["quarantined"] is False
        assert result["note"] is not None

    def test_quarantine_all_three(self):
        mgr = _fresh_manager()
        tools = _register_tools()
        for b in ("supabase", "turso", "d1"):
            r = json.loads(tools["db_quarantine"](b, "bulk-test"))
            assert r["quarantined"] is True
        assert len(mgr._quarantined) == 3


class TestDbReenableTool:
    def test_reenable_restores_backend(self):
        mgr = _fresh_manager()
        mgr.quarantine("d1", "test")
        tools = _register_tools()
        result = json.loads(tools["db_reenable"]("d1"))
        assert result["reenabled"] is True
        assert not mgr.is_quarantined("d1")

    def test_reenable_nonquarantined_is_noop(self):
        _fresh_manager()
        tools = _register_tools()
        result = json.loads(tools["db_reenable"]("turso"))
        assert result["reenabled"] is False


# ── Auto-quarantine via security event ───────────────────────────────────────

class TestAutoQuarantine:
    def test_critical_alert_severs_all_cloud_backends(self):
        mgr = _fresh_manager()
        from core.memory.db_guardian import _on_security_event
        from core.event_bus.types import Event, EventType

        evt = Event(
            event_type=EventType.SECURITY_ALERT,
            data={"threat_level": "critical"},
            source="test",
        )
        asyncio.run(_on_security_event(evt))

        assert mgr.is_quarantined("supabase")
        assert mgr.is_quarantined("turso")
        assert mgr.is_quarantined("d1")
        assert not mgr.is_quarantined("local")

    def test_low_severity_does_not_quarantine(self):
        mgr = _fresh_manager()
        from core.memory.db_guardian import _on_security_event
        from core.event_bus.types import Event, EventType

        evt = Event(
            event_type=EventType.SECURITY_ALERT,
            data={"threat_level": "low"},
            source="test",
        )
        asyncio.run(_on_security_event(evt))

        assert not mgr.is_quarantined("supabase")
        assert not mgr.is_quarantined("turso")

    def test_push_skipped_when_quarantined(self):
        mgr = _fresh_manager()
        mgr.quarantine("supabase", "test")
        mgr.quarantine("turso", "test")

        async def run():
            return await mgr._push_local_to_cloud("1970-01-01T00:00:00+00:00")

        total = asyncio.run(run())
        assert total == 0
