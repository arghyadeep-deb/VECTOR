import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.memory.episodic import EpisodicMemory


@pytest.fixture
def mem():
    return EpisodicMemory()


def test_store_and_recall(mem):
    unique = f"test_recall_{uuid.uuid4().hex[:8]}"
    mem.store(event_type="test", content=unique, tags=["pytest"], source="test")
    results = mem.recall(unique, limit=5)
    assert any(unique in r.get("content", "") for r in results)


def test_recall_empty_query_returns_recent(mem):
    mem.store(event_type="test", content="recent_event_xyz", tags=[], source="test")
    results = mem.recall("", limit=10)
    assert isinstance(results, list)


def test_get_stats_has_expected_keys(mem):
    stats = mem.get_stats()
    assert "episodic_memory" in stats
    assert isinstance(stats["episodic_memory"], int)


def test_store_returns_id(mem):
    eid = mem.store(event_type="test", content="content", tags=[], source="test")
    assert eid is not None and isinstance(eid, str)


def test_multiple_stores_increase_count(mem):
    before = mem.get_stats().get("episodic_memory", 0)
    for i in range(3):
        mem.store(event_type="test", content=f"bulk_{i}_{uuid.uuid4().hex[:6]}", tags=[], source="test")
    after = mem.get_stats().get("episodic_memory", 0)
    assert after >= before + 3


def test_recall_limit_respected(mem):
    for i in range(10):
        mem.store(event_type="test", content=f"limit_test_{uuid.uuid4().hex[:6]}", tags=[], source="test")
    results = mem.recall("", limit=3)
    assert len(results) <= 3


def test_content_stored_and_retrievable(mem):
    unique_content = f"unique_content_{uuid.uuid4().hex[:8]}"
    mem.store(event_type="test", content=unique_content, tags=["pytest"], source="test")
    results = mem.recall(unique_content, limit=5)
    assert len(results) >= 1
    assert any(unique_content in r.get("content", "") for r in results)
