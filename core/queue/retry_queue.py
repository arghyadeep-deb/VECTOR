"""
core/queue/retry_queue.py — Durable retry queue for failed actions (Gap 4).

SQLite-backed. Exponential backoff: 1s → 5s → 30s → 5min → 30min.
After 5 attempts the action moves to the dead-letter table.
The scheduler_loop (every 30s) calls RetryQueue.get().pop_due() to drain it.
"""
import sqlite3

__all__ = [
    "RetryItem",
    "RetryQueue",
]

import json
import time
import datetime
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger
from core.config import CONFIG

_DB_PATH = Path(str(CONFIG.get("db_path", Path(__file__).parent.parent.parent / "vector_memory.db")))
_BACKOFF = [1, 5, 30, 300, 1800]   # seconds per attempt (0-indexed)
_MAX_ATTEMPTS = len(_BACKOFF)


@dataclass
class RetryItem:
    id: int
    action_type: str
    params: dict
    proposed_by: str
    attempt: int
    next_retry_at: float
    error: str = ""
    created_at: float = field(default_factory=time.time)


class RetryQueue:
    _instance: "RetryQueue | None" = None

    def __init__(self, db_path: Path = _DB_PATH):
        self._db = str(db_path)
        self._init_db()

    @classmethod
    def get(cls) -> "RetryQueue":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db, timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS retry_queue (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type   TEXT NOT NULL,
                    params        TEXT NOT NULL,
                    proposed_by   TEXT NOT NULL DEFAULT 'loop',
                    attempt       INTEGER NOT NULL DEFAULT 0,
                    next_retry_at REAL NOT NULL,
                    error         TEXT NOT NULL DEFAULT '',
                    created_at    REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type   TEXT NOT NULL,
                    params        TEXT NOT NULL,
                    proposed_by   TEXT NOT NULL,
                    attempts      INTEGER NOT NULL,
                    last_error    TEXT NOT NULL,
                    failed_at     REAL NOT NULL
                )
            """)

    def push(self, action_type: str, params: dict, proposed_by: str = "loop",
             error: str = "", attempt: int = 0) -> int:
        """Enqueue a failed action for retry. Returns the row id."""
        delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
        next_retry = time.time() + delay
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO retry_queue (action_type, params, proposed_by, attempt, next_retry_at, error, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (action_type, json.dumps(params, default=str), proposed_by,
                 attempt, next_retry, error[:500], time.time()),
            )
            row_id = cur.lastrowid
        logger.info(f"[VECTOR][retry] queued {action_type} attempt={attempt} retry_in={delay}s id={row_id}")
        return row_id

    def pop_due(self, limit: int = 10) -> list[RetryItem]:
        """Return items whose next_retry_at <= now. Removes them from the queue."""
        now = time.time()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM retry_queue WHERE next_retry_at <= ? ORDER BY next_retry_at LIMIT ?",
                (now, limit),
            ).fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                conn.execute(f"DELETE FROM retry_queue WHERE id IN ({','.join('?' * len(ids))})", ids)
        return [
            RetryItem(
                id=r["id"], action_type=r["action_type"],
                params=json.loads(r["params"]), proposed_by=r["proposed_by"],
                attempt=r["attempt"], next_retry_at=r["next_retry_at"],
                error=r["error"], created_at=r["created_at"],
            )
            for r in rows
        ]

    def requeue_or_dlq(self, item: RetryItem, error: str) -> None:
        """After a retry failure: re-enqueue with incremented attempt, or DLQ if exhausted."""
        next_attempt = item.attempt + 1
        if next_attempt >= _MAX_ATTEMPTS:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO dead_letter (action_type, params, proposed_by, attempts, last_error, failed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (item.action_type, json.dumps(item.params, default=str),
                     item.proposed_by, next_attempt, error[:500], time.time()),
                )
            logger.warning(f"[VECTOR][retry] DLQ: {item.action_type} after {next_attempt} attempts — {error[:80]}")
        else:
            self.push(item.action_type, item.params, item.proposed_by, error, next_attempt)

    def size(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM retry_queue").fetchone()[0]

    def dlq_size(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM dead_letter").fetchone()[0]
