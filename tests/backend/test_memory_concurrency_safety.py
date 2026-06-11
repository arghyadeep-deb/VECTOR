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
    orig = ep.CONFIG.get("db_path", "vector_memory.db")
    ep.CONFIG["db_path"] = str(tmp)
    ep._db_connection = None
    ep.EpisodicMemory()
    yield ep
    try:
        if ep._db_connection is not None:
            ep._db_connection.close()
    except Exception:
        pass
    ep._db_connection = None
    ep.CONFIG["db_path"] = orig


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
