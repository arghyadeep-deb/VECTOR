"""Tests for MultiDBManager._push_local_to_cloud and sync_all push step."""
import asyncio
import datetime
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_manager(local_conn):
    """Build a MultiDBManager wired to an in-memory SQLite conn."""
    from core.memory.multi_db_manager import MultiDBManager
    mgr = MultiDBManager.__new__(MultiDBManager)
    mgr._sync_queue = __import__("collections").deque()
    mgr._quarantined = set()
    mgr._last_sync = {
        "local": "1970-01-01T00:00:00+00:00",
        "supabase": None, "turso": None, "d1": None,
    }

    local_mock = MagicMock()
    local_mock.conn = local_conn
    mgr._local = local_mock
    mgr._get_local = lambda: local_mock
    mgr._get_config = lambda key: {
        "supabase_url": "https://fake.supabase.co",
        "supabase_key": "fake_key",
        "turso_url": "https://fake.turso.io",
        "turso_token": "fake_token",
    }.get(key)
    return mgr


def _make_conn_with_rows():
    """In-memory SQLite with semantic_memory rows at different timestamps."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE semantic_memory "
        "(key TEXT PRIMARY KEY, value TEXT, category TEXT, "
        "confidence REAL, updated_at TEXT)"
    )
    # old row — before since_ts
    conn.execute(
        "INSERT INTO semantic_memory VALUES (?,?,?,?,?)",
        ("old_key", "old_val", "test", 0.5, "2020-01-01T00:00:00+00:00"),
    )
    # new row — after since_ts
    conn.execute(
        "INSERT INTO semantic_memory VALUES (?,?,?,?,?)",
        ("new_key", "new_val", "test", 0.9, "2099-01-01T00:00:00+00:00"),
    )
    # other tables — no rows
    for t in ("episodic_memory", "policy_memory", "reasoning_chains",
              "skill_memory", "agent_history"):
        try:
            conn.execute(f"CREATE TABLE {t} (id TEXT PRIMARY KEY)")
        except Exception:
            pass
    conn.commit()
    return conn


class TestPushLocalToCloud:
    def test_only_new_rows_sent_to_supabase(self):
        conn = _make_conn_with_rows()
        mgr = _make_manager(conn)
        captured = []

        async def fake_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 201
            captured.append(kwargs.get("json", []))
            return resp

        async def run():
            with patch("httpx.AsyncClient") as mock_client:
                instance = AsyncMock()
                instance.post = fake_post
                mock_client.return_value.__aenter__ = AsyncMock(return_value=instance)
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
                return await mgr._push_local_to_cloud("2025-01-01T00:00:00+00:00")

        total = asyncio.run(run())
        # Only the "new_key" row (2099) should have been sent
        sent_keys = [r[0]["key"] for r in captured if r]
        assert "new_key" in sent_keys
        assert "old_key" not in sent_keys

    def test_quarantined_supabase_skipped(self):
        conn = _make_conn_with_rows()
        mgr = _make_manager(conn)
        mgr._quarantined = {"supabase", "turso"}

        async def run():
            return await mgr._push_local_to_cloud("1970-01-01T00:00:00+00:00")

        total = asyncio.run(run())
        assert total == 0

    def test_no_rows_returns_zero(self):
        conn = _make_conn_with_rows()
        mgr = _make_manager(conn)

        async def run():
            # since_ts in the far future — no rows are newer
            return await mgr._push_local_to_cloud("2999-01-01T00:00:00+00:00")

        with patch("httpx.AsyncClient"):
            total = asyncio.run(run())
        assert total == 0


class TestSyncAllPushStep:
    def test_sync_all_includes_pushed_local_key(self):
        conn = _make_conn_with_rows()
        mgr = _make_manager(conn)

        async def fake_push(since):
            return 3

        async def fake_pull_supabase():
            pass

        async def fake_pull_turso():
            pass

        async def run():
            mgr._push_local_to_cloud = fake_push
            mgr._pull_supabase = fake_pull_supabase
            mgr._pull_turso = fake_pull_turso
            return await mgr.sync_all()

        result = asyncio.run(run())
        assert "pushed_local" in result
        assert result["pushed_local"] == 3

    def test_sync_all_push_uses_last_sync_ts(self):
        conn = _make_conn_with_rows()
        mgr = _make_manager(conn)
        mgr._last_sync["local"] = "2025-06-01T00:00:00+00:00"
        received_since = []

        async def fake_push(since):
            received_since.append(since)
            return 0

        async def run():
            mgr._push_local_to_cloud = fake_push
            mgr._pull_supabase = AsyncMock()
            mgr._pull_turso = AsyncMock()
            return await mgr.sync_all()

        asyncio.run(run())
        assert received_since[0] == "2025-06-01T00:00:00+00:00"
