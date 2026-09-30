"""Regression test for core/experiments/ab_testing.py's raw-sqlite3-connect
bypass bug, found by Codex's core/ SQLite triage (2026-09-30, part of the
Phase 3 whole-repo audit's Claude/Codex split).

ExperimentRegistry._conn() and Experiment.record()/stats() all opened
sqlite3.connect(self._db, ...) directly against configured_db_path() (the
main DB) with zero SQLCipher awareness. Against the real production main DB
(SQLCipher-encrypted), that raw connect fails outright with "file is not a
database" -- this module has no broad except-and-swallow, so every
ExperimentRegistry/Experiment call would simply crash in production.

Fixed by adding a shared _get_conn(db_path) helper (mirrors
core/queue/retry_queue.py::RetryQueue._conn()'s established pattern:
delegate to core.memory.episodic.get_db_connection() when db_path is the
real main DB, else return a private connection the caller closes) and
routing every call site in both classes through it.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.experiments.ab_testing import ExperimentRegistry, Experiment, _get_conn
from core.memory.db_utils import configured_db_path


def _isolated_registry() -> ExperimentRegistry:
    db_path = Path(tempfile.mkdtemp()) / "test_ab.db"
    return ExperimentRegistry(db_path=db_path)


def test_get_conn_returns_private_for_non_main_db():
    conn, private = _get_conn(str(Path(tempfile.mkdtemp()) / "custom.db"))
    try:
        assert private is True
        assert conn is not None
    finally:
        conn.close()


def test_get_conn_delegates_to_shared_singleton_for_main_db():
    conn, private = _get_conn(str(configured_db_path()))
    assert private is False
    # never close the shared singleton here


def test_create_and_get_experiment_round_trip():
    reg = _isolated_registry()
    exp = reg.create("model_compare", variants=["a", "b"], description="test")
    assert exp.name == "model_compare"
    assert exp.variants == ["a", "b"]

    fetched = reg.get_experiment("model_compare")
    assert fetched is not None
    assert fetched.id == exp.id


def test_create_is_idempotent_by_name():
    reg = _isolated_registry()
    exp1 = reg.create("dup", variants=["x", "y"])
    exp2 = reg.create("dup", variants=["x", "y"])
    assert exp1.id == exp2.id


def test_list_active_and_deactivate():
    reg = _isolated_registry()
    reg.create("exp_a", variants=["1", "2"])
    reg.create("exp_b", variants=["1", "2"])
    assert len(reg.list_active()) == 2

    reg.deactivate("exp_a")
    active = reg.list_active()
    assert len(active) == 1
    assert active[0].name == "exp_b"


def test_experiment_record_and_stats_use_private_conn_for_isolated_db():
    reg = _isolated_registry()
    exp = reg.create("record_test", variants=["control", "treatment"])

    for i in range(10):
        exp.record(f"subject_{i}", "control", "reward", 0.5)
    for i in range(10):
        exp.record(f"subject_{i}", "treatment", "reward", 0.8)

    stats = exp.stats("reward")
    assert stats["control"]["n"] == 10
    assert stats["treatment"]["n"] == 10
    assert stats["treatment"]["mean"] > stats["control"]["mean"]


def test_experiment_stores_db_path_matching_registry():
    reg = _isolated_registry()
    exp = reg.create("db_path_check", variants=["a", "b"])
    assert exp._db == reg._db


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
