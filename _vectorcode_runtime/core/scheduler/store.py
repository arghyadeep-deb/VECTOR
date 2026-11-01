# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""SQLite-backed persistence for scheduled tasks and run logs."""

from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import json
import os
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

try:
    import sqlcipher3 as sqlcipher
    _USE_SQLCIPHER = True
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher
        _USE_SQLCIPHER = True
    except ImportError:
        sqlcipher = None
        _USE_SQLCIPHER = False
        logger.warning("[VECTOR][scheduler] SQLCipher unavailable -- task data will be stored UNENCRYPTED")

_CREATE_TASKS_TABLE = """\
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id              TEXT PRIMARY KEY,
    prompt          TEXT    NOT NULL,
    schedule_type   TEXT    NOT NULL,
    schedule_value  TEXT    NOT NULL,
    context_mode    TEXT    NOT NULL DEFAULT 'isolated',
    status          TEXT    NOT NULL DEFAULT 'active',
    next_run        TEXT,
    last_run        TEXT,
    agent           TEXT    NOT NULL DEFAULT 'simple',
    tools           TEXT    NOT NULL DEFAULT '',
    metadata        TEXT    NOT NULL DEFAULT '{}'
);
"""

_CREATE_LOGS_TABLE = """\
CREATE TABLE IF NOT EXISTS task_run_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT    NOT NULL,
    started_at  TEXT    NOT NULL,
    finished_at TEXT,
    success     INTEGER NOT NULL DEFAULT 0,
    result      TEXT    NOT NULL DEFAULT '',
    error       TEXT    NOT NULL DEFAULT ''
);
"""

_INSERT_TASK = """\
INSERT OR REPLACE INTO scheduled_tasks
    (id, prompt, schedule_type, schedule_value, context_mode,
     status, next_run, last_run, agent, tools, metadata)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_LOG = """\
INSERT INTO task_run_logs
    (task_id, started_at, finished_at, success, result, error)
VALUES (?, ?, ?, ?, ?, ?)
"""

_SCHEDULER_TABLES = ("scheduled_tasks", "task_run_logs")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _get_db_key() -> str:
    from core.memory.episodic import _get_db_key as _episodic_get_db_key
    return _episodic_get_db_key()


def _looks_like_plaintext_sqlite(path: Path) -> bool:
    try:
        return path.read_bytes()[:16] == b"SQLite format 3\x00"
    except OSError:
        return False


def _configure_sqlcipher_connection(conn) -> None:
    conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
    conn.execute("PRAGMA cipher_page_size = 4096")
    apply_pragmas(conn)


def _create_tables_on(conn) -> None:
    conn.execute(_CREATE_TASKS_TABLE)
    conn.execute(_CREATE_LOGS_TABLE)
    conn.commit()


def _open_sqlcipher_connection(path: Path):
    conn = sqlcipher.connect(str(path), check_same_thread=False)
    try:
        _configure_sqlcipher_connection(conn)
        conn.execute("SELECT count(*) FROM sqlite_master")
        return conn
    except Exception:
        conn.close()
        raise


def _migrate_plaintext_scheduler_db_to_sqlcipher(path: Path):
    backup_path = Path(f"{path}.plaintext.bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup_path)
    os.remove(path)
    logger.warning("[VECTOR][scheduler] Migrating plaintext scheduler DB; backup kept at {}", backup_path)
    conn = sqlcipher.connect(str(path), check_same_thread=False)
    try:
        _configure_sqlcipher_connection(conn)
        _create_tables_on(conn)
        plain_conn = sqlite3.connect(str(backup_path), check_same_thread=False)
        try:
            existing = {row[0] for row in plain_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in _SCHEDULER_TABLES:
                if table not in existing:
                    continue
                columns = [row[1] for row in plain_conn.execute(f'PRAGMA table_info("{table}")')]
                quoted = ", ".join(f'"{column}"' for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = plain_conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
                if rows:
                    conn.executemany(f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({placeholders})', rows)
            conn.commit()
        finally:
            plain_conn.close()
        return conn
    except Exception:
        conn.close()
        if path.exists():
            os.remove(path)
        shutil.copy2(backup_path, path)
        raise

class SchedulerStore:
    """SQLite CRUD store for scheduled tasks and their run logs."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        path = Path(self._db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if _USE_SQLCIPHER:
            self._conn = _migrate_plaintext_scheduler_db_to_sqlcipher(path) if _looks_like_plaintext_sqlite(path) else _open_sqlcipher_connection(path)
            self._conn.row_factory = sqlcipher.Row
        else:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            apply_pragmas(self._conn)
            self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            _create_tables_on(self._conn)

    # -- Task CRUD -----------------------------------------------------------

    def save_task(self, task: Dict[str, Any]) -> None:
        """Insert or replace a scheduled task record."""
        with self._lock:
            self._conn.execute(
                _INSERT_TASK,
                (
                    task["id"],
                    task["prompt"],
                    task["schedule_type"],
                    task["schedule_value"],
                    task.get("context_mode", "isolated"),
                    task.get("status", "active"),
                    task.get("next_run"),
                    task.get("last_run"),
                    task.get("agent", "simple"),
                    task.get("tools", ""),
                    json.dumps(task.get("metadata", {})),
                ),
            )
            self._conn.commit()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single task by ID, or ``None`` if not found."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all tasks, optionally filtered by *status*."""
        with self._lock:
            if status is not None:
                rows = self._conn.execute(
                    "SELECT * FROM scheduled_tasks WHERE status = ?", (status,)
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM scheduled_tasks").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_due_tasks(self, now_iso: str) -> List[Dict[str, Any]]:
        """Return active tasks whose ``next_run`` is at or before *now_iso*."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM scheduled_tasks WHERE status = 'active' "
                "AND next_run IS NOT NULL AND next_run <= ?",
                (now_iso,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_task(self, task: Dict[str, Any]) -> None:
        """Update an existing task (same as save_task — uses INSERT OR REPLACE)."""
        self.save_task(task)

    def delete_task(self, task_id: str) -> None:
        """Delete a task by ID."""
        with self._lock:
            self._conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            self._conn.commit()

    # -- Run logs ------------------------------------------------------------

    def log_run(
        self,
        task_id: str,
        started_at: str,
        finished_at: str,
        success: bool,
        result: str = "",
        error: str = "",
    ) -> None:
        """Record a single execution of a task."""
        with self._lock:
            self._conn.execute(
                _INSERT_LOG,
                (task_id, started_at, finished_at, int(success), result, error),
            )
            self._conn.commit()

    def get_run_logs(self, task_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent run logs for *task_id*."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM task_run_logs WHERE task_id = ? ORDER BY id DESC LIMIT ?",
                (task_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- Lifecycle -----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        d = dict(row)
        if "metadata" in d and isinstance(d["metadata"], str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                d["metadata"] = {}
        return d

__all__ = ["SchedulerStore"]
