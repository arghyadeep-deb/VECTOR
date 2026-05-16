"""
Email SQLite schema — Python port of agentic-inbox/workers/db/schema.ts.

Creates and manages the local email database used by VECTOR's email district.
Mirrors the Durable Object schema exactly so data is compatible if synced
between the local SQLite and the cloud Cloudflare D1 instance.

Tables: folders, emails, attachments
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

EMAIL_DB_PATH = Path.home() / ".vector" / "email.db"

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


def get_connection(db_path: Path = EMAIL_DB_PATH) -> sqlite3.Connection:
    """Open (or create) the email database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(db_path: Path = EMAIL_DB_PATH) -> None:
    """Create all tables, indexes, and default folders if they don't exist."""
    conn = get_connection(db_path)
    with conn:
        conn.execute(CREATE_FOLDERS)
        conn.execute(CREATE_EMAILS)
        conn.execute(CREATE_ATTACHMENTS)
        for idx in CREATE_INDEXES:
            try:
                conn.execute(idx)
            except sqlite3.OperationalError:
                pass  # FTS5 may not be available in all builds
        # Seed default folders
        for fid, name, deletable in DEFAULT_FOLDERS:
            conn.execute(
                "INSERT OR IGNORE INTO folders(id, name, is_deletable) VALUES (?, ?, ?)",
                (fid, name, deletable),
            )
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
