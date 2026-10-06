"""Regression tests for the 2026-10-06 vector_cli batch-B audit."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vectorcode.src.vector_cli import profile_distribution, vault_cmd, webhook


def test_profile_distribution_git_clone_terminates_git_options(monkeypatch, tmp_path):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(profile_distribution.subprocess, "run", fake_run)
    profile_distribution._git_clone("-uploader=malicious", tmp_path / "clone")

    assert captured["argv"] == [
        "git", "clone", "--depth", "1", "--", "-uploader=malicious",
        str(tmp_path / "clone"),
    ]


def test_webhook_rejects_non_object_store(monkeypatch, tmp_path):
    path = tmp_path / "webhook_subscriptions.json"
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(webhook, "_subscriptions_path", lambda: path)

    with pytest.raises(webhook.SubscriptionsLoadError, match="JSON object"):
        webhook._load_subscriptions()


def test_webhook_atomic_save_preserves_original_when_replace_fails(monkeypatch, tmp_path):
    path = tmp_path / "webhook_subscriptions.json"
    path.write_text('{"original": {}}', encoding="utf-8")
    monkeypatch.setattr(webhook, "_subscriptions_path", lambda: path)

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(webhook.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        webhook._save_subscriptions({"replacement": {}})

    assert json.loads(path.read_text(encoding="utf-8")) == {"original": {}}
    assert list(tmp_path.glob(".webhook_subscriptions.json.*.tmp")) == []


def test_vault_atomic_save_preserves_original_when_replace_fails(monkeypatch, tmp_path):
    vault_file = tmp_path / "vault.enc"
    key_file = tmp_path / ".vault_key"
    monkeypatch.setattr(vault_cmd, "DEFAULT_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(vault_cmd, "_VAULT_FILE", vault_file)
    monkeypatch.setattr(vault_cmd, "_VAULT_KEY_FILE", key_file)

    vault_cmd._save_vault({"original": "secret"})
    original = vault_file.read_bytes()

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(vault_cmd.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        vault_cmd._save_vault({"replacement": "secret"})

    assert vault_file.read_bytes() == original
    assert list(tmp_path.glob(".vault.enc.*.tmp")) == []


def test_setup_tts_neutts_branch_uses_module_level_import(monkeypatch):
    from vectorcode.src.vector_cli import setup

    monkeypatch.setattr(setup, "managed_nous_tools_enabled", lambda: False)
    monkeypatch.setattr(
        setup,
        "get_nous_subscription_features",
        lambda _config: SimpleNamespace(nous_auth_present=False),
    )
    monkeypatch.setattr(setup, "prompt_choice", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(setup.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(setup, "save_config", lambda _config: None)

    config = {"tts": {"provider": "edge"}}
    setup._setup_tts_provider(config)

    assert config["tts"]["provider"] == "neutts"
