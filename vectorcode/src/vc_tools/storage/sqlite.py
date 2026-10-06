# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""SQLite/FTS5 memory backend — zero-dependency default."""

from __future__ import annotations
from core.memory.db_utils import apply_pragmas
from loguru import logger

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from vectorcode.src.vc_core.events import EventType, get_event_bus
from vectorcode.src.vc_core.registry import MemoryRegistry
from vectorcode.src.vc_tools.storage._abc import MemoryBackend, RetrievalResult

def _check_fts5(conn: sqlite3.Connection) -> bool:
    """Return True if the SQLite build includes FTS5."""
    try:
        opts = conn.execute("PRAGMA compile_options").fetchall()
        return any("FTS5" in o[0].upper() for o in opts)
    except sqlite3.Error:
        return False

@MemoryRegistry.register("sqlite")
class SQLiteMemory(MemoryBackend):
    """Full-text search memory backend using SQLite FTS5.

    Uses the built-in ``sqlite3`` module — no extra dependencies.
    """

    backend_id: str = "sqlite"

    def __init__(self, db_path: str | Path = "") -> None:
        if not db_path:
            from vectorcode.src.vc_core.config import DEFAULT_CONFIG_DIR

            db_path = str(DEFAULT_CONFIG_DIR / "memory.db")

        self._db_path = str(db_path)
        self._lock = threading.RLock()
        self._rust_impl = None

        try:
            from vectorcode.src._rust_bridge import get_rust_module

            _rust = get_rust_module()
            self._rust_impl = _rust.SQLiteMemory(self._db_path)
            self._conn = None  # type: ignore[assignment]
        except (ImportError, AttributeError, RuntimeError, OSError) as exc:
            logger.debug("[VECTOR] Rust SQLite backend unavailable; using Python SQLite: {}", exc)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            apply_pragmas(self._conn)
            self._conn.row_factory = sqlite3.Row
            if not _check_fts5(self._conn):
                self._conn.close()
                raise RuntimeError(
                    "SQLite build lacks the FTS5 extension required by SQLiteMemory; "
                    "install a Python/SQLite build with FTS5 support or configure a "
                    "different memory backend."
                )
            self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id       TEXT PRIMARY KEY,
                    content  TEXT NOT NULL,
                    source   TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                USING fts5(
                    content,
                    source,
                    tokenize='porter unicode61'
                );
            """)

    def store(
        self,
        content: str,
        *,
        source: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist *content* and return a unique document id."""
        meta_json = json.dumps(metadata or {})
        if self._rust_impl is not None:
            doc_id = self._rust_impl.store(content, source, meta_json)
        else:
            doc_id = uuid.uuid4().hex
            with self._lock:
                self._conn.execute(
                    """
                    INSERT INTO documents (id, content, source, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (doc_id, content, source, meta_json, time.time()),
                )
                self._conn.execute(
                    "INSERT INTO documents_fts(rowid, content, source) VALUES ((SELECT rowid FROM documents WHERE id = ?), ?, ?)",
                    (doc_id, content, source),
                )
                self._conn.commit()
        bus = get_event_bus()
        bus.publish(
            EventType.MEMORY_STORE,
            {
                "backend": self.backend_id,
                "doc_id": doc_id,
                "source": source,
            },
        )
        return doc_id

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        **kwargs: Any,
    ) -> List[RetrievalResult]:
        """Search via FTS5 MATCH with BM25 ranking — always via Rust backend."""
        if not query.strip():
            return []

        if self._rust_impl is not None:
            from vectorcode.src._rust_bridge import retrieval_results_from_json

            results = retrieval_results_from_json(
                self._rust_impl.retrieve(query, top_k),
            )
        else:
            with self._lock:
                rows = self._conn.execute(
                    """
                    SELECT d.content, d.source, d.metadata, bm25(documents_fts) AS rank
                    FROM documents_fts
                    JOIN documents d ON d.rowid = documents_fts.rowid
                    WHERE documents_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (query, int(top_k)),
                ).fetchall()
            results = [
                RetrievalResult(
                    content=row["content"],
                    score=float(-row["rank"]),
                    source=row["source"],
                    metadata=json.loads(row["metadata"] or "{}"),
                )
                for row in rows
            ]
        bus = get_event_bus()
        bus.publish(
            EventType.MEMORY_RETRIEVE,
            {
                "backend": self.backend_id,
                "query": query,
                "num_results": len(results),
            },
        )
        return results

    def delete(self, doc_id: str) -> bool:
        """Delete a document by id — always via Rust backend."""
        if self._rust_impl is not None:
            return self._rust_impl.delete(doc_id)
        with self._lock:
            row = self._conn.execute(
                "SELECT rowid FROM documents WHERE id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                return False
            self._conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (row["rowid"],))
            self._conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            self._conn.commit()
            return True

    def clear(self) -> None:
        """Remove all stored documents — always via Rust backend."""
        if self._rust_impl is not None:
            self._rust_impl.clear()
            return
        with self._lock:
            self._conn.execute("DELETE FROM documents_fts")
            self._conn.execute("DELETE FROM documents")
            self._conn.commit()

    def count(self) -> int:
        """Return the number of stored documents — always via Rust backend."""
        if self._rust_impl is not None:
            return self._rust_impl.count()
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0])

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            with self._lock:
                self._conn.close()

__all__ = ["SQLiteMemory"]
