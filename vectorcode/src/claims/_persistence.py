"""
vectorcode/src/claims/_persistence.py
SQLite-backed persistence for VECTOR task claims.
"""
from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from loguru import logger

from ._types import (
    AgentType, ClaimStatus, IssueClaim,
    _ACTIVE_STATUSES, default_claims_db_path,
)


class ClaimRepository:
    """SQLite-backed persistence for VECTOR task claims."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        # Resolve at construction time, not function-definition/import time.
        # VECTOR_TEST_DATA_DIR is deliberately set after some modules import
        # this package, and must still isolate every newly-created repository.
        self.db_path = Path(db_path) if db_path is not None else default_claims_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()
        logger.info(f"[VECTOR][claims] ClaimRepository ready at {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        apply_pragmas(conn)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claims (
                    id TEXT PRIMARY KEY, issue_id TEXT NOT NULL,
                    claimant_id TEXT NOT NULL, claimant_name TEXT NOT NULL,
                    claimant_type TEXT NOT NULL, status TEXT NOT NULL,
                    claimed_at REAL NOT NULL, last_activity_at REAL NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0, blob TEXT NOT NULL
                )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_issue_id ON claims(issue_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_claimant_id ON claims(claimant_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, claim_id TEXT NOT NULL,
                    issue_id TEXT NOT NULL, event_type TEXT NOT NULL,
                    payload TEXT NOT NULL, occurred_at REAL NOT NULL
                )""")
            conn.commit()

    def _row_to_claim(self, row: sqlite3.Row) -> IssueClaim:
        return IssueClaim.from_dict(json.loads(row["blob"]))

    def _claim_to_row(self, claim: IssueClaim) -> dict:
        return {
            "id": claim.id, "issue_id": claim.issue_id,
            "claimant_id": claim.claimant.id, "claimant_name": claim.claimant.name,
            "claimant_type": claim.claimant.type, "status": claim.status.value,
            "claimed_at": claim.claimed_at, "last_activity_at": claim.last_activity_at,
            "progress": claim.progress, "blob": json.dumps(claim.to_dict()),
        }

    def save(self, claim: IssueClaim) -> None:
        row = self._claim_to_row(claim)
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO claims
                    (id, issue_id, claimant_id, claimant_name, claimant_type,
                     status, claimed_at, last_activity_at, progress, blob)
                    VALUES
                    (:id, :issue_id, :claimant_id, :claimant_name, :claimant_type,
                     :status, :claimed_at, :last_activity_at, :progress, :blob)
                    """, row)
                conn.commit()
            finally:
                conn.close()

    def append_event(self, claim_id: str, issue_id: str, event_type: str, payload: dict) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO events (id, claim_id, issue_id, event_type, payload, occurred_at) VALUES (?,?,?,?,?,?)",
                    (f"evt-{uuid.uuid4().hex}", claim_id, issue_id, event_type, json.dumps(payload), time.time()),
                )
                conn.commit()
            finally:
                conn.close()

    def find_by_id(self, claim_id: str) -> Optional[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
            finally:
                conn.close()
        return self._row_to_claim(row) if row else None

    def find_by_issue_id(self, issue_id: str) -> Optional[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM claims WHERE issue_id = ? AND status NOT IN ('completed','released','expired') ORDER BY claimed_at DESC LIMIT 1",
                    (issue_id,),
                ).fetchone()
            finally:
                conn.close()
        return self._row_to_claim(row) if row else None

    def find_by_agent_id(self, agent_id: str) -> list[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT * FROM claims WHERE claimant_id = ?", (agent_id,)).fetchall()
            finally:
                conn.close()
        return [self._row_to_claim(r) for r in rows]

    def find_stealable(self, agent_type: Optional[AgentType] = None) -> list[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT * FROM claims WHERE status = 'stealable'").fetchall()
            finally:
                conn.close()
        claims = [self._row_to_claim(r) for r in rows]
        if agent_type is None:
            return claims
        return [
            c for c in claims
            if c.steal_info is None
            or c.steal_info.allowed_stealer_types is None
            or agent_type in c.steal_info.allowed_stealer_types
        ]

    def find_all_active(self) -> list[IssueClaim]:
        statuses = tuple(s.value for s in _ACTIVE_STATUSES)
        placeholder = ",".join("?" * len(statuses))
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(f"SELECT * FROM claims WHERE status IN ({placeholder})", statuses).fetchall()
            finally:
                conn.close()
        return [self._row_to_claim(r) for r in rows]

    def find_all(self) -> list[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT * FROM claims").fetchall()
            finally:
                conn.close()
        return [self._row_to_claim(r) for r in rows]

    def find_stale(self, since_timestamp: float) -> list[IssueClaim]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM claims WHERE last_activity_at < ? AND status NOT IN ('completed','released','expired','stealable')",
                    (since_timestamp,),
                ).fetchall()
            finally:
                conn.close()
        return [self._row_to_claim(r) for r in rows]

    def count_by_agent(self, agent_id: str) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM claims WHERE claimant_id = ? AND status NOT IN ('completed','released','expired')",
                    (agent_id,),
                ).fetchone()
            finally:
                conn.close()
        return row["cnt"] if row else 0

    def get_events(self, claim_id: str) -> list[dict]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM events WHERE claim_id = ? ORDER BY occurred_at", (claim_id,)
                ).fetchall()
            finally:
                conn.close()
        return [{"id": r["id"], "event_type": r["event_type"], "payload": json.loads(r["payload"]), "occurred_at": r["occurred_at"]} for r in rows]
