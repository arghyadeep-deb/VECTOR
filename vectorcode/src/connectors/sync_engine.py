# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""SyncEngine — checkpoint/resume orchestration for connector syncs.

Wraps ``IngestionPipeline`` with a lightweight SQLite state database so that
long-running syncs can be interrupted and resumed from the last saved cursor.

Typical usage::

    store = KnowledgeStore(db_path=":memory:")
    pipeline = IngestionPipeline(store)
    engine = SyncEngine(pipeline)

    items = engine.sync(connector)        # first run
    items = engine.sync(connector)        # resumes from saved cursor
    cp = engine.get_checkpoint(connector.connector_id)
"""

from __future__ import annotations
from core.memory.db_utils import apply_pragmas
from loguru import logger

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from vectorcode.src.connectors._abc import BaseConnector
from vectorcode.src.connectors.pipeline import IngestionPipeline
from vectorcode.src.vc_core.config import DEFAULT_CONFIG_DIR

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

_CREATE_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS sync_state (
    connector_id  TEXT PRIMARY KEY,
    items_synced  INTEGER NOT NULL DEFAULT 0,
    cursor        TEXT,
    last_sync     TEXT,
    error         TEXT
);
"""

_BATCH_SIZE = 100

class SyncEngine:
    """Orchestrate connector syncs with checkpoint/resume tracking.

    Parameters
    ----------
    pipeline:
        The ``IngestionPipeline`` that documents are fed into.
    state_db:
        Path to the SQLite database used for checkpoint state.  If empty,
        defaults to ``DEFAULT_CONFIG_DIR / "sync_state.db"``.
    """

    def __init__(self, pipeline: IngestionPipeline, *, state_db: str = "") -> None:
        self._pipeline = pipeline

        if not state_db:
            db_path = DEFAULT_CONFIG_DIR / "sync_state.db"
        else:
            db_path = Path(state_db)

        # Ensure parent directory exists (skip for :memory:)
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        apply_pragmas(self._conn)
        with self._lock:
            self._conn.execute(_CREATE_STATE_TABLE)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync(self, connector: BaseConnector) -> int:
        """Run a full sync for *connector* and return the number of items ingested.

        Resumes from the last saved cursor if one exists.  Documents are
        batched in groups of 100 before being handed to the pipeline; a
        checkpoint is saved after every batch and once more at the end.

        On error the checkpoint is updated with the error message and the
        exception is re-raised so callers can handle it.
        """
        connector_id: str = connector.connector_id

        # Load any previous checkpoint so we can resume.
        checkpoint = self.get_checkpoint(connector_id)
        prior_cursor: Optional[str] = checkpoint["cursor"] if checkpoint else None
        prior_items: int = checkpoint["items_synced"] if checkpoint else 0
        prior_last_sync: Optional[str] = checkpoint["last_sync"] if checkpoint else None

        since: Optional[datetime] = None
        if checkpoint and checkpoint.get("last_sync"):
            try:
                since = datetime.fromisoformat(checkpoint["last_sync"])
            except (ValueError, TypeError) as _sve:
                logger.debug("[VECTOR][connectors.sync_engine] suppressed (ValueError, TypeError): {}", _sve)

        items_ingested = 0
        current_cursor: Optional[str] = prior_cursor
        sync_started_at = datetime.now(tz=timezone.utc).isoformat()

        try:
            doc_iter = connector.sync(since=since, cursor=prior_cursor)

            batch = []
            for doc in doc_iter:
                batch.append(doc)

                if len(batch) >= _BATCH_SIZE:
                    items_ingested += self._pipeline.ingest(batch)
                    batch = []
                    current_cursor = connector.sync_status().cursor
                    self._save_checkpoint(
                        connector_id,
                        prior_items + items_ingested,
                        cursor=current_cursor,
                        last_sync=prior_last_sync,
                    )

            # Ingest any remaining documents.
            if batch:
                items_ingested += self._pipeline.ingest(batch)

        except Exception as exc:
            current_cursor = connector.sync_status().cursor or current_cursor
            self._save_checkpoint(
                connector_id,
                prior_items + items_ingested,
                cursor=current_cursor,
                error=str(exc),
                last_sync=prior_last_sync,
            )
            raise

        # Final checkpoint — clear any previous error.
        current_cursor = connector.sync_status().cursor
        self._save_checkpoint(
            connector_id,
            prior_items + items_ingested,
            cursor=current_cursor,
            error=None,
            last_sync=sync_started_at,
        )
        return items_ingested

    def get_checkpoint(self, connector_id: str) -> Optional[Dict[str, Any]]:
        """Return the last checkpoint, or ``None`` if never synced."""
        sql = (
            "SELECT items_synced, cursor, last_sync, error"
            " FROM sync_state WHERE connector_id = ?"
        )
        with self._lock:
            row = self._conn.execute(sql, (connector_id,)).fetchone()

        if row is None:
            return None

        return {
            "items_synced": row["items_synced"],
            "cursor": row["cursor"],
            "last_sync": row["last_sync"],
            "error": row["error"],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_checkpoint(
        self,
        connector_id: str,
        items_synced: int,
        *,
        cursor: Optional[str] = None,
        error: Optional[str] = None,
        last_sync: Optional[str] = None,
    ) -> None:
        """UPSERT a checkpoint row into the state database."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sync_state
                    (connector_id, items_synced, cursor, last_sync, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(connector_id) DO UPDATE SET
                    items_synced = excluded.items_synced,
                    cursor       = excluded.cursor,
                    last_sync    = excluded.last_sync,
                    error        = excluded.error
                """,
                (connector_id, items_synced, cursor, last_sync, error),
            )
            self._conn.commit()

__all__ = ["SyncEngine"]
