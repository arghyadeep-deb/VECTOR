"""Regression test — core/memory/db_registry.py:get_district_db() SQLCipher
landmine (memory-persistence audit 2026-08-05, Finding #4, MEDIUM/latent).

Root cause: three registry entries ("core.episodic", "core.collections",
"core.causal_graph") point path_template at "vector_memory.db" — the main
SQLCipher-encrypted memory DB — but get_district_db()'s factory always
opened with plain sqlite3.connect(). Calling get_district_db() with any of
those keys would hit the same "file is not a database" failure already
fixed (2026-08-05/06) for core/memory/shared_facts.py and
districts/data_analytics/data_engineer.py. Unreachable in production
(nothing calls get_district_db() with those keys today) — a landmine, not
a live bug — but a future caller following this module's own documented
usage pattern would have hit it immediately.

Fix: get_district_db() now special-cases path_template == "vector_memory.db"
and opens through episodic._open_sqlcipher_connection() (SQLCipher-keyed)
when SQLCipher is active, following the precedent in
districts/emergency/log.py:_open_conn() and core/memory/shared_facts.py.
Genuinely separate district DBs (data/{name}.db, data/emergency_log.db,
etc.) are untouched — they still open with plain sqlite3.connect().

This test proves, with a REAL query and by-NAME column access (not just
"connection is not None" — that exact gap let the row_factory trap slip
through undetected on data_engineer's first fix attempt):
1. get_district_db("core.episodic") opens the SQLCipher-encrypted DB
   correctly and by-name column access works (the row_factory trap:
   sqlite3.Row on a sqlcipher cursor raises "Row() argument 1 must be
   sqlite3.Cursor, not sqlcipher3.dbapi2.Cursor").
2. A genuinely separate, unencrypted district DB (e.g.
   "districts.emergency.log") still opens fine and also supports by-name
   access (row_factory is now applied uniformly).

Uses an isolated VECTOR_DB_PATH/VECTOR_DB_KEY (mirrors
tests/unit/test_agent_registry_successor_class.py::isolated_episodic) so
this NEVER touches the real production vector_memory.db.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def isolated_db_env(tmp_path, monkeypatch):
    """Fresh, isolated SQLCipher-keyed DB path per test — never touches the
    real production vector_memory.db."""
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "db_registry_landmine_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_isolated_db_registry_landmine")
    import core.memory.episodic as ep
    ep.close_db_connection()
    yield tmp_path
    ep.close_db_connection()


def test_get_district_db_core_episodic_opens_encrypted_db_with_by_name_access(isolated_db_env):
    """The exact landmine: get_district_db("core.episodic") must open the
    SQLCipher-encrypted main DB successfully and support by-NAME column
    access — a plain sqlite3.connect() against a SQLCipher file raises
    "file is not a database" immediately, and even a fixed connection can
    still fail later at the row_factory trap if the Row class doesn't match
    the driver."""
    import core.memory.episodic as ep
    assert ep._USE_SQLCIPHER, (
        "this test requires sqlcipher3 to be installed/active in this "
        "environment (it is, per the memory-persistence audit) — if this "
        "assertion fires the environment changed and the test needs revisiting"
    )

    from core.memory.db_registry import get_district_db

    conn = get_district_db("core.episodic")
    try:
        # Real query, by-NAME column access — proves both the SQLCipher
        # open succeeded AND the row_factory matches the connection's
        # driver (sqlite3.Row on a sqlcipher3 cursor raises TypeError).
        conn.execute(
            "CREATE TABLE IF NOT EXISTS landmine_probe (id INTEGER PRIMARY KEY, label TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO landmine_probe (label) VALUES (?)", ("hello-encrypted",))
        conn.commit()

        row = conn.execute(
            "SELECT id, label FROM landmine_probe WHERE label = ?", ("hello-encrypted",)
        ).fetchone()
        assert row is not None
        # By-NAME access — this is the part a bare "connection is not None"
        # assertion would never catch.
        assert row["label"] == "hello-encrypted"
        assert row["id"] == 1
    finally:
        conn.close()


def test_get_district_db_separate_unencrypted_db_still_works(isolated_db_env, monkeypatch, tmp_path):
    """A genuinely separate district DB (not an alias of vector_memory.db)
    must be untouched by the fix — still opens with plain sqlite3.connect(),
    still supports by-name access.

    _project_root() is redirected into tmp_path so this test never writes
    into the real repo's data/ directory (get_district_db() for
    non-aliased keys derives its path from _project_root(), unlike the
    core.* keys which now go through configured_db_path())."""
    import core.memory.db_registry as db_registry
    from core.memory.db_registry import get_district_db, REGISTRY

    entry = REGISTRY["districts.emergency.log"]
    assert entry.path_template != "vector_memory.db", (
        "sanity check: this entry must be a genuinely separate file, not "
        "an alias of the encrypted main DB"
    )

    fake_root = tmp_path / "fake_project_root"
    monkeypatch.setattr(db_registry, "_project_root", lambda: fake_root)

    conn = get_district_db("districts.emergency.log")
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS separate_db_probe (id INTEGER PRIMARY KEY, label TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO separate_db_probe (label) VALUES (?)", ("hello-separate",))
        conn.commit()

        row = conn.execute(
            "SELECT id, label FROM separate_db_probe WHERE label = ?", ("hello-separate",)
        ).fetchone()
        assert row is not None
        assert row["label"] == "hello-separate"

        # It really is a separate physical file, isolated under tmp_path —
        # not the encrypted main DB, and not the real repo's data/ dir.
        abs_path = fake_root / entry.path_template
        assert abs_path.exists()
        assert abs_path != isolated_db_env / "db_registry_landmine_test.db"
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
