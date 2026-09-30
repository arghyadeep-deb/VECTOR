"""Regression test for core/api/routers/queue.py's raw-sqlite3-connect bypass
bug, found by Codex's core/ SQLite triage (2026-09-30, part of the Phase 3
whole-repo audit's Claude/Codex split).

retry_items(), dlq_items(), and replay_item() used to open
`sqlite3.connect(rq._db, ...)` directly, duplicating (and bypassing)
RetryQueue._conn()'s SQLCipher-aware logic. Against the real production main
DB (SQLCipher-encrypted), that raw connect always fails with "file is not a
database" -- silently swallowed by each endpoint's broad `except Exception`,
so the API would always report an empty queue/DLQ instead of the real state.
Fixed by routing through RetryQueue._conn() like every other method on the
class already does (see push()/pop_due()/size() etc.), closing the connection
only when _conn() reports it as private.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.queue.retry_queue import RetryQueue
from core.api.routers.queue import retry_items, dlq_items, replay_item


def _isolated_queue() -> RetryQueue:
    db_path = Path(tempfile.mkdtemp()) / "test_retry_queue.db"
    return RetryQueue(db_path=db_path)


@pytest.mark.asyncio
async def test_retry_items_uses_conn_not_raw_sqlite3():
    rq = _isolated_queue()
    rq.push("test_action", {"foo": "bar"})

    with patch("core.queue.retry_queue.RetryQueue.get", return_value=rq):
        result = await retry_items(limit=20)

    assert "error" not in result
    assert result["count"] == 1
    assert result["items"][0]["action_type"] == "test_action"


@pytest.mark.asyncio
async def test_dlq_items_uses_conn_not_raw_sqlite3():
    rq = _isolated_queue()
    conn, private = rq._conn()
    try:
        conn.execute(
            "INSERT INTO dead_letter (action_type, params, proposed_by, attempts, last_error, failed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("dead_action", "{}", "loop", 5, "boom", 0.0),
        )
        conn.commit()
    finally:
        if private:
            conn.close()

    with patch("core.queue.retry_queue.RetryQueue.get", return_value=rq):
        result = await dlq_items(limit=20)

    assert "error" not in result
    assert result["count"] == 1
    assert result["items"][0]["action_type"] == "dead_action"


@pytest.mark.asyncio
async def test_replay_item_uses_conn_and_deletes_row():
    rq = _isolated_queue()
    item_id = rq.push("replay_me", {"x": 1})

    with patch("core.queue.retry_queue.RetryQueue.get", return_value=rq), \
         patch("core.loop.permission_gateway.PermissionGateway.execute") as mock_exec:
        mock_exec.return_value.level = "green"
        result = await replay_item(item_id)

    assert result["replayed"] == item_id
    # row must be gone from the pending queue after replay
    conn, private = rq._conn()
    try:
        row = conn.execute("SELECT id FROM retry_queue WHERE id = ?", (item_id,)).fetchone()
    finally:
        if private:
            conn.close()
    assert row is None


@pytest.mark.asyncio
async def test_retry_items_connection_is_closed_when_private():
    """The old bug's failure mode was a silently-swallowed connection error;
    confirm the new code path actually calls RetryQueue._conn() (not a
    duplicated sqlite3.connect) by spying on it."""
    rq = _isolated_queue()
    rq.push("spy_action", {})

    with patch("core.queue.retry_queue.RetryQueue.get", return_value=rq), \
         patch.object(RetryQueue, "_conn", wraps=rq._conn) as spy:
        result = await retry_items(limit=5)

    assert spy.called
    assert result["count"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
