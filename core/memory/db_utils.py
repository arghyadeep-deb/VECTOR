"""Shared SQLite connection utilities for VECTOR memory stores.

Single source of truth for the PRAGMA triplet used by every store.
Import and call apply_pragmas(conn) immediately after opening a connection.
"""
from __future__ import annotations

import sqlite3


def apply_pragmas(conn: sqlite3.Connection, *, foreign_keys: bool = False) -> None:
    """Apply the standard VECTOR PRAGMA set to a new SQLite connection.

    WAL mode + 5s busy timeout make concurrent writers safe.
    foreign_keys=True is opt-in (not all schemas need it).
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
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
