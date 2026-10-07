"""DigestStore -- SQLite-backed storage for pre-computed digest artifacts."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from core.memory.db_utils import apply_pragmas

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
            "[VECTOR][digest_store] SQLCipher not available -- digest content "
            "will be stored UNENCRYPTED. Install sqlcipher3 to encrypt."
        )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _get_db_key() -> str:
    from core.memory.episodic import _get_db_key as _episodic_get_db_key
    return _episodic_get_db_key()


def _looks_like_plaintext_sqlite(path: str) -> bool:
    try:
        with open(path, "rb") as file:
            return file.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _open_sqlcipher_connection(path: str):
    conn = sqlcipher.connect(path, check_same_thread=False)
    try:
        conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("SELECT count(*) FROM sqlite_master")
        return conn
    except Exception:
        conn.close()
        raise


def _create_digest_table_on(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            audio_path TEXT NOT NULL,
            sections TEXT NOT NULL,
            sources_used TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            model_used TEXT NOT NULL,
            voice_used TEXT NOT NULL,
            quality_score REAL NOT NULL DEFAULT 0.0,
            evaluator_feedback TEXT NOT NULL DEFAULT ''
        )
        """
    )


def _migrate_plaintext_digest_db_to_sqlcipher(path: str):
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    backup_path = f"{path}.plaintext.bak.{stamp}"
    shutil.copy2(path, backup_path)
    os.remove(path)
    logger.warning(
        "[VECTOR][digest_store] Migrating plaintext digest DB to SQLCipher; "
        "plaintext backup kept at {}",
        backup_path,
    )
    conn = sqlcipher.connect(path, check_same_thread=False)
    try:
        conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
        conn.execute("PRAGMA cipher_page_size = 4096")
        _create_digest_table_on(conn)
        plain_conn = sqlite3.connect(backup_path, check_same_thread=False)
        try:
            columns = [
                row[1] for row in plain_conn.execute(
                    'PRAGMA table_info("digests")'
                ).fetchall()
            ]
            if columns:
                quoted_cols = ", ".join(f'"{column}"' for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = plain_conn.execute(
                    f'SELECT {quoted_cols} FROM "digests"'
                ).fetchall()
                if rows:
                    conn.executemany(
                        f'INSERT OR REPLACE INTO "digests" ({quoted_cols}) '
                        f'VALUES ({placeholders})',
                        rows,
                    )
            conn.commit()
        finally:
            plain_conn.close()
        logger.info(
            "[VECTOR][digest_store] SQLCipher migration completed, backup={}",
            backup_path,
        )
        return conn
    except Exception:
        conn.close()
        if os.path.exists(path):
            os.remove(path)
        shutil.copy2(backup_path, path)
        raise

@dataclass
class DigestArtifact:
    """A pre-computed morning digest ready for delivery."""

    text: str
    audio_path: Path
    sections: Dict[str, str]
    sources_used: List[str]
    generated_at: datetime
    model_used: str
    voice_used: str
    quality_score: float = 0.0
    evaluator_feedback: str = ""

class DigestStore:
    """SQLite store for digest artifacts."""

    def __init__(self, db_path: str = "") -> None:
        if not db_path:
            db_path = str(Path.home() / ".vector" / "digest.db")
        self._db_path = db_path
        self._lock = threading.RLock()
        if _USE_SQLCIPHER:
            if os.path.exists(db_path) and _looks_like_plaintext_sqlite(db_path):
                self._conn = _migrate_plaintext_digest_db_to_sqlcipher(db_path)
            else:
                self._conn = _open_sqlcipher_connection(db_path)
        else:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
        apply_pragmas(self._conn)
        with self._lock:
            _create_digest_table_on(self._conn)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the initial schema."""
        with self._lock:
            existing = {
                row[1]
                for row in self._conn.execute("PRAGMA table_info(digests)").fetchall()
            }
            if "quality_score" not in existing:
                self._conn.execute(
                    "ALTER TABLE digests ADD COLUMN quality_score REAL NOT NULL DEFAULT 0.0"
                )
            if "evaluator_feedback" not in existing:
                self._conn.execute(
                    "ALTER TABLE digests"
                    " ADD COLUMN evaluator_feedback TEXT NOT NULL DEFAULT ''"
                )

    def save(self, artifact: DigestArtifact) -> None:
        """Save a digest artifact."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO digests
                    (text, audio_path, sections, sources_used,
                     generated_at, model_used, voice_used,
                     quality_score, evaluator_feedback)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.text,
                    str(artifact.audio_path),
                    json.dumps(artifact.sections),
                    json.dumps(artifact.sources_used),
                    artifact.generated_at.isoformat(),
                    artifact.model_used,
                    artifact.voice_used,
                    artifact.quality_score,
                    artifact.evaluator_feedback,
                ),
            )
            self._conn.commit()

    def _row_to_artifact(self, row: tuple) -> DigestArtifact:
        return DigestArtifact(
            text=row[0],
            audio_path=Path(row[1]),
            sections=json.loads(row[2]),
            sources_used=json.loads(row[3]),
            generated_at=datetime.fromisoformat(row[4]),
            model_used=row[5],
            voice_used=row[6],
            quality_score=row[7] if len(row) > 7 else 0.0,
            evaluator_feedback=row[8] if len(row) > 8 else "",
        )

    def get_latest(self) -> Optional[DigestArtifact]:
        """Return the most recent digest, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT text, audio_path, sections, sources_used,"
                " generated_at, model_used, voice_used,"
                " quality_score, evaluator_feedback"
                " FROM digests ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self._row_to_artifact(row)

    def get_today(self, timezone_name: str = "UTC") -> Optional[DigestArtifact]:
        """Return today's digest if it exists, or None."""
        try:
            from zoneinfo import ZoneInfo

            today = datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")
        except ImportError:
            today = datetime.now().strftime("%Y-%m-%d")

        with self._lock:
            row = self._conn.execute(
                "SELECT text, audio_path, sections, sources_used,"
                " generated_at, model_used, voice_used,"
                " quality_score, evaluator_feedback"
                " FROM digests WHERE generated_at LIKE ? ORDER BY id DESC LIMIT 1",
                (f"{today}%",),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_artifact(row)

    def history(self, limit: int = 10) -> List[DigestArtifact]:
        """Return the N most recent digests."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT text, audio_path, sections, sources_used,"
                " generated_at, model_used, voice_used,"
                " quality_score, evaluator_feedback"
                " FROM digests ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_artifact(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
