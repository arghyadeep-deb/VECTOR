"""Regression tests for OD-57 fail-closed database opens and HUD argv safety."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


def _uninitialized_shared_facts(db_path: Path):
    from core.memory.shared_facts import SharedFacts

    shared_facts = object.__new__(SharedFacts)
    shared_facts._db = str(db_path)
    return shared_facts


def test_shared_facts_sqlcipher_open_failure_propagates(monkeypatch, tmp_path):
    from core.memory import episodic

    monkeypatch.setattr(episodic, "_USE_SQLCIPHER", True)
    monkeypatch.setattr(
        episodic,
        "_open_sqlcipher_connection",
        lambda path: (_ for _ in ()).throw(RuntimeError("key unavailable")),
    )

    with pytest.raises(RuntimeError, match="key unavailable"):
        _uninitialized_shared_facts(tmp_path / "shared_facts.db")._open_conn()


def test_db_registry_main_db_sqlcipher_open_failure_propagates(monkeypatch, tmp_path):
    from core.memory import db_registry, episodic

    monkeypatch.setattr(db_registry, "configured_db_path", lambda: tmp_path / "main.db")
    monkeypatch.setattr(episodic, "_USE_SQLCIPHER", True)
    monkeypatch.setattr(
        episodic,
        "_open_sqlcipher_connection",
        lambda path: (_ for _ in ()).throw(RuntimeError("wrong key")),
    )

    with pytest.raises(RuntimeError, match="wrong key"):
        db_registry.get_district_db("core.episodic")


def test_sqlcipher_happy_paths_return_working_connections(monkeypatch, tmp_path):
    from core.memory import db_registry, episodic

    shared_connection = sqlite3.connect(":memory:")
    registry_connection = sqlite3.connect(":memory:")
    opened_paths: list[str] = []

    def open_encrypted(path: str):
        opened_paths.append(path)
        return shared_connection if len(opened_paths) == 1 else registry_connection

    monkeypatch.setattr(episodic, "_USE_SQLCIPHER", True)
    monkeypatch.setattr(episodic, "_open_sqlcipher_connection", open_encrypted)
    monkeypatch.setattr(db_registry, "configured_db_path", lambda: tmp_path / "main.db")

    actual_shared = _uninitialized_shared_facts(tmp_path / "shared.db")._open_conn()
    actual_registry = db_registry.get_district_db("core.episodic")
    try:
        assert actual_shared is shared_connection
        assert actual_registry is registry_connection
        assert actual_shared.execute("SELECT 1").fetchone()[0] == 1
        assert actual_registry.execute("SELECT 1").fetchone()[0] == 1
        assert opened_paths == [str(tmp_path / "shared.db"), str(tmp_path / "main.db")]
    finally:
        actual_shared.close()
        actual_registry.close()


def test_hud_api_key_is_absent_from_browser_argv(monkeypatch, tmp_path):
    import core.voice.ambient_listener as ambient_listener

    secret = "OD57-DISTINCTIVE-SECRET"
    popen_calls: list[list[str]] = []
    bootstrap_contents: list[str] = []

    monkeypatch.setenv("VECTOR_API_KEY", secret)
    monkeypatch.setattr(ambient_listener.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(ambient_listener.os.path, "exists", lambda path: True)
    monkeypatch.setattr(
        ambient_listener.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    def capture_popen(argv, **kwargs):
        popen_calls.append(argv)
        bootstrap_path = Path(argv[1].removeprefix("--app=file:///"))
        bootstrap_contents.append(bootstrap_path.read_text(encoding="utf-8"))
        return SimpleNamespace()

    monkeypatch.setattr(ambient_listener.subprocess, "Popen", capture_popen)
    monkeypatch.setattr(ambient_listener._time, "sleep", lambda seconds: None)

    listener = object.__new__(ambient_listener.AmbientListener)
    listener._summon_hud()

    assert len(popen_calls) == 1
    assert all(secret not in argument for argument in popen_calls[0])
    assert popen_calls[0][1].startswith("--app=file:")
    assert secret in bootstrap_contents[0]
    assert not list(tmp_path.glob("vector_hud_*.html"))
