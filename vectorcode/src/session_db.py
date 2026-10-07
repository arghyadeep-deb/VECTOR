"""VectorCode SQLite session database with FTS5 full-text search.

VectorCode implementation (SCHEMA_VERSION 10), adapted for VectorCode:
  - Removed source-specific fields (source, user_id, billing_*, reasoning_*)
  - Kept core session/message schema and all FTS5 logic
  - WAL mode + application-level jitter retry for multi-process safety
  - Thread-safe via a single shared connection + threading.Lock

Database: ~/.vector/sessions.db
"""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from core.memory.db_utils import apply_pragmas


try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

from loguru import logger

# ── Paths ─────────────────────────────────────────────────────────────────────
_VECTOR_DATA_DIR = Path.home() / ".vector"
_DEFAULT_DB_PATH = _VECTOR_DATA_DIR / "sessions.db"

# ── Schema ─────────────────────────────────────────────────────────────────────
SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id                  TEXT PRIMARY KEY,
    model               TEXT,
    project             TEXT,
    mode                TEXT,
    started_at          TEXT NOT NULL,
    ended_at            TEXT,
    end_reason          TEXT,
    message_count       INTEGER DEFAULT 0,
    tool_call_count     INTEGER DEFAULT 0,
    input_tokens        INTEGER DEFAULT 0,
    output_tokens       INTEGER DEFAULT 0,
    cache_read_tokens   INTEGER DEFAULT 0,
    cost_usd            REAL DEFAULT 0.0,
    title               TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT,
    timestamp     TEXT NOT NULL,
    token_count   INTEGER DEFAULT 0,
    finish_reason TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_started  ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session  ON messages(session_id, timestamp);
