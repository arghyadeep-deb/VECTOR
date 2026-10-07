# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""KnowledgeStore — source-aware SQLite/FTS5 memory backend for Deep Research.

Extends ``MemoryBackend`` with per-document provenance columns so that the
IngestionPipeline and the ``knowledge_search`` tool can filter results by
source, doc_type, author, and timestamp ranges.

Pure Python ``sqlite3`` (no Rust extension required).
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from core.memory.db_utils import apply_pragmas
from vectorcode.src.vc_core.events import EventType, get_event_bus
from vectorcode.src.vc_core.registry import MemoryRegistry
from vectorcode.src.vc_tools.storage._abc import MemoryBackend, RetrievalResult

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
            "[VECTOR][connectors.store] SQLCipher not available -- connector "
            "knowledge will be stored UNENCRYPTED. Install sqlcipher3 to encrypt."
        )

_OPERATIONAL_ERRORS = (
    (sqlite3.OperationalError, sqlcipher.OperationalError)
    if _USE_SQLCIPHER
    else (sqlite3.OperationalError,)
)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_MAIN_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id            TEXT PRIMARY KEY,
    doc_id        TEXT NOT NULL,
    content       TEXT NOT NULL,
    source        TEXT NOT NULL DEFAULT '',
    doc_type      TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL DEFAULT '',
    author        TEXT NOT NULL DEFAULT '',
    participants  TEXT NOT NULL DEFAULT '[]',
    timestamp     TEXT NOT NULL DEFAULT '',
    thread_id     TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    metadata      TEXT NOT NULL DEFAULT '{}',
    chunk_index   INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL
);
"""

_CREATE_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
USING fts5(
    content,
    title,
    author,
    content='knowledge_chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);
"""

_CREATE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge_chunks BEGIN
    INSERT INTO knowledge_fts(rowid, content, title, author)
    VALUES (new.rowid, new.content, new.title, new.author);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge_chunks BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, content, title, author)
    VALUES ('delete', old.rowid, old.content, old.title, old.author);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge_chunks BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, content, title, author)
    VALUES ('delete', old.rowid, old.content, old.title, old.author);
    INSERT INTO knowledge_fts(rowid, content, title, author)
    VALUES (new.rowid, new.content, new.title, new.author);
