"""SQLCipher connection owner and schema for VECTOR contacts data."""
from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from core.memory.db_utils import apply_pragmas
from core.runtime_paths import data_path

CONTACTS_DB_PATH = data_path("contacts.db")
_CONTACT_TABLES = ("contacts", "interactions")

CREATE_CONTACTS = """CREATE TABLE IF NOT EXISTS contacts (
    name TEXT PRIMARY KEY,
    phone TEXT,
    email TEXT,
    notes TEXT,
    added_at TEXT,
    last_contacted TEXT,
    contact_count INTEGER DEFAULT 0
)"""
CREATE_INTERACTIONS = """CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_name TEXT,
    interaction_type TEXT,
    content TEXT,
    timestamp TEXT
)"""

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
        logger.warning("[VECTOR][relationships] SQLCipher unavailable -- contacts will be stored UNENCRYPTED")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _get_db_key() -> str:
    from core.memory.episodic import _get_db_key as _episodic_get_db_key
    return _episodic_get_db_key()


def _looks_like_plaintext_sqlite(path: Path) -> bool:
    try:
        return path.read_bytes()[:16] == b"SQLite format 3\x00"
    except OSError:
        return False


def _configure_sqlcipher_connection(conn) -> None:
    conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
    conn.execute("PRAGMA cipher_page_size = 4096")
    apply_pragmas(conn)


def _create_tables_on(conn) -> None:
    conn.execute(CREATE_CONTACTS)
    conn.execute(CREATE_INTERACTIONS)
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


def _migrate_plaintext_contacts_db_to_sqlcipher(path: Path):
    backup_path = Path(f"{path}.plaintext.bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup_path)
    os.remove(path)
    logger.warning("[VECTOR][relationships] Migrating plaintext contacts DB; backup kept at {}", backup_path)
    conn = sqlcipher.connect(str(path), check_same_thread=False)
    try:
        _configure_sqlcipher_connection(conn)
        _create_tables_on(conn)
        plain_conn = sqlite3.connect(str(backup_path), check_same_thread=False)
        try:
            existing = {row[0] for row in plain_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in _CONTACT_TABLES:
                if table not in existing:
                    continue
                columns = [row[1] for row in plain_conn.execute(f'PRAGMA table_info("{table}")')]
                quoted = ", ".join(f'"{column}"' for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = plain_conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
                if rows:
                    conn.executemany(f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({placeholders})', rows)
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


def get_connection(db_path: str | Path | None = None):
    path = Path(db_path) if db_path is not None else data_path("contacts.db")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _USE_SQLCIPHER:
        conn = _migrate_plaintext_contacts_db_to_sqlcipher(path) if _looks_like_plaintext_sqlite(path) else _open_sqlcipher_connection(path)
        conn.row_factory = sqlcipher.Row
        return conn
    conn = sqlite3.connect(str(path), check_same_thread=False)
    apply_pragmas(conn)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(db_path: str | Path | None = None) -> None:
    conn = get_connection(db_path)
    try:
        _create_tables_on(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    init_schema()