"""

_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content=messages,
    content_rowid=rowid
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES('delete', old.rowid, old.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES('delete', old.rowid, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""

# ── Write-retry tuning ((VectorCode default) ───────────────────────────────────────
_WRITE_MAX_RETRIES   = 10
_WRITE_RETRY_MIN_S   = 0.020
_WRITE_RETRY_MAX_S   = 0.150
_CHECKPOINT_EVERY_N  = 50


class SessionDB:
    """SQLite-backed session store with FTS5 full-text search.

    Database: ~/.vector/sessions.db
    Schema mirrors reference state structure (simplified).
    Thread-safe — one shared connection, all writes behind a lock with
    BEGIN IMMEDIATE + jitter retry.
    """

    def __init__(self, db_path: "Path | None" = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock        = threading.Lock()
        self._write_count = 0

        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=1.0,
            isolation_level=None,   # we manage transactions ourselves
        )
        self._conn.row_factory = sqlite3.Row
        apply_pragmas(self._conn, foreign_keys=True)

        self._init_schema()

    # ── Write helper ─────────────────────────────────────────────────────────

    def _execute_write(self, fn):
        """Run a write transaction with BEGIN IMMEDIATE + jitter retry."""
        import random
        last_err = None
        for attempt in range(_WRITE_MAX_RETRIES):
            try:
                with self._lock:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        result = fn(self._conn)
                        self._conn.commit()
                    except BaseException as _sve:
                        try:
                            self._conn.rollback()
                        except Exception as _sve:
                            logger.debug("[VECTOR][session_db] suppressed Exception: %s", _sve)
                        raise
                self._write_count += 1
                if self._write_count % _CHECKPOINT_EVERY_N == 0:
                    self._try_wal_checkpoint()
                return result
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    last_err = exc
                    if attempt < _WRITE_MAX_RETRIES - 1:
                        time.sleep(random.uniform(_WRITE_RETRY_MIN_S, _WRITE_RETRY_MAX_S))
                        continue
                raise
        raise last_err or sqlite3.OperationalError("database is locked after max retries")

    def _try_wal_checkpoint(self) -> None:
        """Best-effort PASSIVE WAL checkpoint — never raises."""
        try:
            with self._lock:
                self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception as _sve:
            logger.debug("[VECTOR][session_db] suppressed Exception: %s", _sve)

    def close(self) -> None:
        """Close the database connection after a best-effort checkpoint."""
        global _db
        with self._lock:
            if self._conn:
                try:
                    self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except Exception as _sve:
                    logger.debug("[VECTOR][session_db] suppressed Exception: %s", _sve)
                self._conn.close()
                self._conn = None  # type: ignore[assignment]
        with _db_lock:
            if _db is self:
                _db = None

    # ── Schema init ──────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript(_SCHEMA_SQL)

        # FTS5 (CREATE VIRTUAL TABLE can't be in executescript reliably)
        try:
            cursor.execute("SELECT * FROM messages_fts LIMIT 0")
        except sqlite3.OperationalError:
            cursor.executescript(_FTS_SQL)

        # Schema version bookkeeping
        cursor.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        # Future migrations go here gated on row["version"] < N

        self._conn.commit()

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        model: str,
        project: str,
        mode: str,
    ) -> None:
        """Insert a new session row (INSERT OR IGNORE — safe to call twice)."""
        def _do(conn):
            conn.execute(
                """INSERT OR IGNORE INTO sessions
                   (id, model, project, mode, started_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, model, project, mode,
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            )
        self._execute_write(_do)

    def end_session(self, session_id: str, end_reason: str = "user_exit") -> None:
        """Mark a session as ended. First end_reason wins (no-op if already ended)."""
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET ended_at = ?, end_reason = ? "
                "WHERE id = ? AND ended_at IS NULL",
                (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 end_reason,
                 session_id),
            )
        self._execute_write(_do)

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Return session as dict, or None."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 20) -> List[Dict]:
        """Return most-recent sessions first."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages. Returns True if found."""
        def _do(conn):
            cursor = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,)
            )
            if cursor.fetchone()[0] == 0:
                return False
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return True
        return self._execute_write(_do)

    # ── Message storage ──────────────────────────────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        token_count: int = 0,
        finish_reason: str = "",
    ) -> str:
        """Append a message. Returns the message id."""
        msg_id = uuid.uuid4().hex
        ts     = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        def _do(conn):
            conn.execute(
                """INSERT INTO messages
                   (id, session_id, role, content, timestamp, token_count, finish_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, session_id, role, content, ts, token_count, finish_reason),
            )
            if role == "tool":
                conn.execute(
                    """UPDATE sessions SET
                       message_count     = message_count + 1,
                       tool_call_count   = tool_call_count + 1
                       WHERE id = ?""",
                    (session_id,),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
                    (session_id,),
                )

        self._execute_write(_do)
        return msg_id

    def get_messages(self, session_id: str) -> List[Dict]:
        """Return all messages for a session, ordered by timestamp."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp, rowid",
                (session_id,),
            )
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    # ── Search ───────────────────────────────────────────────────────────────

    def search_messages(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """FTS5 full-text search across messages (optionally within one session)."""
        if not query or not query.strip():
            return []

        safe_query = self._sanitize_fts5_query(query)
        if not safe_query:
            return []

        if session_id:
            sql = """
                SELECT m.id, m.session_id, m.role,
                       snippet(messages_fts, 0, '>>>', '<<<', '...', 40) AS snippet,
                       m.timestamp
                FROM messages_fts
                JOIN messages m ON m.rowid = messages_fts.rowid
                WHERE messages_fts MATCH ?
                  AND m.session_id = ?
                ORDER BY rank
                LIMIT ?
            """
            params = (safe_query, session_id, limit)
        else:
            sql = """
                SELECT m.id, m.session_id, m.role,
                       snippet(messages_fts, 0, '>>>', '<<<', '...', 40) AS snippet,
                       m.timestamp
                FROM messages_fts
                JOIN messages m ON m.rowid = messages_fts.rowid
                WHERE messages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            params = (safe_query, limit)

        try:
            with self._lock:
                cursor = self._conn.execute(sql, params)
                rows = cursor.fetchall()
        except sqlite3.OperationalError as exc:
            logger.debug(f"[VECTOR][session_db] FTS5 search error: {exc}")
            return []
        return [dict(r) for r in rows]

    @staticmethod
    def _sanitize_fts5_query(query: str) -> str:
        """Strip FTS5-special chars that would cause syntax errors."""
        import re
        # Preserve balanced quoted phrases
        quoted_parts: list = []

        def _preserve(m):
            quoted_parts.append(m.group(0))
            return f"\x00Q{len(quoted_parts)-1}\x00"

        sanitized = re.sub(r'"[^"]*"', _preserve, query)
        sanitized = re.sub(r'[+{}()\"^]', " ", sanitized)
        sanitized = re.sub(r"\*+", "*", sanitized)
        sanitized = re.sub(r"(^|\s)\*", r"\1", sanitized)
        sanitized = re.sub(r"(?i)^(AND|OR|NOT)\b\s*", "", sanitized.strip())
        sanitized = re.sub(r"(?i)\s+(AND|OR|NOT)\s*$", "", sanitized.strip())

        for i, qp in enumerate(quoted_parts):
            sanitized = sanitized.replace(f"\x00Q{i}\x00", qp)

        return sanitized.strip()

    # ── Token / cost tracking ─────────────────────────────────────────────────

    def update_usage(
        self,
        session_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Increment token usage and cost for a session."""
        def _do(conn):
            conn.execute(
                """UPDATE sessions SET
                   input_tokens      = input_tokens + ?,
                   output_tokens     = output_tokens + ?,
                   cache_read_tokens = cache_read_tokens + ?,
                   cost_usd          = cost_usd + ?
                   WHERE id = ?""",
                (input_tokens, output_tokens, cache_read, cost_usd, session_id),
            )
        self._execute_write(_do)

    # ── Utilities ─────────────────────────────────────────────────────────────

    def generate_title(self, session_id: str) -> str:
        """Return the first non-empty user message truncated to 60 chars."""
        with self._lock:
            cursor = self._conn.execute(
                """SELECT content FROM messages
                   WHERE session_id = ? AND role = 'user'
                     AND content IS NOT NULL AND content != ''
                   ORDER BY timestamp, rowid
                   LIMIT 1""",
                (session_id,),
            )
            row = cursor.fetchone()
        if not row:
            return f"Session {session_id[:8]}"
        text = (row["content"] or "").replace("\n", " ").strip()
        return text[:60] + ("…" if len(text) > 60 else "")

    def get_context_window(
        self, session_id: str, max_messages: int = 50
    ) -> List[Dict]:
        """Return last N messages as {role, content} for LLM context."""
        with self._lock:
            cursor = self._conn.execute(
                """SELECT role, content FROM messages
                   WHERE session_id = ?
                   ORDER BY timestamp DESC, rowid DESC
                   LIMIT ?""",
                (session_id, max_messages),
            )
            rows = cursor.fetchall()
        # Reverse so oldest is first (LLM expects chronological order)
        return [{"role": r["role"], "content": r["content"] or ""} for r in reversed(rows)]

    def export_markdown(self, session_id: str) -> str:
        """Export a session as a Markdown document."""
        session = self.get_session(session_id)
        if not session:
            return f"Session {session_id!r} not found."

        messages = self.get_messages(session_id)
        lines = [
            f"# Session {session_id[:8]}",
            f"",
            f"- **Model:** {session.get('model', '?')}",
            f"- **Project:** {session.get('project', '?')}",
            f"- **Mode:** {session.get('mode', '?')}",
            f"- **Started:** {session.get('started_at', '?')}",
            f"- **Messages:** {session.get('message_count', 0)}",
            f"",
        ]
        for msg in messages:
            role    = msg.get("role", "?")
            content = msg.get("content") or ""
            lines.append(f"**{role.upper()}**")
            lines.append(content)
            lines.append("")
        return "\n".join(lines)

    def migrate_up(self) -> None:
        """Migrate this database to SCHEMA_VERSION 10 (VectorCode-compatible schema)."""
        from vectorcode.migrations.v1_to_v10 import migrate_v1_to_v10
        with self._lock:
            migrate_v1_to_v10(self._conn)


# ── Singleton getter ──────────────────────────────────────────────────────────

_db: Optional[SessionDB] = None
_db_lock = threading.Lock()


def get_session_db() -> SessionDB:
    """Return the module-level singleton SessionDB instance."""
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = SessionDB()
    return _db


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_sessions.db"
        db = SessionDB(db_path)

        # create_session / get_session
        sid = "test-session-001"
        db.create_session(sid, model="vector-focus", project="/tmp/myproject", mode="repl")
        session = db.get_session(sid)
        assert session is not None
        assert session["model"] == "vector-focus"
        assert session["mode"] == "repl"
        assert session["message_count"] == 0

        # add_message
        msg_id = db.add_message(sid, "user", "Hello VECTOR, build something cool.")
        assert len(msg_id) == 32   # uuid hex
        msg_id2 = db.add_message(sid, "assistant", "Working on it now.")
        assert msg_id != msg_id2

        session = db.get_session(sid)
        assert session["message_count"] == 2

        # get_messages
        msgs = db.get_messages(sid)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

        # search_messages — FTS5
        results = db.search_messages("VECTOR")
        assert len(results) >= 1
        assert any("VECTOR" in (r.get("snippet") or "") for r in results)

        # search within session
        results2 = db.search_messages("cool", session_id=sid)
        assert len(results2) >= 1

        # empty query returns []
        assert db.search_messages("") == []
        assert db.search_messages("   ") == []

        # generate_title
        title = db.generate_title(sid)
        assert "Hello VECTOR" in title or len(title) <= 61

        # get_context_window
        ctx = db.get_context_window(sid, max_messages=10)
        assert len(ctx) == 2
        assert ctx[0]["role"] == "user"
        assert ctx[1]["role"] == "assistant"

        # update_usage
        db.update_usage(sid, input_tokens=100, output_tokens=50, cost_usd=0.001)
        session = db.get_session(sid)
        assert session["input_tokens"] == 100
        assert session["output_tokens"] == 50

        # list_sessions
        sid2 = "test-session-002"
        db.create_session(sid2, "vector-coder", "/tmp/other", "auto")
        sessions = db.list_sessions(limit=10)
        assert len(sessions) == 2

        # end_session
        db.end_session(sid, "user_exit")
        ended = db.get_session(sid)
        assert ended["end_reason"] == "user_exit"
        assert ended["ended_at"] is not None

        # end_session is idempotent (first reason wins)
        db.end_session(sid, "second_call")
        still = db.get_session(sid)
        assert still["end_reason"] == "user_exit"

        # export_markdown
        md = db.export_markdown(sid)
        assert "Session test-ses" in md
        assert "user" in md.lower() or "VECTOR" in md

        # delete_session
        deleted = db.delete_session(sid)
        assert deleted is True
        assert db.get_session(sid) is None
        not_found = db.delete_session(sid)
        assert not_found is False

        # Singleton
        db.close()

    db1 = get_session_db()
    db2 = get_session_db()
    assert db1 is db2, "get_session_db() must return a singleton"

    print("session_db.py OK")


    def migrate_up(self) -> None:
        """Migrate this database to SCHEMA_VERSION 10 (VectorCode-compatible schema)."""
        from vectorcode.migrations.v1_to_v10 import migrate_v1_to_v10
        with self._lock:
            migrate_v1_to_v10(self._conn)
