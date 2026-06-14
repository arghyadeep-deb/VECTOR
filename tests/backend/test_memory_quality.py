"""Memory quality: forgetting/decay + cross-restart task continuation (roadmap #7)."""
from __future__ import annotations

import datetime

import pytest


# ── #7a: forgetting / decay ───────────────────────────────────────────────────

def _insert_dated(mem, event_id: str, event_type: str, content: str, days_ago: int):
    from core.memory.episodic import get_temp_cursor

    ts = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=days_ago)
    ).isoformat()
    with get_temp_cursor() as cur:
        cur.execute(
            "INSERT INTO episodic_memory (id,event_type,content,tags,context_snapshot,timestamp,source)"
            " VALUES (?,?,?,?,?,?,?)",
            (event_id, event_type, content, None, None, ts, "test"),
        )
        cur.execute(
            "INSERT INTO episodic_memory_fts (id,event_type,content,tags,source,timestamp,context_snapshot)"
            " VALUES (?,?,?,?,?,?,?)",
            (event_id, event_type, content, "", "test", ts, ""),
        )


def _exists(mem, event_id: str) -> bool:
    from core.memory.episodic import get_temp_cursor

    with get_temp_cursor() as cur:
        cur.execute("SELECT 1 FROM episodic_memory WHERE id=?", (event_id,))
        return cur.fetchone() is not None


def _fts_exists(event_id: str) -> bool:
    from core.memory.episodic import get_temp_cursor

    with get_temp_cursor() as cur:
        cur.execute("SELECT 1 FROM episodic_memory_fts WHERE id=?", (event_id,))
        return cur.fetchone() is not None


def test_prune_forgets_old_but_keeps_recent_and_protected():
    from core.memory.episodic import EpisodicMemory

    mem = EpisodicMemory()
    old_id = "test-old-" + datetime.datetime.now().strftime("%H%M%S%f")
    recent_id = "test-recent-" + datetime.datetime.now().strftime("%H%M%S%f")
    protected_id = "test-council-" + datetime.datetime.now().strftime("%H%M%S%f")

    _insert_dated(mem, old_id, "observation", "stale event", days_ago=200)
    _insert_dated(mem, recent_id, "observation", "fresh event", days_ago=2)
    _insert_dated(mem, protected_id, "council", "important verdict", days_ago=200)

    deleted = mem.prune_old_episodes(retention_days=90)

    assert deleted >= 1
    assert not _exists(mem, old_id), "old episode should be forgotten"
    assert not _fts_exists(old_id), "FTS row must be removed in sync"
    assert _exists(mem, recent_id), "recent episode must survive"
    assert _exists(mem, protected_id), "protected event_type must survive"


def test_prune_zero_retention_is_noop():
    from core.memory.episodic import EpisodicMemory

    mem = EpisodicMemory()
    assert mem.prune_old_episodes(retention_days=0) == 0
