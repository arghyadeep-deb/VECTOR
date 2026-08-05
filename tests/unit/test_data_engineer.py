"""Tests for districts/data_analytics/data_engineer.py — previously ZERO
coverage, which let a real bug run unnoticed: _open_db() called plain
sqlite3.connect() on the SQLCipher-encrypted main DB, so every call failed
with "file is not a database" and returned None. Every pipeline check this
agent performs was a silent no-op — 612 such errors in a single live run's
log. Fixed in commit 21ecdc437.

These tests would have caught it: they open a REAL SQLCipher-encrypted DB
(not a mock) and assert on actual query results, including the subtle half
of the bug — sqlite3.Row on a sqlcipher3 cursor raises "Row() argument 1
must be sqlite3.Cursor, not sqlcipher3.dbapi2.Cursor" — which only surfaces
on a real fetchone()/fetchall() call, not on "connection is not None".

Isolation: mirrors tests/unit/test_memory_decay.py's `isolated_episodic`
fixture exactly (tmp_path + VECTOR_DB_PATH/VECTOR_DB_KEY monkeypatch +
close_db_connection() before/after) so nothing here ever touches the
owner's production vector_memory.db. DataEngineer.VECTOR_DB_PATH is a CLASS
attribute resolved once at module-import time via configured_db_path(), so
monkeypatching the env var alone is not enough to redirect an
already-imported class — each test additionally overrides the AGENT
INSTANCE's .VECTOR_DB_PATH (every method in data_engineer.py reads
self.VECTOR_DB_PATH, so the instance attribute shadows the class default).
"""
from __future__ import annotations

import sqlite3

import pytest

from districts.data_analytics.data_engineer import DataEngineer


@pytest.fixture()
def isolated_engineer(tmp_path, monkeypatch):
    """A DataEngineer wired to a fresh, isolated SQLCipher-encrypted DB.

    Populates the DB through the real episodic module (the only writer),
    then hands back a DataEngineer instance pointed at that same file via an
    instance-level VECTOR_DB_PATH override — never the production DB.
    """
    db_path = tmp_path / "isolated_data_engineer.db"
    monkeypatch.setenv("VECTOR_DB_PATH", str(db_path))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_data_engineer_isolation")

    import core.memory.episodic as ep
    ep.close_db_connection()

    # Populate via the real singleton — this both creates the schema
    # (episodic_memory + friends) AND encrypts the file with SQLCipher,
    # exactly like the real vector_memory.db data_engineer must read.
    conn = ep.get_db_connection()
    conn.execute(
        "INSERT INTO episodic_memory "
        "(id, event_type, content, tags, context_snapshot, timestamp, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("test-row-1", "observation", "hello from isolated db",
         None, None, "2026-01-01T00:00:00Z", "test"),
    )
    conn.commit()

    agent = DataEngineer()
    agent.VECTOR_DB_PATH = db_path  # instance override — see module docstring

    yield agent, db_path, ep

    ep.close_db_connection()


# ── _open_db() ──────────────────────────────────────────────────────────────

def test_open_db_returns_connection_with_working_by_name_row_access(isolated_engineer):
    """The core regression test. A prior fix attempt returned a non-None
    connection but paired a sqlcipher3 cursor with sqlite3.Row, which raises
    on the very first fetch — "connection is not None" alone would NOT have
    caught that. This asserts on a real query's by-name column access."""
    agent, db_path, ep = isolated_engineer

    conn = agent._open_db()
    assert conn is not None, "_open_db() must return a usable connection against a SQLCipher DB"

    try:
        row = conn.execute(
            "SELECT * FROM episodic_memory WHERE id=?", ("test-row-1",)
        ).fetchone()
        assert row is not None
        # By-NAME access — this is exactly what raised
        # "Row() argument 1 must be sqlite3.Cursor, not sqlcipher3.dbapi2.Cursor"
        # in the first fix attempt.
        assert row["content"] == "hello from isolated db"
        assert row["event_type"] == "observation"
        assert row["source"] == "test"
    finally:
        conn.close()


