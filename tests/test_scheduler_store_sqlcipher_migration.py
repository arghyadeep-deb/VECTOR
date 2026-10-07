"""Regression tests for OD-20 scheduler store encryption and migration."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.scheduler.store import SchedulerStore, _create_tables_on, _USE_SQLCIPHER

pytestmark = pytest.mark.skipif(not _USE_SQLCIPHER, reason="sqlcipher3 not installed")

_PROMPT = "email secret-report-OD20@example.test tomorrow"


def _make_plaintext_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    _create_tables_on(conn)
    conn.execute("INSERT INTO scheduled_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("task-1", _PROMPT, "once", "2026-10-08", "isolated", "active", "2026-10-08", None, "simple", "email", '{"private":true}'))
    conn.execute("INSERT INTO task_run_logs VALUES (?, ?, ?, ?, ?, ?, ?)", (5, "task-1", "start", "finish", 1, "sent", ""))
    conn.commit()
    conn.close()


def test_fresh_scheduler_database_is_encrypted(tmp_path: Path) -> None:
    path = tmp_path / "scheduler.db"
    store = SchedulerStore(path)
    store.save_task({"id": "task-1", "prompt": _PROMPT, "schedule_type": "once", "schedule_value": "tomorrow"})
    store.close()
    raw = path.read_bytes()
    assert raw[:16] != b"SQLite format 3\x00"
    assert _PROMPT.encode() not in raw


def test_plaintext_scheduler_database_migrates_and_reopens_once(tmp_path: Path) -> None:
    path = tmp_path / "scheduler.db"
    _make_plaintext_db(path)
    store = SchedulerStore(path)
    assert store.get_task("task-1")["prompt"] == _PROMPT
    assert store.get_run_logs("task-1")[0]["id"] == 5
    store.close()
    backups = list(tmp_path.glob("scheduler.db.plaintext.bak.*"))
    assert len(backups) == 1
    plain = sqlite3.connect(str(backups[0]))
    assert plain.execute("SELECT prompt FROM scheduled_tasks").fetchone()[0] == _PROMPT
    plain.close()
    assert path.read_bytes()[:16] != b"SQLite format 3\x00"
    SchedulerStore(path).close()
    assert len(list(tmp_path.glob("scheduler.db.plaintext.bak.*"))) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
