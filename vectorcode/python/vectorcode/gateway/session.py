"""Gateway session management — session store, context, key building."""

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionSource:
    platform: str = ""
    chat_id: str = ""
    user_id: str = ""
    thread_id: str = ""
    guild_id: str = ""


@dataclass
class SessionContext:
    session_id: str = ""
    source: Optional[SessionSource] = None
    platform: str = ""
    connected_platforms: list[str] = field(default_factory=list)
    home_channels: dict[str, str] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)
    created_at: float = 0.0
    last_active: float = 0.0
    token_count: int = 0


class SessionStore:
    """SQLite-backed session store with JSONL fallback."""
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".vector" / "sessions.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                platform TEXT,
                source_json TEXT,
                messages TEXT,
                created_at REAL,
                last_active REAL,
                token_count INTEGER DEFAULT 0
            )
        """)
        self._conn.commit()

    def create_session(self, source: SessionSource) -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        self._conn.execute(
            "INSERT INTO sessions (id, platform, source_json, messages, created_at, last_active) VALUES (?,?,?,?,?,?)",
            (session_id, source.platform, json.dumps({"chat_id": source.chat_id, "user_id": source.user_id}),
             json.dumps([]), now, now),
        )
        self._conn.commit()
        return session_id

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        row = self._conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row: return None
        return SessionContext(
            session_id=row[0], platform=row[1],
            source=SessionSource(**json.loads(row[2])),
            messages=json.loads(row[3]), created_at=row[4],
            last_active=row[5], token_count=row[6] or 0,
        )

    def append_message(self, session_id: str, role: str, content: str):
        sess = self.get_session(session_id)
        if not sess: return
        sess.messages.append({"role": role, "content": content, "ts": time.time()})
        sess.last_active = time.time()
        sess.token_count += len(content) // 4
        self._conn.execute(
            "UPDATE sessions SET messages=?, last_active=?, token_count=? WHERE id=?",
            (json.dumps(sess.messages), sess.last_active, sess.token_count, session_id),
        )
        self._conn.commit()

    def list_sessions(self, limit: int = 20) -> list[SessionContext]:
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY last_active DESC LIMIT ?", (limit,)
        ).fetchall()
        return [SessionContext(
            session_id=r[0], platform=r[1],
            source=SessionSource(**json.loads(r[2])),
            messages=json.loads(r[3]), created_at=r[4],
            last_active=r[5], token_count=r[6] or 0,
        ) for r in rows]

    def delete_session(self, session_id: str):
        self._conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self._conn.commit()
