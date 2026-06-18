"""
core/memory/shared_facts.py — Cross-agent fact consensus store (Gap 8).

SQLite-backed. Higher confidence wins on conflict. Agents can vote on facts.
All agents check this before forming conclusions.

Usage:
    from core.memory.shared_facts import SharedFacts
    sf = SharedFacts()
    sf.set("tax_deadline", "April 15", confidence=0.9, source_agent="finance_agent")
    val = sf.get("tax_deadline")   # → "April 15"
    sf.vote("tax_deadline", "April 15", voter="calendar_agent")
"""
import sqlite3
import json
import time
from pathlib import Path
from loguru import logger
from core.config import CONFIG

_DB_PATH = Path(str(CONFIG.get("db_path", Path(__file__).parent.parent.parent / "vector_memory.db")))


class SharedFacts:
    _instance: "SharedFacts | None" = None

    def __init__(self, db_path: Path = _DB_PATH):
        self._db = str(db_path)
        self._init_db()

    @classmethod
    def get(cls) -> "SharedFacts":
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
                CREATE TABLE IF NOT EXISTS shared_facts (
                    fact_key     TEXT PRIMARY KEY,
                    value        TEXT NOT NULL,
                    confidence   REAL NOT NULL DEFAULT 0.5,
                    source_agent TEXT NOT NULL DEFAULT 'unknown',
                    votes        INTEGER NOT NULL DEFAULT 1,
                    updated_at   REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fact_votes (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact_key     TEXT NOT NULL,
                    value        TEXT NOT NULL,
                    voter        TEXT NOT NULL,
                    voted_at     REAL NOT NULL
                )
            """)

    def set(self, key: str, value: str, confidence: float = 0.5,
            source_agent: str = "unknown") -> None:
        """Set a fact. Higher confidence overwrites lower confidence."""
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT confidence FROM shared_facts WHERE fact_key = ?", (key,)
            ).fetchone()
            if existing and existing["confidence"] > confidence:
                logger.debug(
                    f"[VECTOR][shared_facts] {key}: existing confidence "
                    f"{existing['confidence']:.2f} > {confidence:.2f}, skipping"
                )
                return
            conn.execute("""
                INSERT INTO shared_facts (fact_key, value, confidence, source_agent, votes, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(fact_key) DO UPDATE SET
                    value=excluded.value,
                    confidence=excluded.confidence,
                    source_agent=excluded.source_agent,
                    updated_at=excluded.updated_at
            """, (key, str(value), confidence, source_agent, time.time()))
        logger.debug(f"[VECTOR][shared_facts] set {key}={value!r} conf={confidence:.2f} by {source_agent}")

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a fact value, or default if not found."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM shared_facts WHERE fact_key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def get_with_meta(self, key: str) -> dict | None:
        """Get fact with confidence, source, votes."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM shared_facts WHERE fact_key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def vote(self, key: str, value: str, voter: str) -> None:
        """Cast a vote for a fact value. Increases confidence if majority agrees."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO fact_votes (fact_key, value, voter, voted_at) VALUES (?, ?, ?, ?)",
                (key, value, voter, time.time()),
            )
            # Count votes for this value
            vote_count = conn.execute(
                "SELECT COUNT(*) FROM fact_votes WHERE fact_key = ? AND value = ?",
                (key, value),
            ).fetchone()[0]
            # Update confidence based on vote count (each vote adds 0.05, cap at 0.99)
            new_conf = min(0.99, 0.5 + vote_count * 0.05)
            conn.execute(
                "UPDATE shared_facts SET votes = ?, confidence = ? WHERE fact_key = ?",
                (vote_count, new_conf, key),
            )
        logger.debug(f"[VECTOR][shared_facts] vote: {voter} → {key}={value!r} (total votes: {vote_count})")

    def all_facts(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM shared_facts ORDER BY confidence DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete(self, key: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM shared_facts WHERE fact_key = ?", (key,))
