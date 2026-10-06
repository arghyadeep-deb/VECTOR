"""Regression test: SQLiteMemory must surface a clear error when the SQLite
build lacks FTS5, instead of letting _create_tables() raise a cryptic
sqlite3.OperationalError("no such module: fts5").

_check_fts5() existed in the module but had zero callers anywhere in the
repo -- a "built but never wired" safety check.
"""

from __future__ import annotations

import sys
import types

import pytest

import vectorcode.src.vc_tools.storage.sqlite as sqlite_backend


def _stub_rust_bridge_module_that_fails(monkeypatch) -> None:
    stub = types.ModuleType("vectorcode.src._rust_bridge")

    def _get_rust_module():
        raise ImportError("no rust backend in test")

    stub.get_rust_module = _get_rust_module
    monkeypatch.setitem(sys.modules, "vectorcode.src._rust_bridge", stub)


def test_missing_fts5_raises_clear_runtime_error(tmp_path, monkeypatch) -> None:
    _stub_rust_bridge_module_that_fails(monkeypatch)
    monkeypatch.setattr(sqlite_backend, "_check_fts5", lambda conn: False)

    with pytest.raises(RuntimeError, match="FTS5"):
        sqlite_backend.SQLiteMemory(db_path=tmp_path / "memory.db")


def test_available_fts5_creates_backend_normally(tmp_path, monkeypatch) -> None:
    _stub_rust_bridge_module_that_fails(monkeypatch)
    backend = sqlite_backend.SQLiteMemory(db_path=tmp_path / "memory2.db")
    try:
        assert backend.count() == 0
    finally:
        backend.close()
