"""Phase 1 — multi-DB mesh: tiering, last-write-wins merge, tier tagging,
and the quarantine kill-switch (manager side). No network: cloud calls are
no-ops without creds; we test the local merge + policy logic directly."""
from __future__ import annotations

import asyncio
import datetime

import pytest

from core.memory import tiering
from core.memory.multi_db_manager import MultiDBManager


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── tiering policy ────────────────────────────────────────────────────────────

def test_tiering_classifies_tables_and_events():
    assert tiering.is_critical("semantic_memory")
    assert tiering.is_critical("agent_history")
    assert tiering.classify("episodic_memory", {"event_type": "council"}) == "critical"
    assert tiering.classify("episodic_memory", {"event_type": "observation"}) == "bulk"
    assert tiering.classify("reasoning_chains") == "bulk"
    assert "ghost" in tiering.protected_event_types()


# ── last-write-wins merge (single PK) ───────────────────────────────────────────

def test_merge_rows_lww_single_pk():
    mgr = MultiDBManager()
    eid = "mesh-test-" + datetime.datetime.now().strftime("%H%M%S%f")
    old, new = "2020-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00"

    # seed an old local row
    assert mgr.write_local("episodic_memory", {
        "id": eid, "event_type": "observation", "content": "old",
        "tags": None, "context_snapshot": None, "timestamp": old, "source": "test",
    })
    # newer cloud row wins
    merged = mgr._merge_rows("episodic_memory", [{
        "id": eid, "event_type": "observation", "content": "new",
        "tags": None, "context_snapshot": None, "timestamp": new, "source": "cloud",
    }])
    assert merged == 1
    conn = mgr._get_local().conn
    assert conn.execute("SELECT content FROM episodic_memory WHERE id=?", (eid,)).fetchone()[0] == "new"

    # older cloud row is ignored (LWW)
    merged2 = mgr._merge_rows("episodic_memory", [{
        "id": eid, "event_type": "observation", "content": "stale",
        "tags": None, "context_snapshot": None, "timestamp": old, "source": "cloud",
    }])
    assert merged2 == 0
    assert conn.execute("SELECT content FROM episodic_memory WHERE id=?", (eid,)).fetchone()[0] == "new"


def test_merge_rows_composite_pk():
    """policy_memory has a composite PK (action_type, situation_hash)."""
    mgr = MultiDBManager()
    sit = "mesh-" + datetime.datetime.now().strftime("%H%M%S%f")
    merged = mgr._merge_rows("policy_memory", [{
        "action_type": "test_action", "situation_hash": sit,
        "avg_reward": 0.7, "sample_count": 3, "last_updated": _now(),
    }])
    assert merged == 1
    conn = mgr._get_local().conn
    row = conn.execute(
        "SELECT avg_reward FROM policy_memory WHERE action_type=? AND situation_hash=?",
        ("test_action", sit),
    ).fetchone()
    assert row and abs(row[0] - 0.7) < 1e-9


# ── tier tagging on write_all ───────────────────────────────────────────────────

def test_write_all_tags_tier():
    mgr = MultiDBManager()
    async def go():
        eid = "tier-" + datetime.datetime.now().strftime("%H%M%S%f")
        r_bulk = await mgr.write_all("episodic_memory", {
            "id": eid, "event_type": "observation", "content": "x",
            "tags": None, "context_snapshot": None, "timestamp": _now(), "source": "t",
        })
        r_crit = await mgr.write_all("semantic_memory", {
            "key": eid, "value": "v", "category": "c", "confidence": 0.9, "updated_at": _now(),
        })
        return r_bulk, r_crit
    r_bulk, r_crit = asyncio.run(go())
    assert r_bulk["tier"] == "bulk" and r_bulk["local"] is True
    assert r_crit["tier"] == "critical" and r_crit["local"] is True


# ── quarantine kill-switch (manager side) ───────────────────────────────────────

def test_quarantine_and_reenable():
    mgr = MultiDBManager()
    assert mgr.quarantine("turso", reason="malware-test") is True
    assert mgr.is_quarantined("turso")
    assert mgr.backend_status()["turso"]["quarantined"] is True
    assert mgr.backend_status()["turso"]["reason"] == "malware-test"
    # local cannot be quarantined
    assert mgr.quarantine("local") is False
    assert mgr.quarantine("bogus") is False
    # reenable
    assert mgr.reenable("turso") is True
    assert not mgr.is_quarantined("turso")
    assert mgr.reenable("turso") is False  # already enabled


def test_quarantined_backend_skipped_on_write():
    mgr = MultiDBManager()
    mgr.quarantine("supabase")
    mgr.quarantine("turso")
    async def go():
        return await mgr.write_cloud("episodic_memory", {
            "id": "q-" + datetime.datetime.now().strftime("%H%M%S%f"),
            "event_type": "observation", "content": "x", "timestamp": _now(), "source": "t",
        })
    res = asyncio.run(go())
    # both quarantined → nothing written, queued for later
    assert res["supabase"] is False and res["turso"] is False
    assert len(mgr._sync_queue) == 1


def test_sync_all_noop_without_cloud_creds():
    """With no cloud configured, sync_all must run clean (no crash, no-op)."""
    mgr = MultiDBManager()
    res = asyncio.run(mgr.sync_all())
    assert isinstance(res, dict) and "pushed" in res and "pulled" in res
