"""Regression tests for core/memory/multi_db_manager.py::MultiDBManager.restore()'s
SQL-injection and path-traversal bugs, found by a Claude self-fork's deep-verify
pass on core/api/routers/ batch 2 (Phase 3 whole-repo audit, 2026-09-30).

restore() f-string-interpolated table and column names taken directly from a
backup JSON file's own keys into DELETE FROM {table} / INSERT INTO {table}
({cols}) with zero validation against the target database's real schema --
a crafted backup file's "tables" dict could carry arbitrary table/column
name strings straight into SQL. backup_path itself also had no path
confinement, so any file the process could read would be accepted as a
"backup".

Fixed by: confining backup_path to the VECTOR repo root, and validating
every table/column name against a freshly-queried real sqlite_master /
PRAGMA table_info result (plus the existing _SAFE_IDENTIFIER regex already
used elsewhere in this same file for write_local()) before it is ever
interpolated into SQL. Unknown tables/columns are skipped, not errored, so
a legitimate backup-then-restore round trip is unaffected.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory.multi_db_manager import MultiDBManager


def _make_target_db(tmp_path: Path) -> Path:
    """A minimal real target DB with one legitimate table, mirroring the
    shape restore() expects to operate against."""
    db_path = tmp_path / "target.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE episodic_memory (id TEXT PRIMARY KEY, content TEXT)")
    conn.commit()
    conn.close()
    return db_path


def _repo_root_temp_json() -> Path:
    """A real file under the repo root (required by the path-confinement
    fix) without leaking an open file descriptor on Windows."""
    fd, raw_path = tempfile.mkstemp(dir=str(Path(__file__).resolve().parent.parent), suffix=".json")
    os.close(fd)
    return Path(raw_path)


def _restore_against(monkeypatch, db_path: Path, backup_path: Path, overwrite: bool = False) -> dict:
    monkeypatch.setattr(
        "core.memory.db_utils.configured_db_path", lambda: db_path
    )
    mgr = MultiDBManager.__new__(MultiDBManager)  # bypass __init__'s own DB wiring
    return mgr.restore(str(backup_path), overwrite=overwrite)


def test_malicious_table_name_is_not_interpolated_into_sql(tmp_path, monkeypatch):
    db_path = _make_target_db(tmp_path)
    backup_path = _repo_root_temp_json()
    try:
        malicious = {
            "version": 1,
            "tables": {
                "episodic_memory; DROP TABLE episodic_memory; --": [{"id": "x", "content": "y"}],
            },
        }
        backup_path.write_text(json.dumps(malicious), encoding="utf-8")

        result = _restore_against(monkeypatch, db_path, backup_path)

        assert result["tables_restored"] == 0
        assert result["rows_restored"] == 0
        conn = sqlite3.connect(str(db_path))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "episodic_memory" in tables, "malicious table name must not have dropped the real table"
    finally:
        backup_path.unlink(missing_ok=True)


def test_malicious_column_name_is_not_interpolated_into_sql(tmp_path, monkeypatch):
    db_path = _make_target_db(tmp_path)
    backup_path = _repo_root_temp_json()
    try:
        malicious = {
            "version": 1,
            "tables": {
                "episodic_memory": [
                    {"id": "x", "content); DROP TABLE episodic_memory; --": "y"}
                ],
            },
        }
        backup_path.write_text(json.dumps(malicious), encoding="utf-8")

        # Must not raise and must not drop the table; the unknown column is
        # silently skipped, leaving only recognized columns (here: "id").
        result = _restore_against(monkeypatch, db_path, backup_path)

        conn = sqlite3.connect(str(db_path))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "episodic_memory" in tables
        assert result["tables_restored"] == 1
    finally:
        backup_path.unlink(missing_ok=True)


def test_backup_path_outside_repo_root_is_refused(tmp_path, monkeypatch):
    db_path = _make_target_db(tmp_path)
    outside_file = tmp_path / "not_a_real_backup.json"
    outside_file.write_text(json.dumps({"version": 1, "tables": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="outside the VECTOR repo root"):
        _restore_against(monkeypatch, db_path, outside_file)


def test_legitimate_round_trip_still_works(tmp_path, monkeypatch):
    db_path = _make_target_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO episodic_memory (id, content) VALUES ('1', 'hello')")
    conn.commit()
    conn.close()

    backup_path = _repo_root_temp_json()
    try:
        monkeypatch.setattr("core.memory.db_utils.configured_db_path", lambda: db_path)
        mgr = MultiDBManager.__new__(MultiDBManager)
        real_path = mgr.backup(str(backup_path))
        assert real_path == str(backup_path)

        # Wipe and restore
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM episodic_memory")
        conn.commit()
        conn.close()

        result = _restore_against(monkeypatch, db_path, backup_path, overwrite=True)
        assert result["tables_restored"] == 1
        assert result["rows_restored"] == 1

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT id, content FROM episodic_memory").fetchall()
        conn.close()
        assert rows == [("1", "hello")]
    finally:
        backup_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
