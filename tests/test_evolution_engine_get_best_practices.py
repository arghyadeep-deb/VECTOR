"""Regression for core/city/evolution_engine.py's get_best_practices():

close_db_connection(conn) was called in a `finally` block after every query.
close_db_connection() takes zero arguments, so this call always raised
TypeError at the argument-binding stage -- before close_db_connection()'s
body ever ran, meaning the shared singleton connection was never actually
closed in practice. But the TypeError still propagated out of the inner
`finally`, was caught by the method's own broad `except Exception`, and
logged as a misleading "get_best_practices query failed" warning on every
single call, even when the query itself succeeded and real data was
returned. The call was also wrong on principle even with a fixed arg count:
get_db_connection() returns a process-wide singleton (KNOWN_ISSUES #21), and
closing it from a routine caller like this would poison memory access for
every other agent/thread in the system -- see core/api_manager.py's
_check_memory_health() for the documented precedent of never doing this.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "evolution_test.db"
    monkeypatch.setenv("VECTOR_DB_PATH", str(db_path))
    from core.memory import episodic

    episodic.close_db_connection()
    yield db_path
    episodic.close_db_connection()


def test_get_best_practices_does_not_log_a_spurious_query_failed_warning(
    isolated_db, monkeypatch
):
    from core.memory.episodic import get_db_connection
    from core.city import evolution_engine as ee

    conn = get_db_connection()
    ghost_memory = json.dumps(
        {"best_decisions": [{"decision": "always check cache first", "reward": 0.9}]}
    )
    conn.execute(
        "INSERT OR REPLACE INTO agent_history "
        "(agent_id, agent_name, district, generation, final_hp, ghost_memory, died_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("agent-1", "TestAgent", "test_district", 1, 0, ghost_memory, "2026-10-06"),
    )
    conn.commit()

    warnings = []
    monkeypatch.setattr(
        ee.logger, "warning", lambda *a, **k: warnings.append((a, k))
    )

    engine = ee.EvolutionEngine()
    practices = engine.get_best_practices("TestAgent")

    assert practices == ["always check cache first"]
    assert warnings == [], (
        "a successful query must not log a 'query failed' warning -- "
        f"got: {warnings}"
    )

    # The shared singleton must still be usable afterwards.
    conn2 = get_db_connection()
    conn2.execute("SELECT 1").fetchone()
