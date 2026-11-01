# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""SyncScheduler — background thread for periodic incremental connector syncs.

Registers connectors for timed re-sync and runs them on a configurable
interval.  Designed to be long-lived (daemon thread) inside a running
VectorCode server process.

Typical usage::

    store = KnowledgeStore(db_path=":memory:")
    pipeline = IngestionPipeline(store)
    engine = SyncEngine(pipeline)

    scheduler = SyncScheduler(engine, interval_seconds=3600)
    scheduler.add(gmail_connector)
    scheduler.add(slack_connector)
    scheduler.start()       # background thread syncs every hour

    # Later:
    scheduler.stop()
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from loguru import logger

from vectorcode.src.connectors._abc import BaseConnector
from vectorcode.src.connectors.sync_engine import SyncEngine

class SyncScheduler:
    """Runs incremental sync for all registered connectors on a schedule.

    Parameters
    ----------
    sync_engine:
        The :class:`~vector.connectors.sync_engine.SyncEngine` used to
        drive each connector's sync (handles checkpointing).
    interval_seconds:
        How often (in seconds) to sync all connected connectors.
        Defaults to ``3600`` (one hour).
    """

    def __init__(self, sync_engine: SyncEngine, interval_seconds: int = 3600) -> None:
        self._engine = sync_engine
        self._interval = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._connectors: List[BaseConnector] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, connector: BaseConnector) -> None:
        """Register a connector for scheduled sync.

        Parameters
        ----------
        connector:
            Any :class:`~vector.connectors._abc.BaseConnector` instance.
            Only connected connectors are synced during each cycle.
        """
        self._connectors.append(connector)

    def start(self) -> None:
        """Start the background sync thread.

        The thread is a daemon so it does not prevent process exit.  The
        first sync run occurs after one full *interval_seconds* wait.
        Calling :meth:`start` on an already-running scheduler is a no-op.
        """
        if self._thread is not None and self._thread.is_alive():
            logger.debug("SyncScheduler already running; ignoring start()")
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="sync_scheduler"
        )
        self._thread.start()
        logger.info(
            "SyncScheduler started (interval={}s, connectors={})",
            self._interval,
            len(self._connectors),
        )

    def stop(self) -> None:
        """Stop the background sync thread.

        Signals the thread to exit and waits up to 5 seconds for it to
        finish the current sync cycle.  Safe to call even when the scheduler
        is not running.
        """
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                # The sync cycle in progress took longer than the join
                # timeout -- do NOT clear self._thread here. start()'s
                # already-running guard checks self._thread.is_alive(), so
                # leaving the reference in place lets it correctly refuse
                # to spawn a second thread; clearing it unconditionally
                # (as this previously did) would let a stop()-then-start()
                # sequence leak a zombie thread and run two _loop()s
                # concurrently, racing on the same connectors/store.
                logger.warning(
                    "SyncScheduler: background thread did not stop within "
                    "5s (sync cycle still in progress); leaving it tracked "
                    "so start() won't spawn a duplicate"
                )
                return
        self._thread = None
        logger.info("SyncScheduler stopped")

    def run_once(self) -> Dict[str, int]:
        """Sync all connected connectors once (synchronous, non-blocking test helper).

        Returns
        -------
        dict[str, int]
            Mapping of ``connector_id`` → number of new chunks ingested.
            Only connectors that are currently connected are included.
        """
        results: Dict[str, int] = {}
        for conn in self._connectors:
            if conn.is_connected():
                try:
                    count = self._engine.sync(conn)
                    results[conn.connector_id] = count
                except Exception as exc:
                    logger.error(
                        "run_once sync failed for {}: {}", conn.connector_id, exc
                    )
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """Background thread body: wait *interval* seconds then sync."""
        while not self._stop.wait(timeout=self._interval):
            for conn in self._connectors:
                if conn.is_connected():
                    try:
                        count = self._engine.sync(conn)
                        logger.debug(
                            "Scheduled sync completed for {} ({} items)",
                            conn.connector_id,
                            count,
                        )
                    except Exception as exc:
                        logger.error(
                            "Scheduled sync failed for {}: {}",
                            conn.connector_id,
                            exc,
                        )

__all__ = ["SyncScheduler"]