def test_open_db_uses_matching_row_factory_for_the_driver(isolated_engineer):
    """Regression for the specific driver-mismatch bug: the Row class must
    come from whichever driver actually opened the connection."""
    agent, db_path, ep = isolated_engineer
    if not ep._USE_SQLCIPHER:
        pytest.skip("sqlcipher3 not installed in this environment")

    from sqlcipher3 import dbapi2 as sqlcipher_dbapi

    conn = agent._open_db()
    try:
        assert conn.row_factory is sqlcipher_dbapi.Row, (
            "a SQLCipher connection must use sqlcipher3's Row class, not sqlite3.Row"
        )
    finally:
        conn.close()


def test_plain_sqlite_connect_fails_on_the_same_encrypted_file(isolated_engineer):
    """Documents the original bug's exact failure mode: plain sqlite3.connect()
    against this same file opens 'successfully' (connect() doesn't validate
    format) but the first real query raises 'file is not a database'."""
    agent, db_path, ep = isolated_engineer
    if not ep._USE_SQLCIPHER:
        pytest.skip("sqlcipher3 not installed in this environment — DB isn't actually encrypted")

    plain_conn = sqlite3.connect(str(db_path))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            plain_conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()
    finally:
        plain_conn.close()


def test_open_db_connection_is_independent_of_shared_singleton(isolated_engineer):
    """_open_db() must hand back its OWN connection, not the shared singleton
    from get_db_connection() — callers here close what they're given, and
    closing the shared singleton would take the rest of VECTOR's memory
    access down with it."""
    agent, db_path, ep = isolated_engineer

    singleton = ep.get_db_connection()
    own_conn = agent._open_db()

    assert own_conn is not None
    assert own_conn is not singleton, "_open_db() must not hand out the shared singleton connection"

    own_conn.close()

    # Closing the agent's own connection must NOT have damaged the shared one.
    row = singleton.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()
    assert row[0] >= 1


def test_open_db_returns_none_when_db_file_missing(tmp_path):
    """No DB file at all → graceful None, not an exception."""
    agent = DataEngineer()
    agent.VECTOR_DB_PATH = tmp_path / "does_not_exist.db"
    assert agent._open_db() is None


# ── inspect_pipeline_health() ────────────────────────────────────────────────

def test_inspect_pipeline_health_returns_real_data_not_a_silent_failure(isolated_engineer):
    """This is the exact method that logged 612 no-op errors in production.
    With the fix, it must report real table stats instead of
    health_score=0 / 'Cannot open database'."""
    agent, db_path, ep = isolated_engineer

    health = agent.inspect_pipeline_health()

    assert health["db_exists"] is True
    assert "Cannot open database" not in health.get("issues", [])
    assert health["health_score"] > 0
    assert "episodic_memory" in health["tables"]
    assert health["tables"]["episodic_memory"]["exists"] is True
    assert health["tables"]["episodic_memory"]["rows"] >= 1


def test_inspect_pipeline_health_reports_wal_mode(isolated_engineer):
    agent, db_path, ep = isolated_engineer
    health = agent.inspect_pipeline_health()
    assert health["wal_mode"] is True


# ── other _open_db() callers — same bug, same blast radius ──────────────────

def test_generate_data_contract_returns_real_columns(isolated_engineer):
    agent, db_path, ep = isolated_engineer
    contract = agent.generate_data_contract("episodic_memory")
    assert "error" not in contract
    assert len(contract["columns"]) > 0
    assert any(c["name"] == "content" for c in contract["columns"])


def test_profile_dataset_returns_real_profile(isolated_engineer):
    agent, db_path, ep = isolated_engineer
    profile = agent.profile_dataset("episodic_memory", limit=100)
    assert "error" not in profile
    assert profile["total_rows"] >= 1
    assert "content" in profile["profile"]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-v"]))
