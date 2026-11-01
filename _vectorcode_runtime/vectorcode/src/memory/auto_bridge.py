"""
AutoMemoryBridge — bidirectional sync between EpisodicMemory and FAISSIndex.

Syncs every SYNC_INTERVAL_SEC (300s) via a LOW-priority background TaskQueue task.
Only events tagged with INSIGHT_CATEGORIES are synced to FAISS.

RULE 11: no Claude API.
RULE 8:  leverages EpisodicMemory for source data.
"""
import sys
import math
import random
import uuid

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {"ollama_host": "http://localhost:11434"}
from loguru import logger
try:
    from core.memory.episodic import EpisodicMemory
except ImportError:
    EpisodicMemory = None
from .faiss_index import FAISSIndex

# ── Embedding helper (same pattern as pattern_store) ─────────────────────────

_EMBED_MODEL = "nomic-embed-text"
_EMBED_DIM = 768


def _unit_random_vector(dim: int) -> list[float]:
    vec = [random.gauss(0, 1) for _ in range(dim)]
    mag = math.sqrt(sum(x * x for x in vec))
    if mag == 0.0:
        return [1.0 / math.sqrt(dim)] * dim
    return [x / mag for x in vec]


def _embed_text(text: str) -> list[float]:
    """Embed text via Ollama; fall back to random unit vector."""
    try:
        import ollama
        client = ollama.Client(host=CONFIG["ollama_host"], timeout=10.0)
        response = client.embeddings(model=_EMBED_MODEL, prompt=text)
        embedding = response.get("embedding", [])
        if len(embedding) == _EMBED_DIM:
            return embedding
    except Exception as e:
        logger.debug(f"[VECTOR][auto_bridge] embed fallback: {e}")
    return _unit_random_vector(_EMBED_DIM)


# ── AutoMemoryBridge ──────────────────────────────────────────────────────────

