"""LangGraph checkpoint support for resumable analysis runs.

Per-ticker SQLite databases so concurrent tickers don't contend.
"""

from __future__ import annotations
from core.memory.db_utils import apply_pragmas
from loguru import logger

__all__ = [
    "checkpoint_step",
    "clear_all_checkpoints",
    "clear_checkpoint",
    "get_checkpointer",
    "has_checkpoint",
    "thread_id",
]


import hashlib
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from langgraph.checkpoint.sqlite import SqliteSaver

from core.trading.dataflows.utils import safe_ticker_component

_lock = threading.RLock()

try:
    import sqlcipher3 as sqlcipher
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlcipher
    except ImportError:
        sqlcipher = None


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _get_db_key() -> str:
    from core.memory.episodic import _get_db_key as _episodic_get_db_key

    key = _episodic_get_db_key()
    if not key:
        raise RuntimeError("[VECTOR][trading_checkpoint] encryption key unavailable")
    return key


def _require_sqlcipher() -> None:
    if sqlcipher is None:
        raise RuntimeError(
            "[VECTOR][trading_checkpoint] SQLCipher unavailable; refusing plaintext checkpoint storage"
        )


def _looks_like_plaintext_sqlite(path: Path) -> bool:
    try:
        return path.read_bytes()[:16] == b"SQLite format 3\x00"
    except OSError:
        return False


def _configure_connection(conn) -> None:
    conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
    conn.execute("PRAGMA cipher_page_size = 4096")
    apply_pragmas(conn)


def _open_sqlcipher_connection(path: Path):
    _require_sqlcipher()
    conn = sqlcipher.connect(str(path), check_same_thread=False)
    try:
        _configure_connection(conn)
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.row_factory = sqlcipher.Row
        return conn
    except Exception:
        conn.close()
        raise


def _copy_langgraph_tables(plain_path: Path, encrypted_conn) -> None:
    plain_conn = sqlite3.connect(str(plain_path), check_same_thread=False)
    try:
        existing = {
            row[0]
            for row in plain_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in ("checkpoints", "writes"):
            if table not in existing:
                continue
            columns = [
                row[1]
                for row in plain_conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            ]
            if not columns:
                continue
            quoted = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            rows = plain_conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
            if rows:
                encrypted_conn.executemany(
                    f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({placeholders})',
                    rows,
                )
        encrypted_conn.commit()
    finally:
        plain_conn.close()


def _migrate_plaintext_checkpoint(path: Path):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    backup = Path(f"{path}.plaintext.bak.{stamp}")
    shutil.copy2(path, backup)
    os.remove(path)
    logger.warning(
        "[VECTOR][trading_checkpoint] migrating plaintext DB; backup kept at {}",
        backup,
    )
    conn = _open_sqlcipher_connection(path)
    try:
        SqliteSaver(conn).setup()
        _copy_langgraph_tables(backup, conn)
        return conn
    except Exception:
        conn.close()
        path.unlink(missing_ok=True)
        shutil.copy2(backup, path)
        raise


def _db_path(data_dir: str | Path, ticker: str) -> Path:
    """Return the SQLite checkpoint DB path for a ticker."""
    # Reject ticker values that would escape the checkpoints directory.
    safe = safe_ticker_component(ticker).upper()
    p = Path(data_dir) / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{safe}.db"


def thread_id(ticker: str, date: str) -> str:
    """Deterministic thread ID for a ticker+date pair."""
    return hashlib.sha256(f"{ticker.upper()}:{date}".encode()).hexdigest()[:16]


@contextmanager
def get_checkpointer(data_dir: str | Path, ticker: str) -> Generator[SqliteSaver, None, None]:
    """Context manager yielding a SqliteSaver backed by a per-ticker DB."""
    db = _db_path(data_dir, ticker)
    conn = (
        _migrate_plaintext_checkpoint(db)
        if db.exists() and _looks_like_plaintext_sqlite(db)
        else _open_sqlcipher_connection(db)
    )
    try:
        saver = SqliteSaver(conn)
        saver.setup()
        yield saver
    finally:
        conn.close()


def has_checkpoint(data_dir: str | Path, ticker: str, date: str) -> bool:
    """Check whether a resumable checkpoint exists for ticker+date."""
    return checkpoint_step(data_dir, ticker, date) is not None


def checkpoint_step(data_dir: str | Path, ticker: str, date: str) -> int | None:
    """Return the step number of the latest checkpoint, or None if none exists."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return None
    tid = thread_id(ticker, date)
    with get_checkpointer(data_dir, ticker) as saver:
        config = {"configurable": {"thread_id": tid}}
        cp = saver.get_tuple(config)
        if cp is None:
            return None
        return cp.metadata.get("step")


def clear_all_checkpoints(data_dir: str | Path) -> int:
    """Remove all checkpoint DBs. Returns number of files deleted."""
    cp_dir = Path(data_dir) / "checkpoints"
    if not cp_dir.exists():
        return 0
    dbs = list(cp_dir.glob("*.db"))
    for db in dbs:
        db.unlink()
        # A stale -wal/-shm left beside a deleted DB can be replayed into the next
        # DB created at the same path, resurrecting a cleared checkpoint.
        for suffix in ("-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)
    return len(dbs)


def clear_checkpoint(data_dir: str | Path, ticker: str, date: str) -> None:
    """Remove checkpoint for a specific ticker+date by deleting the thread's rows."""
    db = _db_path(data_dir, ticker)
    if not db.exists():
        return
    tid = thread_id(ticker, date)
    with _lock:
        conn = _open_sqlcipher_connection(db)
        try:
            for table in ("writes", "checkpoints"):
                conn.execute(f"DELETE FROM {table} WHERE thread_id = ?", (tid,))
            conn.commit()
        except Exception as e:
            logger.warning(
                "[VECTOR][trading_checkpoint] could not clear checkpoint for {} on {}: {}",
                ticker, date, e,
            )
        finally:
            conn.close()
