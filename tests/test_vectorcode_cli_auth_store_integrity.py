"""Regression for vectorcode/src/cli/auth.py's AuthManager file-store handling:

_load_file_store() silently returned {} on a corrupted/unparseable
credentials.json instead of raising -- add()/remove() would then treat the
store as empty and overwrite it on the next save, permanently destroying
every other stored credential's metadata. _save_file_store() also wrote
directly to the final path with no atomicity, so a crash mid-write could
itself produce exactly that corrupted file.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _load_auth_module():
    import vectorcode.src.cli.auth as auth

    return importlib.reload(auth)


def test_corrupted_store_raises_instead_of_silently_emptying(tmp_path, monkeypatch):
    auth = _load_auth_module()
    store_path = tmp_path / "credentials.json"
    store_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(auth.AuthManager, "STORAGE_PATH", store_path)

    mgr = auth.AuthManager()
    mgr._keyring_available = False

    with pytest.raises(auth.CredentialStoreCorruptedError):
        mgr._load_file_store()

    # The corrupted file must be left untouched, not silently replaced.
    assert store_path.read_text(encoding="utf-8") == "{not valid json"


def test_add_does_not_overwrite_a_corrupted_store(tmp_path, monkeypatch):
    auth = _load_auth_module()
    store_path = tmp_path / "credentials.json"
    original = '{"existing-cred": {"provider": "openai", "hint": "abcd"}}'
    store_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(auth.AuthManager, "STORAGE_PATH", store_path)

    mgr = auth.AuthManager()
    mgr._keyring_available = False

    # Simulate corruption appearing between reads (e.g. a crashed writer).
    store_path.write_text("{truncated", encoding="utf-8")

    with pytest.raises(auth.CredentialStoreCorruptedError):
        mgr.add("new-cred", "anthropic", "sk-test-key")

    assert store_path.read_text(encoding="utf-8") == "{truncated"


def test_handle_auth_prints_clean_error_on_corrupted_store(tmp_path, monkeypatch, capsys):
    auth = _load_auth_module()
    store_path = tmp_path / "credentials.json"
    store_path.write_text("not json at all", encoding="utf-8")
    monkeypatch.setattr(auth.AuthManager, "STORAGE_PATH", store_path)
    auth._auth_manager_instance = None
    monkeypatch.setattr(auth.AuthManager, "_probe_keyring", lambda self: False)

    class Args:
        auth_action = "list"

    auth.handle_auth(Args())

    captured = capsys.readouterr()
    assert "could not be parsed" in captured.out
    assert "Traceback" not in captured.out


def test_save_file_store_is_atomic_and_leaves_no_tmp_file(tmp_path, monkeypatch):
    auth = _load_auth_module()
    store_path = tmp_path / "credentials.json"
    monkeypatch.setattr(auth.AuthManager, "STORAGE_PATH", store_path)

    mgr = auth.AuthManager()
    mgr._keyring_available = False
    mgr._save_file_store({"a": {"provider": "openai", "hint": "aaaa"}})

    assert json.loads(store_path.read_text(encoding="utf-8")) == {
        "a": {"provider": "openai", "hint": "aaaa"}
    }
    assert list(tmp_path.glob(".credentials.json.*.tmp")) == []
