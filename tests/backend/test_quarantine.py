"""Phase 2 — quarantine kill-switch: auto-on-threat guardian + MCP control tools."""
from __future__ import annotations

import asyncio
import json

import pytest

from core.event_bus.types import Event, EventType
from core.memory.multi_db_manager import MultiDBManager, get_manager


@pytest.fixture(autouse=True)
def _clean_quarantine():
    """Ensure the singleton manager starts/ends each test with nothing quarantined."""
    mgr = get_manager()
    for b in ("supabase", "turso", "d1"):
        mgr.reenable(b)
    yield
    for b in ("supabase", "turso", "d1"):
        mgr.reenable(b)


# ── auto-on-threat guardian ─────────────────────────────────────────────────────

def test_guardian_quarantines_cloud_on_critical_threat():
    from core.memory import db_guardian

    mgr = get_manager()
    assert not mgr._quarantined
    evt = Event(event_type=EventType.SECURITY_ALERT,
                data={"threat_level": "critical"}, source="malware_hunter")
    asyncio.run(db_guardian._on_security_event(evt))
    assert mgr.is_quarantined("supabase")
    assert mgr.is_quarantined("turso")
    assert mgr.is_quarantined("d1")


def test_guardian_ignores_low_severity():
    from core.memory import db_guardian

    mgr = get_manager()
    evt = Event(event_type=EventType.SECURITY_ALERT,
                data={"threat_level": "low"}, source="x")
    asyncio.run(db_guardian._on_security_event(evt))
    assert not mgr._quarantined


def test_guardian_install_and_publish_roundtrip():
    """install + publish_threat must wire to the bus without error."""
    from core.memory import db_guardian

    async def go():
        from core.event_bus.bus import get_event_bus
        bus = await get_event_bus()
        await db_guardian.install_db_guardian(bus)
        await db_guardian.publish_threat("high", source="test", details={"target": "unit"})
        # let the async bus dispatch
        await asyncio.sleep(0.2)
    asyncio.run(go())
    # guardian should have severed the mesh from the published high threat
    assert get_manager().is_quarantined("supabase")


# ── MCP control tools (control from any device) ─────────────────────────────────

def _call(mcp, name, **params):
    import core.mcp_server  # noqa
    res = asyncio.run(mcp.call_tool(name, params))
    # FastMCP returns a result whose text content holds our JSON string
    content = res.content if hasattr(res, "content") else res
    text = content[0].text if isinstance(content, list) else str(content)
    return json.loads(text)


def test_mcp_db_control_tools_roundtrip():
    import core.mcp_server as m
    srv = m._make_server()

    q = _call(srv, "db_quarantine", backend="turso", reason="unit-test")
    assert q["quarantined"] is True and q["backend"] == "turso"

    status = _call(srv, "db_status")
    assert status["backends"]["turso"]["quarantined"] is True
    assert "turso" in status["quarantined"]

    r = _call(srv, "db_reenable", backend="turso")
    assert r["reenabled"] is True

    status2 = _call(srv, "db_status")
    assert status2["backends"]["turso"]["quarantined"] is False


def test_mcp_db_quarantine_rejects_local():
    import core.mcp_server as m
    srv = m._make_server()
    q = _call(srv, "db_quarantine", backend="local")
    assert q["quarantined"] is False
