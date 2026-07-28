"""Regression coverage for the MemoryTree I/O bottleneck fix.

Root cause: EpisodicMemory.store() constructed a brand-new MemoryTree() on
every call. MemoryTree.__init__ unconditionally _load()'d (full read+parse
of the whole tree file) and ingest() unconditionally _save()'d (full
re-serialize+rewrite) — on a machine with a ~20MB/~42k-chunk tree file, 200
store() calls (8 threads x 25 each) hung 90+ seconds
(tests/backend/test_memory_concurrency_safety.py::test_concurrent_writes_no_database_locked).
The tree's path also ignored VECTOR_DB_PATH, so tests believed they were
isolated but weren't.
"""
from __future__ import annotations

import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.engine.memory_tree import tree_builder
from core.engine.memory_tree.tree_builder import (
    MemoryTree,
    TreeChunk,
    close_shared_tree,
    get_shared_tree,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    close_shared_tree()
    yield
    close_shared_tree()


class TestSingleton:
    def test_get_shared_tree_returns_same_instance(self, tmp_path):
        t1 = get_shared_tree(db_dir=tmp_path / "db", wiki_dir=tmp_path / "wiki")
        t2 = get_shared_tree()
        assert t1 is t2

    def test_close_shared_tree_resets_singleton(self, tmp_path):
        t1 = get_shared_tree(db_dir=tmp_path / "db", wiki_dir=tmp_path / "wiki")
        close_shared_tree()
        t2 = get_shared_tree(db_dir=tmp_path / "db2", wiki_dir=tmp_path / "wiki2")
        assert t1 is not t2

    def test_no_per_call_reconstruction(self, tmp_path, monkeypatch):
        """The actual bug: MemoryTree() (and therefore _load()) used to run
        once per store() call. Prove get_shared_tree() only loads once
        across many ingests."""
        load_calls = {"n": 0}
        original_load = MemoryTree._load

        def counting_load(self):
            load_calls["n"] += 1
            return original_load(self)

        monkeypatch.setattr(MemoryTree, "_load", counting_load)

        tree = get_shared_tree(db_dir=tmp_path / "db", wiki_dir=tmp_path / "wiki")
        assert load_calls["n"] == 1
        for i in range(30):
            tree.ingest("test", "src", f"chunk {i}", topic="t")
        assert load_calls["n"] == 1, "MemoryTree must not reload per ingest()"


class TestDebounce:
    def test_save_is_debounced_not_per_ingest(self, tmp_path):
        tree = MemoryTree(db_dir=tmp_path / "db", wiki_dir=tmp_path / "wiki")
        tree._save_every_n = 5
        tree._save_interval_s = 999  # effectively disable the time trigger

        path = tree._db_path()
        assert not path.exists()

        for i in range(4):
            tree.ingest("test", "src", f"chunk {i}", topic="t")
        assert not path.exists(), "must not save before the count threshold"

        tree.ingest("test", "src", "chunk 4", topic="t")  # 5th ingest
        assert path.exists(), "must save once the count threshold is reached"

    def test_flush_forces_a_save(self, tmp_path):
        tree = MemoryTree(db_dir=tmp_path / "db", wiki_dir=tmp_path / "wiki")
        tree._save_every_n = 999
        tree._save_interval_s = 999
        tree.ingest("test", "src", "chunk", topic="t")
        assert not tree._db_path().exists()
        assert tree.flush() is True
        assert tree._db_path().exists()
        assert tree.flush() is False, "flush() with nothing dirty must be a no-op"


class TestGrowthBound:
    def test_per_topic_cap_enforced(self, tmp_path):
        tree = MemoryTree(db_dir=tmp_path / "db", wiki_dir=tmp_path / "wiki")
        tree._max_chunks_per_topic = 10
        for i in range(25):
            tree.ingest("test", "src", f"chunk {i}", topic="capped")
        node = tree._sources["test:src"].nodes["capped"]
        assert len(node.chunks) == 10
        # Most recent chunks retained, not the oldest.
        assert node.chunks[-1].content == "chunk 24"


class TestRetention:
    def test_prune_old_chunks_removes_only_stale_ones(self, tmp_path):
        tree = MemoryTree(db_dir=tmp_path / "db", wiki_dir=tmp_path / "wiki")
        old = TreeChunk(
            id="old", source_kind="test", source_id="src", topic="t",
            content="old", created_at=(datetime.now(timezone.utc) - timedelta(days=200)).isoformat(),
        )
        recent = TreeChunk(
            id="recent", source_kind="test", source_id="src", topic="t",
            content="recent", created_at=datetime.now(timezone.utc).isoformat(),
        )
        tree._sources["test:src"] = tree._sources.get("test:src")
        from core.engine.memory_tree.tree_builder import MemorySource
        tree._sources["test:src"] = MemorySource(source_kind="test", source_id="src")
        node = tree._sources["test:src"].get_or_create_node("t")
        node.chunks = [old, recent]

        removed = tree.prune_old_chunks(retention_days=90)

        assert removed == 1
        assert [c.id for c in node.chunks] == ["recent"]


class TestIsolation:
    def test_default_tree_dir_honors_vector_db_path(self, tmp_path, monkeypatch):
        """The actual isolation bug: the tree path used to be hardcoded to
        ~/.vector_ca/memory_tree regardless of VECTOR_DB_PATH."""
        fake_db = tmp_path / "isolated" / "mem.db"
        monkeypatch.setenv("VECTOR_DB_PATH", str(fake_db))
        resolved = tree_builder._default_tree_dir()
        assert resolved == (fake_db.parent / "memory_tree").resolve()
        assert str(tmp_path.resolve()) in str(resolved)

    def test_default_tree_dir_is_absolute_regardless_of_relative_db_path(self, tmp_path, monkeypatch):
        """The real bug found live during this fix's own verification: a
        RELATIVE VECTOR_DB_PATH (this deployment's actual .env value,
        "vector_memory.db") made the tree dir silently depend on the
        calling process's CWD — two callers from different directories
        would each get their own un-synced copy. Must always resolve to
        an absolute, CWD-independent path."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("VECTOR_DB_PATH", "relative_mem.db")
        resolved = tree_builder._default_tree_dir()
        assert resolved.is_absolute()
        assert resolved == (tmp_path / "memory_tree").resolve()

    def test_vector_memory_tree_path_env_var_overrides(self, tmp_path, monkeypatch):
        override = tmp_path / "custom_tree_dir"
        monkeypatch.setenv("VECTOR_MEMORY_TREE_PATH", str(override))
        assert tree_builder._default_tree_dir() == override.resolve()

    def test_legacy_tree_migrated_for_continuity(self, tmp_path, monkeypatch):
        """A real ~/.vector_ca/memory_tree/memory_tree.json with genuine
        accumulated data must not be silently orphaned by the CWD-fix
        above — copy it into the new resolved location the first time,
        never delete/move the original."""
        fake_legacy_dir = tmp_path / "legacy"
        fake_legacy_dir.mkdir()
        (fake_legacy_dir / "memory_tree.json").write_text(
            '{"episodic:real_data": {"source_kind": "episodic", "source_id": "real_data", '
            '"global_summary": "", "updated_at": "", "nodes": {}}}',
            encoding="utf-8",
        )
        monkeypatch.setattr(tree_builder, "_LEGACY_TREE_DIR", fake_legacy_dir)

        new_dir = tmp_path / "new_location"
        tree_builder._migrate_legacy_tree_if_needed(new_dir)

        assert (new_dir / "memory_tree.json").exists()
        assert (fake_legacy_dir / "memory_tree.json").exists(), "original must be left in place, never deleted"

    def test_migration_is_noop_when_target_already_has_data(self, tmp_path, monkeypatch):
        fake_legacy_dir = tmp_path / "legacy"
        fake_legacy_dir.mkdir()
        (fake_legacy_dir / "memory_tree.json").write_text('{"legacy": true}', encoding="utf-8")
        monkeypatch.setattr(tree_builder, "_LEGACY_TREE_DIR", fake_legacy_dir)

        new_dir = tmp_path / "new_location"
        new_dir.mkdir()
        (new_dir / "memory_tree.json").write_text('{"already_here": true}', encoding="utf-8")

        tree_builder._migrate_legacy_tree_if_needed(new_dir)

        assert "already_here" in (new_dir / "memory_tree.json").read_text(encoding="utf-8")

    def test_close_db_connection_resets_tree_singleton(self, tmp_path, monkeypatch):
        """The fixture used by the concurrency test only resets the SQL
        singleton via close_db_connection() — this proves that call also
        resets the MemoryTree singleton, with no test-file changes needed."""
        import core.memory.episodic as ep

        t1 = get_shared_tree(db_dir=tmp_path / "db", wiki_dir=tmp_path / "wiki")
        ep.close_db_connection()
        t2 = get_shared_tree(db_dir=tmp_path / "db2", wiki_dir=tmp_path / "wiki2")
        assert t1 is not t2


class TestOrphanedTmpCleanup:
    def test_dead_pid_tmp_file_is_removed_on_load(self, tmp_path):
        pytest.importorskip("psutil")
        db_dir = tmp_path / "db"
        db_dir.mkdir(parents=True)
        # An almost-certainly-dead PID (2**30 is far past any real process).
        dead_pid = 2**30
        orphan = db_dir / f"memory_tree.json.tmp{dead_pid}"
        orphan.write_text("{}", encoding="utf-8")
        assert orphan.exists()

        MemoryTree(db_dir=db_dir, wiki_dir=tmp_path / "wiki")

        assert not orphan.exists(), "orphaned tmp file from a dead pid must be cleaned up"

    def test_live_pid_tmp_file_is_kept(self, tmp_path):
        pytest.importorskip("psutil")
        import os

        db_dir = tmp_path / "db"
        db_dir.mkdir(parents=True)
        live = db_dir / f"memory_tree.json.tmp{os.getpid()}"
        live.write_text("{}", encoding="utf-8")

        MemoryTree(db_dir=db_dir, wiki_dir=tmp_path / "wiki")

        assert live.exists(), "must not delete a tmp file belonging to a live process"
        live.unlink()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        close_shared_tree()

        load_calls = {"n": 0}
        original_load = MemoryTree._load

        def counting_load(self):
            load_calls["n"] += 1
            return original_load(self)

        MemoryTree._load = counting_load
        tree = get_shared_tree(db_dir=tmp / "db", wiki_dir=tmp / "wiki")
        t0 = time.monotonic()
        for i in range(200):
            tree.ingest("test", "src", f"chunk {i}", topic="t")
        elapsed = time.monotonic() - t0
        MemoryTree._load = original_load

        assert load_calls["n"] == 1, f"expected 1 load, got {load_calls['n']}"
        assert elapsed < 5.0, f"200 ingests took {elapsed:.2f}s, expected well under 5s"
        close_shared_tree()
        print(f"200 ingests in {elapsed:.2f}s, _load() called {load_calls['n']}x")
    print("OK test_memory_tree_performance.py")
