"""Shared SQLite connection utilities for VECTOR memory stores.

Single source of truth for the PRAGMA triplet used by every store.
Import and call apply_pragmas(conn) immediately after opening a connection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def configured_db_path() -> Path:
    """Return the canonical VECTOR memory DB path.

    ``VECTOR_DB_PATH`` is honored for repair/tests; otherwise the validated
    app config is the source of truth. The final fallback is only for unusual
    partial-import situations where config is unavailable.
    """
    import os

    override = os.environ.get("VECTOR_DB_PATH")
    if override:
        return Path(override)

    try:
        from core.config import CONFIG
        return Path(str(CONFIG["db_path"]))
    except Exception:
        return Path(__file__).resolve().parents[2] / "vector_memory.db"


def apply_pragmas(conn: sqlite3.Connection, *, foreign_keys: bool = False) -> None:
    """Apply the standard VECTOR PRAGMA set to a new SQLite connection.

    WAL mode + 5s busy timeout make concurrent writers safe.
    foreign_keys=True is opt-in (not all schemas need it).
    """
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode=DELETE")
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys=ON")


if __name__ == "__main__":
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = sqlite3.connect(path)
        apply_pragmas(conn)
        row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal", f"expected wal, got {row[0]}"
        print("✅ db_utils OK")
    finally:
        os.unlink(path)
