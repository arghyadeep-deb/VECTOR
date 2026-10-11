"""FL-023 — AutoMemoryBridge durability/lifecycle (full build, owner decision
2026-10-11: build it now, with the same encryption VECTOR's other memory
already uses).

Before this fix:
- The constructor never called FAISSIndex.load(), so a restart always
  started from an empty index even when a previously-saved one existed.
- sync_episodic_to_faiss() never called FAISSIndex.save(), so a crash lost
  every cycle's work.
- Every sync cycle re-fetched and re-embedded the same recent events with
  no deduplication (a real Ollama embedding call each time, not free).
- start_background_sync() had no cancellation handle and no idempotence
  guard (calling it twice would spawn two concurrent sync loops).
- FAISSIndex's metadata store was always plain, unencrypted SQLite.

Zero production callers exist (confirmed via repo-wide grep for
"AutoMemoryBridge(" outside this module and its tests), so these tests use
the real FAISSIndex (not mocked) against a real tmp_path to prove the
actual on-disk behavior, with a lightweight fake EpisodicMemory standing in
for the real one (the real one needs the full memory subsystem; this file
is about the bridge's own lifecycle, not episodic recall itself).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from vectorcode.src.memory.auto_bridge import AutoMemoryBridge
from vectorcode.src.memory.faiss_index import FAISSIndex


class _FakeEpisodicMemory:
    """Returns a fixed set of events for every category, each with a
    STABLE id so repeat sync cycles exercise the dedup path for real."""

    def __init__(self, events_by_category: dict[str, list[dict]] | None = None):
        self._events_by_category = events_by_category or {}

    def recall(self, query: str, limit: int = 20):
        return list(self._events_by_category.get(query, []))


def _bridge(tmp_path: Path, events_by_category=None, **kwargs) -> AutoMemoryBridge:
    fake_memory = _FakeEpisodicMemory(events_by_category)
    with patch(
        "vectorcode.src.memory.auto_bridge.EpisodicMemory",
        return_value=fake_memory,
    ):
        return AutoMemoryBridge(index_path=str(tmp_path / "bridge"), **kwargs)


def _one_event_per_category(categories, content="learned something useful"):
    return {
        cat: [{"id": f"evt-{cat}", "content": content, "event_type": "insight"}]
        for cat in categories
    }


def test_sync_persists_and_a_fresh_bridge_recovers_on_restart(tmp_path):
    events = _one_event_per_category(AutoMemoryBridge.INSIGHT_CATEGORIES)
    bridge = _bridge(tmp_path, events)
    synced = bridge.sync_episodic_to_faiss()
    assert synced == len(AutoMemoryBridge.INSIGHT_CATEGORIES)

    # Simulate a restart: a brand-new AutoMemoryBridge instance pointed at
    # the same index_path, with no prior in-memory state at all.
    bridge2 = _bridge(tmp_path, events)
    for cat in AutoMemoryBridge.INSIGHT_CATEGORIES:
        assert bridge2._faiss.contains(f"evt-{cat}") is True


def test_sync_does_not_reembed_already_synced_events(tmp_path):
    events = _one_event_per_category(AutoMemoryBridge.INSIGHT_CATEGORIES)
    bridge = _bridge(tmp_path, events)

    first = bridge.sync_episodic_to_faiss()
    assert first == len(AutoMemoryBridge.INSIGHT_CATEGORIES)

    # Same bridge instance, same events, second cycle -- everything should
    # already be present, so nothing new gets embedded/added.
    second = bridge.sync_episodic_to_faiss()
    assert second == 0


def test_sync_reembeds_only_the_genuinely_new_event(tmp_path):
    events = _one_event_per_category(AutoMemoryBridge.INSIGHT_CATEGORIES)
    bridge = _bridge(tmp_path, events)
    bridge.sync_episodic_to_faiss()

    # Add one brand-new event to one category; the rest are unchanged.
    events["patterns"].append(
        {"id": "evt-patterns-2", "content": "a second insight", "event_type": "insight"}
    )
    second = bridge.sync_episodic_to_faiss()
    assert second == 1


def test_meta_db_is_encrypted_by_default(tmp_path):
    events = _one_event_per_category(AutoMemoryBridge.INSIGHT_CATEGORIES)
    bridge = _bridge(tmp_path, events)
    bridge.sync_episodic_to_faiss()

    meta_path = tmp_path / "bridge.meta.db"
    assert meta_path.exists()
    header = meta_path.read_bytes()[:16]
    # A real, unencrypted SQLite file always starts with this exact magic
    # header. An AES-encrypted SQLCipher file never does.
    assert header != b"SQLite format 3\x00"


def test_meta_db_is_plaintext_when_encryption_explicitly_disabled(tmp_path):
    events = _one_event_per_category(AutoMemoryBridge.INSIGHT_CATEGORIES)
    bridge = _bridge(tmp_path, events, encrypted=False)
    bridge.sync_episodic_to_faiss()

    meta_path = tmp_path / "bridge.meta.db"
    header = meta_path.read_bytes()[:16]
    assert header == b"SQLite format 3\x00"


def test_faiss_index_contains_reflects_add_and_delete(tmp_path):
    idx = FAISSIndex(index_path=str(tmp_path / "idx"), dim=4)
    assert idx.contains("x") is False
    idx.add("x", [1.0, 0.0, 0.0, 0.0], {})
    assert idx.contains("x") is True
    idx.delete("x")
    assert idx.contains("x") is False


class _FakeTaskQueueTask:
    def __init__(self):
        self.cancelled = False


class _FakeTaskQueue:
    """Lightweight stand-in for the real process-global TaskQueue singleton
    (which touches a real ledger DB) -- this file is about AutoMemoryBridge's
    own cancellation/idempotence bookkeeping, not TaskQueue's internals."""

    def __init__(self):
        self.submitted: list[dict] = []
        self.cancel_calls: list[str] = []
        self._next_id = 0
        self._tasks: dict[str, _FakeTaskQueueTask] = {}

    def submit(self, work, name, priority=None, district="core", tags=None):
        self._next_id += 1
        task_id = f"fake-{self._next_id}"
        self._tasks[task_id] = _FakeTaskQueueTask()
        self.submitted.append({"name": name, "district": district, "tags": tags})
        # Close the coroutine so pytest's asyncio loop doesn't warn about an
        # un-awaited coroutine -- this fake never actually drives it.
        work.close()
        return task_id

    def cancel(self, task_id: str) -> bool:
        self.cancel_calls.append(task_id)
        task = self._tasks.get(task_id)
        if task is None or task.cancelled:
            return False
        task.cancelled = True
        return True


def test_start_background_sync_is_idempotent(tmp_path):
    bridge = _bridge(tmp_path)
    fake_tq = _FakeTaskQueue()
    with patch("core.loop.task_queue.TaskQueue.get", return_value=fake_tq):
        bridge.start_background_sync()
        bridge.start_background_sync()  # second call must be a no-op
    assert len(fake_tq.submitted) == 1


def test_stop_background_sync_cancels_and_clears_handle(tmp_path):
    bridge = _bridge(tmp_path)
    fake_tq = _FakeTaskQueue()
    with patch("core.loop.task_queue.TaskQueue.get", return_value=fake_tq):
        bridge.start_background_sync()
        assert bridge._sync_task_id is not None
        stopped = bridge.stop_background_sync()
    assert stopped is True
    assert bridge._sync_task_id is None
    assert fake_tq.cancel_calls  # cancel() was actually called


def test_stop_background_sync_is_false_when_nothing_running(tmp_path):
    bridge = _bridge(tmp_path)
    assert bridge.stop_background_sync() is False


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
