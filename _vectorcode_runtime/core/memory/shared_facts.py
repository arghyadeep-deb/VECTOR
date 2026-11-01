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
from core.memory.db_utils import apply_pragmas
import sqlite3
import json
import time
from contextlib import contextmanager
from pathlib import Path
from loguru import logger
from core.memory.db_utils import configured_db_path

_DB_PATH = configured_db_path()


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

    @staticmethod
    def _row_class(conn):
        """sqlite3.Row rejects sqlcipher cursors — pick the driver's own Row.

        Same trap documented in districts/emergency/log.py:_row_class() and
        districts/data_analytics/data_engineer.py:_open_db(): sqlite3.Row raises
        "Row() argument 1 must be sqlite3.Cursor, not sqlcipher3.dbapi2.Cursor"
        when handed a cursor from the sqlcipher3/pysqlcipher3 driver.
        """
        mod = type(conn).__module__
        if mod.startswith("sqlcipher3"):
            from sqlcipher3 import dbapi2
            return dbapi2.Row
        if mod.startswith("pysqlcipher3"):
            from pysqlcipher3 import dbapi2
            return dbapi2.Row
        return sqlite3.Row

    def _open_conn(self) -> sqlite3.Connection:
        """Open a connection to self._db — SQLCipher-keyed when the main DB is
        encrypted (2026-08-05 fix: this used to open the encrypted DB with plain
        sqlite3.connect(), which raised "file is not a database" on every call —
        the entire Gap-8 shared-fact store was a silent no-op in production).

        Not the shared singleton from episodic.get_db_connection(): every method
        below opens+closes its own connection per operation (see _conn()), so
        handing out and having callers close the shared singleton would take the
        rest of VECTOR's memory access down with it. An own keyed connection is
        the right shape here, matching the existing precedent in
        districts/emergency/log.py:_open_conn() and
        districts/data_analytics/data_engineer.py:_open_db().
        """
        from core.memory import episodic

        if getattr(episodic, "_USE_SQLCIPHER", False):
            conn = episodic._open_sqlcipher_connection(self._db)
        else:
            conn = sqlite3.connect(self._db, timeout=10, check_same_thread=False)
        apply_pragmas(conn)
        conn.row_factory = self._row_class(conn)
        return conn

    @contextmanager
    def _conn(self):
        """Context manager yielding a connection: commits/rolls back like the
        old `with self._conn() as conn:` call sites expect, and additionally
        closes the connection afterward (each call opens a fresh one — nothing
        else reuses or closes it, so not closing here would leak a connection,
        plus a SQLCipher key derivation, on every SharedFacts call)."""
        conn = self._open_conn()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

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