class AutoMemoryBridge:
    """
    Bidirectional bridge between episodic memory and FAISS vector index.

    sync_episodic_to_faiss()  — pull relevant events from EpisodicMemory → FAISS.
    sync_faiss_to_episodic()  — placeholder for reverse sync (future).
    start_background_sync()   — submits itself as a recurring LOW-priority TaskQueue task.
    """

    SYNC_INTERVAL_SEC = 300
    INSIGHT_CATEGORIES = [
        "patterns",
        "debugging",
        "architecture",
        "performance",
        "security",
        "preferences",
    ]

    def __init__(self, index_path: str, *, encrypted: bool = True) -> None:
        self._index_path = str(index_path)
        self._faiss = FAISSIndex(index_path=index_path, dim=_EMBED_DIM, encrypted=encrypted)
        # FL-023: restart lifecycle — previously the constructor never called
        # load(), so every restart started from an empty index even when a
        # previously-saved one existed on disk.
        self._faiss.load()
        self._memory = EpisodicMemory()
        self._sync_task_id: str | None = None
        logger.info(
            f"[VECTOR][auto_bridge] ready path={index_path} encrypted={encrypted}"
        )

    # ── Sync: episodic → FAISS ────────────────────────────────────────────────

    def sync_episodic_to_faiss(self) -> int:
        """
        Retrieve recent episodic events tagged with any INSIGHT_CATEGORY and
        upsert them into the FAISS index.

        Returns the number of events synced.
        """
        synced = 0
        for category in self.INSIGHT_CATEGORIES:
            events = self._memory.recall(query=category, limit=20)
            for event in events:
                content = event.get("content", "")
                if not content:
                    continue
                doc_id = event.get("id") or uuid.uuid4().hex
                # FL-023: deduplication — every sync cycle used to re-fetch
                # and re-embed the same recent events from scratch forever
                # (re-embedding is a real Ollama call, not free). Skip
                # anything already present in the index.
                if self._faiss.contains(doc_id) is True:
                    continue
                vector = _embed_text(content)
                metadata = {
                    "event_id": doc_id,
                    "event_type": event.get("event_type", ""),
                    "category": category,
                    "timestamp": event.get("timestamp", ""),
                    "source": event.get("source", "episodic"),
                }
                self._faiss.add(doc_id, vector, metadata)
                synced += 1

        if synced:
            # FL-023: restart lifecycle — previously save() was never
            # called at all, so every sync cycle's work was lost on restart.
            self._faiss.save()

        logger.info(f"[VECTOR][auto_bridge] synced {synced} episodic events → FAISS")
        return synced

    # ── Sync: FAISS → episodic (future) ──────────────────────────────────────

    def sync_faiss_to_episodic(self) -> int:
        """
        Reverse sync placeholder. Returns 0 until implemented in a future phase.
        """
        logger.debug("[VECTOR][auto_bridge] sync_faiss_to_episodic: placeholder — returns 0")
        return 0

    # ── Background scheduling ─────────────────────────────────────────────────

    def start_background_sync(self) -> None:
        """
        Submit the sync loop as a LOW-priority recurring background task.
        Uses TaskQueue singleton if an event loop is running; logs a warning
        and skips silently if no loop is available.

        FL-023: idempotent — calling this while a sync task is already
        running is a no-op instead of spawning a second concurrent loop.
        """
        if self._sync_task_id is not None:
            logger.debug(
                "[VECTOR][auto_bridge] background sync already running "
                f"(task_id={self._sync_task_id}) — skipping duplicate start"
            )
            return
        try:
            from core.loop.task_queue import TaskQueue, Priority

            async def _sync_loop():
                import asyncio
                try:
                    while True:
                        try:
                            self.sync_episodic_to_faiss()
                        except Exception as e:
                            logger.error(f"[VECTOR][auto_bridge] sync error: {e}")
                        await asyncio.sleep(self.SYNC_INTERVAL_SEC)
                except asyncio.CancelledError:
                    logger.info("[VECTOR][auto_bridge] background sync cancelled")
                    raise

            tq = TaskQueue.get()
            self._sync_task_id = tq.submit(
                _sync_loop(),
                name="AutoMemoryBridge.sync",
                priority=Priority.LOW,
                district="coding",
                tags=["memory", "faiss", "sync"],
            )
            logger.info(
                f"[VECTOR][auto_bridge] background sync task submitted "
                f"task_id={self._sync_task_id}"
            )
        except RuntimeError:
            logger.warning(
                "[VECTOR][auto_bridge] no running event loop — background sync not started"
            )
        except Exception as e:
            logger.warning(f"[VECTOR][auto_bridge] start_background_sync failed: {e}")

    def stop_background_sync(self) -> bool:
        """
        Cancel the running background sync task, if any (FL-023:
        cancellation handle — previously there was no way to stop a
        started sync loop short of killing the whole process).

        Returns True if a running task was actually cancelled, False if
        none was running.
        """
        if self._sync_task_id is None:
            return False
        task_id = self._sync_task_id
        self._sync_task_id = None
        try:
            from core.loop.task_queue import TaskQueue

            cancelled = TaskQueue.get().cancel(task_id)
            logger.info(
                f"[VECTOR][auto_bridge] stop_background_sync task_id={task_id} "
                f"cancelled={cancelled}"
            )
            return cancelled
        except Exception as e:
            logger.warning(f"[VECTOR][auto_bridge] stop_background_sync failed: {e}")
            return False


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        bridge = AutoMemoryBridge(index_path=f"{tmp}/bridge")

        assert AutoMemoryBridge.SYNC_INTERVAL_SEC == 300
        assert set(AutoMemoryBridge.INSIGHT_CATEGORIES) == {
            "patterns", "debugging", "architecture", "performance", "security", "preferences"
        }

        count = bridge.sync_episodic_to_faiss()
        print(f"   synced {count} events (may be 0 on fresh DB)")

        rev = bridge.sync_faiss_to_episodic()
        assert rev == 0, "reverse sync must return 0 (placeholder)"

    print("✅ auto_bridge.py OK")


