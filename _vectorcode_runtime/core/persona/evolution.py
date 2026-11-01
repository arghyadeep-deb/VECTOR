from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import os
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from core.config import CONFIG
from core.runtime_paths import data_path

__all__ = ["PersonaEvolution"]

_DB_DIR = data_path("persona")
_EVOLUTION_TABLES = ("evolution_signals", "trait_values")

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
        logger.warning("[VECTOR][persona_evolution] SQLCipher unavailable -- evolution data will be stored UNENCRYPTED")


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
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS evolution_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_type TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trait_values (
            trait TEXT PRIMARY KEY,
            value REAL NOT NULL DEFAULT 0.5,
            updated_at TEXT NOT NULL
        );
    """)
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


def _migrate_plaintext_evolution_db_to_sqlcipher(path: Path):
    backup_path = Path(f"{path}.plaintext.bak.{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup_path)
    os.remove(path)
    logger.warning("[VECTOR][persona_evolution] Migrating plaintext DB; backup kept at {}", backup_path)
    conn = sqlcipher.connect(str(path), check_same_thread=False)
    try:
        _configure_sqlcipher_connection(conn)
        _create_tables_on(conn)
        plain_conn = sqlite3.connect(str(backup_path), check_same_thread=False)
        try:
            existing = {row[0] for row in plain_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in _EVOLUTION_TABLES:
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


class PersonaEvolution:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _DB_DIR / "evolution.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        if _USE_SQLCIPHER:
            self._conn = _migrate_plaintext_evolution_db_to_sqlcipher(self._db_path) if _looks_like_plaintext_sqlite(self._db_path) else _open_sqlcipher_connection(self._db_path)
            self._conn.row_factory = sqlcipher.Row
        else:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            apply_pragmas(self._conn)
            self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_tables()

    def _init_tables(self) -> None:
        _create_tables_on(self._conn)

    def record_signal(self, signal_type: str, metadata: dict | None = None) -> None:
        import json
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO evolution_signals (signal_type, metadata, recorded_at) VALUES (?,?,?)",
                (signal_type, json.dumps(metadata or {}), now),
            )
            self._conn.commit()
            self._adjust_trait_from_signal(signal_type)
        logger.debug("[VECTOR][persona_evolution] signal recorded: {}", signal_type)

    def get_evolved_traits(self) -> dict[str, float]:
        rows = self._conn.execute("SELECT trait, value FROM trait_values").fetchall()
        return {r["trait"]: r["value"] for r in rows}

    def should_deepen(self) -> bool:
        count = self._conn.execute(
            "SELECT COUNT(*) FROM evolution_signals"
        ).fetchone()[0]
        return count > 0 and count % 50 == 0

    def get_evolution_level(self) -> float:
        total = self._conn.execute(
            "SELECT COUNT(*) FROM evolution_signals"
        ).fetchone()[0]
        level = min(1.0, total / 500.0)
        return round(level, 3)

    def close(self) -> None:
        self._conn.close()

    def _adjust_trait_from_signal(self, signal_type: str) -> None:
        _SIGNAL_TRAIT_MAP: dict[str, str] = {
            "owner_interaction": "confidence",
            "correct_prediction": "confidence",
            "owner_correction": "adaptiveness",
            "task_completed": "reliability",
        }
        trait = _SIGNAL_TRAIT_MAP.get(signal_type)
        if not trait:
            return
        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT value FROM trait_values WHERE trait=?", (trait,)
        ).fetchone()
        if existing:
            new_val = min(1.0, existing["value"] + 0.02)
            self._conn.execute(
                "UPDATE trait_values SET value=?, updated_at=? WHERE trait=?",
                (new_val, now, trait),
            )
        else:
            self._conn.execute(
                "INSERT INTO trait_values (trait, value, updated_at) VALUES (?,?,?)",
                (trait, 0.52, now),
            )
        self._conn.commit()
