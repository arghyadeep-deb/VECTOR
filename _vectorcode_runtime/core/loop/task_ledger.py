"""Durable task ledger — cross-restart task continuation (roadmap #7).

The TaskQueue runs work in-memory, so a crash/restart silently loses everything
that was queued or running. This ledger persists every task's metadata to a small
SQLite file (separate from the encrypted memory DB — task metadata isn't secret).

On startup, any task still marked QUEUED/RUNNING from a previous process is a task
that was interrupted by the restart: it is flipped to INTERRUPTED and surfaced via
``recover_interrupted()`` so the autonomous loop (or the owner) can re-submit it.
Live coroutines can't be resurrected, so this gives durable visibility +
re-submission — not magical resume of arbitrary in-flight callables.

Follows the audit #17 concurrency rule: RLock + WAL + busy_timeout.
"""
from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger

_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_ledger (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    priority     TEXT,
    district     TEXT,
    tags         TEXT,
    status       TEXT,
    progress     REAL DEFAULT 0.0,
    error        TEXT,
    submitted_at REAL,
    started_at   REAL,
    finished_at  REAL,
    updated_at   REAL
)
"""

# Statuses considered "in flight" — if found at startup they were interrupted.
_IN_FLIGHT = ("queued", "running")


class TaskLedger:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        apply_pragmas(self._conn)
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def upsert(self, row: dict[str, Any]) -> None:
        """Insert or update a task record. Best-effort: never raises to caller."""
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT INTO task_ledger
                       (id,name,priority,district,tags,status,progress,error,
                        submitted_at,started_at,finished_at,updated_at)
                       VALUES (:id,:name,:priority,:district,:tags,:status,:progress,
                               :error,:submitted_at,:started_at,:finished_at,:updated_at)
                       ON CONFLICT(id) DO UPDATE SET
                         status=excluded.status, progress=excluded.progress,
                         error=excluded.error, started_at=excluded.started_at,
                         finished_at=excluded.finished_at, updated_at=excluded.updated_at""",
                    {**row, "updated_at": time.time()},
                )
                self._conn.commit()
        except Exception as e:  # ledger must never crash the queue (RULE 2)
            logger.warning(f"[VECTOR][task_ledger] upsert failed: {e}")

    def recover_interrupted(self) -> list[dict[str, Any]]:
        """Flip any in-flight tasks from a previous run to INTERRUPTED, return them."""
        try:
            with self._lock:
                cur = self._conn.execute(
                    f"SELECT * FROM task_ledger WHERE status IN ({','.join('?' * len(_IN_FLIGHT))})",
                    _IN_FLIGHT,
                )
                cols = [c[0] for c in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                if rows:
                    self._conn.execute(
                        f"UPDATE task_ledger SET status='interrupted', updated_at=? "
                        f"WHERE status IN ({','.join('?' * len(_IN_FLIGHT))})",
                        (time.time(), *_IN_FLIGHT),
                    )
                    self._conn.commit()
                    logger.warning(
                        f"[VECTOR][task_ledger] recovered {len(rows)} interrupted task(s) "
                        "from previous run"
                    )
            return rows
        except Exception as e:
            logger.warning(f"[VECTOR][task_ledger] recover failed: {e}")
            return []

    def list_interrupted(self) -> list[dict[str, Any]]:
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT * FROM task_ledger WHERE status='interrupted' ORDER BY submitted_at"
                )
                cols = [c[0] for c in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            logger.warning(f"[VECTOR][task_ledger] list_interrupted failed: {e}")
            return []

    def get(self, task_id: str) -> dict[str, Any] | None:
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT * FROM task_ledger WHERE id=?", (task_id,)
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [c[0] for c in cur.description]
                return dict(zip(cols, row))
        except Exception as e:
            logger.warning(f"[VECTOR][task_ledger] get failed: {e}")
            return None

    def close(self) -> None:
        try:
            with self._lock:
                self._conn.close()
        except Exception as e:
            logger.warning("[VECTOR][task_ledger] close failed: {}", e)