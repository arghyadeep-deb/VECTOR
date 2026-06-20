"""Task 07 — memory/concurrency safety: serialized writes + bounded buffers."""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    import core.memory.episodic as ep
    tmp = Path(tempfile.mkdtemp()) / "mem.db"
    ep.close_db_connection()
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp))
    ep.EpisodicMemory()
    yield ep
    try:
        ep.close_db_connection()
    except Exception:
        pass


def test_open_sqlcipher_connection_sets_busy_timeout_and_wal(isolated_db):
    """Task 1.0 of plans/wire-absorbed-repos-autonomy.md. Phase 0 hit a hard
    'file is not a database'/hmac failure the instant a second process tried
    to open the same encrypted DB file a first process already held — these
    pragmas were simply never set. WAL + busy_timeout don't make true
    multi-process access a supported pattern (the architecture decision is
    in-process singleton, see autonomous_loop), but they turn an instant hard
    failure into a bounded wait, which is what actually bit us today."""
    ep = isolated_db
    conn = ep.get_db_connection()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_second_connection_to_same_file_waits_not_hard_fails(isolated_db):
    """Simulates the Phase 0 failure mode directly: two separate connection
    objects to the same encrypted DB file (standing in for two OS processes),
    one holding a write lock while the other tries to write. Before Task
    1.0, the second connection's write would raise 'database is locked'
    immediately; with busy_timeout=5000 it must instead wait and succeed."""
    import sqlcipher3
    from core.memory.episodic import _get_db_key, _sql_literal, _memory_db_path
    import threading
    import time

    db_path = _memory_db_path()
    db_key = _get_db_key()

    def _connect():
        c = sqlcipher3.dbapi2.connect(db_path, check_same_thread=False)
        c.execute("PRAGMA key = " + _sql_literal(db_key))
        c.execute("PRAGMA busy_timeout = 5000")
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("SELECT count(*) FROM sqlite_master")
        return c

    conn_a = _connect()
    conn_b = _connect()
    result: dict = {}

    def hold_write_lock():
        conn_a.execute("BEGIN IMMEDIATE")
        conn_a.execute(
            "INSERT INTO episodic_memory (event_type, content, tags, source, timestamp) "
            "VALUES ('lock_test', 'a', '[]', 'test', datetime('now'))"
        )
        time.sleep(0.5)
        conn_a.commit()

    def try_write():
        try:
            conn_b.execute(
                "INSERT INTO episodic_memory (event_type, content, tags, source, timestamp) "
                "VALUES ('lock_test', 'b', '[]', 'test', datetime('now'))"
            )
            conn_b.commit()
            result["ok"] = True
        except Exception as e:
            result["error"] = repr(e)

    t_a = threading.Thread(target=hold_write_lock)
    t_a.start()
    time.sleep(0.1)  # let A acquire the write lock first
    t_b = threading.Thread(target=try_write)
    t_b.start()
    t_a.join()
    t_b.join()

    conn_a.close()
    conn_b.close()

    assert result.get("ok") is True, f"second connection should wait then succeed, got: {result}"


def test_concurrent_writes_no_database_locked(isolated_db):
    ep = isolated_db
    errors: list[str] = []

    def writer(n: int):
        try:
            mem = ep.EpisodicMemory()
            for i in range(25):
                mem.store(event_type="concurrent", content=f"w{n}-{i}",
                          tags=["t"], source="test")
        except Exception as e:  # pragma: no cover - failure path
            errors.append(repr(e))

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent writes raised: {errors[:3]}"
    with ep.get_temp_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM episodic_memory WHERE event_type='concurrent'")
        assert cur.fetchone()[0] == 8 * 25


def test_point_system_log_is_bounded():
    from core.city.point_system import PointSystem, _MAX_POINT_LOGS
    ps = PointSystem()
    for i in range(_MAX_POINT_LOGS + 500):
        ps.apply(f"agent{i % 3}", "successful_action", 1)
    assert len(ps._logs) <= _MAX_POINT_LOGS
    # still functional
    assert isinstance(ps.leaderboard(), list)


def test_loop_guard_recent_calls_bounded():
    from core.loop.loop_guard import LoopGuardState, PHANTOM_THRESHOLD
    st = LoopGuardState(task_id="bound")
    for i in range(1000):
        st.check_phantom("tool", {"i": i})  # all distinct args
    assert len(st._recent_calls) <= PHANTOM_THRESHOLD + 2


def test_loop_guard_phantom_still_detected_with_deque():
    from core.loop.loop_guard import LoopGuardState, PHANTOM_THRESHOLD
    st = LoopGuardState(task_id="phantom")
    v = None
    for _ in range(PHANTOM_THRESHOLD + 1):
        v = st.check_phantom("bash", {"cmd": "ls"})
    assert v is not None and v.kind == "phantom"