END;
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_kc_source     ON knowledge_chunks(source);
CREATE INDEX IF NOT EXISTS idx_kc_doc_type   ON knowledge_chunks(doc_type);
CREATE INDEX IF NOT EXISTS idx_kc_author     ON knowledge_chunks(author);
CREATE INDEX IF NOT EXISTS idx_kc_timestamp  ON knowledge_chunks(timestamp);
CREATE INDEX IF NOT EXISTS idx_kc_thread_id  ON knowledge_chunks(thread_id);
CREATE INDEX IF NOT EXISTS idx_kc_doc_id     ON knowledge_chunks(doc_id);
"""


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


def _create_knowledge_schema_on(conn) -> None:
    conn.executescript(
        _CREATE_MAIN_TABLE + _CREATE_FTS_TABLE + _CREATE_TRIGGERS + _CREATE_INDEXES
    )
    conn.commit()


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


def _migrate_plaintext_knowledge_db_to_sqlcipher(path: str):
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    backup_path = f"{path}.plaintext.bak.{stamp}"
    shutil.copy2(path, backup_path)
    os.remove(path)
    logger.warning(
        "[VECTOR][connectors.store] Migrating plaintext knowledge DB to SQLCipher; "
        "plaintext backup kept at {}",
        backup_path,
    )
    conn = sqlcipher.connect(path, check_same_thread=False)
    try:
        conn.execute("PRAGMA key = " + _sql_literal(_get_db_key()))
        conn.execute("PRAGMA cipher_page_size = 4096")
        _create_knowledge_schema_on(conn)
        plain_conn = sqlite3.connect(backup_path, check_same_thread=False)
        try:
            columns = [
                row[1] for row in plain_conn.execute(
                    'PRAGMA table_info("knowledge_chunks")'
                ).fetchall()
            ]
            if columns:
                quoted_cols = ", ".join(f'"{column}"' for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = plain_conn.execute(
                    f'SELECT {quoted_cols} FROM "knowledge_chunks"'
                ).fetchall()
                if rows:
                    conn.executemany(
                        f'INSERT OR REPLACE INTO "knowledge_chunks" ({quoted_cols}) '
                        f'VALUES ({placeholders})',
                        rows,
                    )
            conn.commit()
        finally:
            plain_conn.close()
        logger.info(
            "[VECTOR][connectors.store] SQLCipher migration completed, backup={}",
            backup_path,
        )
        return conn
    except Exception:
        conn.close()
        if os.path.exists(path):
            os.remove(path)
        shutil.copy2(backup_path, path)
        raise

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _to_iso(ts: Optional[Union[datetime, str]]) -> str:
    """Normalise a timestamp to ISO 8601 string (UTC)."""
    if ts is None:
        return ""
    if isinstance(ts, str):
        return ts
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.isoformat()

# ---------------------------------------------------------------------------
# KnowledgeStore
# ---------------------------------------------------------------------------

@MemoryRegistry.register("knowledge")
class KnowledgeStore(MemoryBackend):
    """Source-aware SQLite/FTS5 knowledge store for Deep Research.

    Stores document chunks with rich provenance metadata and supports
    filtered BM25 retrieval by source, doc_type, author, and timestamp.
    """

    backend_id: str = "knowledge"

    def __init__(self, db_path: Union[str, Path] = "") -> None:
        if not db_path:
            from vectorcode.src.vc_core.config import DEFAULT_CONFIG_DIR

            db_path = DEFAULT_CONFIG_DIR / "knowledge.db"

        self._db_path = str(db_path)
        # Ensure the parent directory exists (skip for :memory:)
        if self._db_path != ":memory:":
            from vectorcode.src.vc_security.file_utils import secure_create

            secure_create(Path(self._db_path))

        self._lock = threading.RLock()
        if _USE_SQLCIPHER:
            if os.path.exists(self._db_path) and _looks_like_plaintext_sqlite(self._db_path):
                self._conn = _migrate_plaintext_knowledge_db_to_sqlcipher(self._db_path)
            else:
                self._conn = _open_sqlcipher_connection(self._db_path)
            self._conn.row_factory = sqlcipher.Row
        else:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        apply_pragmas(self._conn, foreign_keys=True)
        self._setup()

    def __enter__(self) -> "KnowledgeStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal setup
    # ------------------------------------------------------------------

    def _setup(self) -> None:
        """Create tables, FTS virtual table, triggers and indexes."""
        with self._lock:
            _create_knowledge_schema_on(self._conn)

    # ------------------------------------------------------------------
    # MemoryBackend interface
    # ------------------------------------------------------------------

    def store(  # type: ignore[override]
        self,
        content: str,
        *,
        source: str = "",
        doc_type: str = "",
        doc_id: Optional[str] = None,
        title: str = "",
        author: str = "",
        participants: Optional[List[str]] = None,
        timestamp: Optional[Union[datetime, str]] = None,
        thread_id: Optional[str] = None,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_index: int = 0,
    ) -> str:
        """Persist a content chunk and return its unique chunk id.

        All source-level fields are merged into the stored metadata so that
        ``retrieve()`` results carry full provenance.
        """
        chunk_id = str(uuid.uuid4())
        if doc_id is None:
            doc_id = str(uuid.uuid4())

        ts_str = _to_iso(timestamp)
        participants_json = json.dumps(participants or [])

        # Merge provenance fields into metadata for easy access in results
        combined_meta: Dict[str, Any] = dict(metadata or {})
        combined_meta["chunk_id"] = chunk_id
        combined_meta["source"] = source
        combined_meta["doc_type"] = doc_type
        combined_meta["doc_id"] = doc_id
        combined_meta["title"] = title
        combined_meta["author"] = author
        combined_meta["participants"] = participants or []
        combined_meta["timestamp"] = ts_str
        combined_meta["thread_id"] = thread_id or ""
        combined_meta["url"] = url or ""
        combined_meta["chunk_index"] = chunk_index

        meta_json = json.dumps(combined_meta)

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO knowledge_chunks
                    (id, doc_id, content, source, doc_type, title, author,
                     participants, timestamp, thread_id, url, metadata,
                     chunk_index, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    doc_id,
                    content,
                    source,
                    doc_type,
                    title,
                    author,
                    participants_json,
                    ts_str,
                    thread_id or "",
                    url or "",
                    meta_json,
                    chunk_index,
                    time.time(),
                ),
            )
            self._conn.commit()

        get_event_bus().publish(
            EventType.MEMORY_STORE,
            {
                "backend": self.backend_id,
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "source": source,
                "doc_type": doc_type,
            },
        )
        return chunk_id

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        source: Optional[str] = None,
        doc_type: Optional[str] = None,
        author: Optional[str] = None,
        since: Optional[Union[datetime, str]] = None,
        until: Optional[Union[datetime, str]] = None,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        """Search using FTS5 BM25 with optional column filters.

        Parameters
        ----------
        query:    Full-text search query.
        top_k:    Maximum number of results.
        source:   Restrict to chunks from this source (e.g. "gmail").
        doc_type: Restrict to chunks of this type (e.g. "email").
        author:   Restrict to chunks authored by this person.
        since:    Exclude chunks whose timestamp is earlier than this value.
        until:    Exclude chunks whose timestamp is later than this value.
        """
        if not query.strip():
            return []

        since_str = _to_iso(since) if since is not None else None
        until_str = _to_iso(until) if until is not None else None

        # Build the WHERE clause for filter columns
        filters: List[str] = []
        params: List[Any] = []

        if source is not None:
            filters.append("kc.source = ?")
            params.append(source)
        if doc_type is not None:
            filters.append("kc.doc_type = ?")
            params.append(doc_type)
        if author is not None:
            filters.append("kc.author = ?")
            params.append(author)
        if since_str:
            filters.append("kc.timestamp >= ?")
            params.append(since_str)
        if until_str:
            filters.append("kc.timestamp <= ?")
            params.append(until_str)

        where_clause = ""
        if filters:
            where_clause = "AND " + " AND ".join(filters)

        # FTS5 bm25() returns negative scores; abs() gives a positive rank
        sql = f"""
            SELECT
                kc.id,
                kc.content,
                kc.source,
                kc.metadata,
                abs(bm25(knowledge_fts)) AS score
            FROM knowledge_fts
            JOIN knowledge_chunks kc ON knowledge_fts.rowid = kc.rowid
            WHERE knowledge_fts MATCH ?
            {where_clause}
            ORDER BY score DESC
            LIMIT ?
        """

        try:
            with self._lock:
                rows = self._conn.execute(sql, [query] + params + [top_k]).fetchall()
        except _OPERATIONAL_ERRORS:
            # Malformed FTS query — return empty rather than crash
            return []

        results: List[RetrievalResult] = []
        for row in rows:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            # Ensure chunk_id is always present in metadata (backfill for
            # rows stored before this field was added to combined_meta).
            if "chunk_id" not in meta:
                meta["chunk_id"] = row["id"]
            results.append(
                RetrievalResult(
                    content=row["content"],
                    score=float(row["score"]),
                    source=row["source"],
                    metadata=meta,
                )
            )

        get_event_bus().publish(
            EventType.MEMORY_RETRIEVE,
            {
                "backend": self.backend_id,
                "query": query,
                "num_results": len(results),
                "filters": {
                    "source": source,
                    "doc_type": doc_type,
                    "author": author,
                    "since": since_str,
                    "until": until_str,
                },
            },
        )
        return results

    def delete(self, doc_id: str) -> bool:
        """Delete all chunks with the given *doc_id*. Returns True if any existed."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM knowledge_chunks WHERE doc_id = ?", (doc_id,)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> None:
        """Remove all stored chunks."""
        with self._lock:
            self._conn.executescript(
                "DELETE FROM knowledge_chunks; DELETE FROM knowledge_fts;"
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Extra helpers
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the total number of stored chunks."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        try:
            with self._lock:
                self._conn.close()
        except Exception as _sve:
            logger.debug("[VECTOR][connectors.store] suppressed Exception: {}", _sve)

__all__ = ["KnowledgeStore"]
