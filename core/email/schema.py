"""
Email SQLite schema — Python port of agentic-inbox/workers/db/schema.ts.

Creates and manages the local email database used by VECTOR's email district.
Mirrors the Durable Object schema exactly so data is compatible if synced
between the local SQLite and the cloud Cloudflare D1 instance.

Tables: folders, emails, attachments
"""
from __future__ import annotations

from core.memory.db_utils import apply_pragmas, configured_db_path
__all__ = [
    "CREATE_ATTACHMENTS",
    "CREATE_EMAILS",
    "CREATE_FOLDERS",
    "CREATE_INDEXES",
    "DEFAULT_FOLDERS",
    "EMAIL_DB_PATH",
    "get_connection",
    "init_schema",
]


import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
        logger.warning(
            "[VECTOR][email] SQLCipher not available -- email correspondence "
            "will be stored UNENCRYPTED. Install sqlcipher3."
        )

EMAIL_DB_PATH = configured_db_path().with_name("email.db")

CREATE_FOLDERS = """
CREATE TABLE IF NOT EXISTS folders (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    is_deletable INTEGER NOT NULL DEFAULT 1
)"""

CREATE_EMAILS = """
CREATE TABLE IF NOT EXISTS emails (
    id               TEXT PRIMARY KEY,
    folder_id        TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    subject          TEXT,
    sender           TEXT,
    recipient        TEXT,
    cc               TEXT,
    bcc              TEXT,
    date             TEXT,
    read             INTEGER DEFAULT 0,
    starred          INTEGER DEFAULT 0,
    body             TEXT,
    in_reply_to      TEXT,
    email_references TEXT,
    thread_id        TEXT,
    message_id       TEXT,
    raw_headers      TEXT
)"""

CREATE_ATTACHMENTS = """
CREATE TABLE IF NOT EXISTS attachments (
    id          TEXT PRIMARY KEY,
    email_id    TEXT NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    filename    TEXT NOT NULL,
    mimetype    TEXT NOT NULL,
    size        INTEGER NOT NULL,
    content_id  TEXT,
    disposition TEXT
)"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_emails_folder   ON emails(folder_id)",
    "CREATE INDEX IF NOT EXISTS idx_emails_thread   ON emails(thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_emails_date     ON emails(date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_emails_sender   ON emails(sender)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(id, subject, body, sender, content=emails)",
]

DEFAULT_FOLDERS = [
    ("inbox",   "Inbox",   0),
    ("sent",    "Sent",    0),
    ("draft",   "Draft",   0),
    ("archive", "Archive", 0),
    ("trash",   "Trash",   0),
    ("spam",    "Spam",    0),
]

_EMAIL_TABLES = ("folders", "emails", "attachments")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _get_db_key() -> str:
    """Use the owner-managed encryption key shared by VECTOR stores."""
    from core.memory.episodic import _get_db_key as _episodic_get_db_key
    return _episodic_get_db_key()


def _looks_like_plaintext_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as database:
            return database.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _configure_sqlcipher_connection(conn) -> None:
    conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
    conn.execute("PRAGMA cipher_page_size = 4096")
    apply_pragmas(conn, foreign_keys=True)


def _create_schema_on(conn) -> None:
    conn.execute(CREATE_FOLDERS)
    conn.execute(CREATE_EMAILS)
    conn.execute(CREATE_ATTACHMENTS)
    for index in CREATE_INDEXES:
        try:
            conn.execute(index)
        except sqlite3.OperationalError:
            pass
    for folder_id, name, deletable in DEFAULT_FOLDERS:
        conn.execute(
            "INSERT OR IGNORE INTO folders(id, name, is_deletable) VALUES (?, ?, ?)",
            (folder_id, name, deletable),
        )
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


def _migrate_plaintext_email_db_to_sqlcipher(path: Path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = Path(f"{path}.plaintext.bak.{stamp}")
    shutil.copy2(path, backup_path)
    os.remove(path)
    logger.warning(
        "[VECTOR][email] Migrating plaintext email DB to SQLCipher; backup kept at {}",
        backup_path,
    )
    conn = sqlcipher.connect(str(path), check_same_thread=False)
    try:
        _configure_sqlcipher_connection(conn)
        _create_schema_on(conn)
        plain_conn = sqlite3.connect(str(backup_path), check_same_thread=False)
        try:
            existing = {row[0] for row in plain_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in _EMAIL_TABLES:
                if table not in existing:
                    continue
                columns = [row[1] for row in plain_conn.execute(f'PRAGMA table_info("{table}")')]
                if not columns:
                    continue
                quoted = ", ".join(f'"{column}"' for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = plain_conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
                if rows:
                    conn.executemany(
                        f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({placeholders})',
                        rows,
                    )
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


def get_connection(db_path: Path = EMAIL_DB_PATH):
    """Open (or create) the email database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if _USE_SQLCIPHER:
        if _looks_like_plaintext_sqlite(db_path):
            conn = _migrate_plaintext_email_db_to_sqlcipher(db_path)
        else:
            conn = _open_sqlcipher_connection(db_path)
        conn.row_factory = sqlcipher.Row
    else:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        apply_pragmas(conn, foreign_keys=True)
        conn.row_factory = sqlite3.Row
    return conn


def init_schema(db_path: Path = EMAIL_DB_PATH) -> None:
    """Create all tables, indexes, and default folders if they don't exist."""
    conn = get_connection(db_path)
    _create_schema_on(conn)
    conn.close()


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    init_schema()
    conn = get_connection()
    folders = conn.execute("SELECT id, name FROM folders ORDER BY id").fetchall()
    emails_count = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    conn.close()

    print(f"[OK] schema: {len(folders)} default folders created")
    for f in folders:
        print(f"  {f['id']}: {f['name']}")
    print(f"[OK] emails: {emails_count} total")
    print("schema.py OK")
