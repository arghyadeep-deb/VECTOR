from __future__ import annotations

import json

import pytest

from core.security import secrets_manager
from core.security.secrets_manager import audit_secret, generate_secret, get_secret, record_secret_event


def test_secret_audit_reports_missing_without_value(monkeypatch):
    monkeypatch.delenv("VECTOR_TEST_SECRET", raising=False)
    monkeypatch.setattr(secrets_manager, "_keyring_get", lambda name: "")

    audit = audit_secret("VECTOR_TEST_SECRET", min_length=32)

    assert audit.configured is False
    assert audit.source == "missing"
    assert audit.strong is False


def test_secret_audit_uses_env_without_exposing_value(monkeypatch):
    monkeypatch.setenv("VECTOR_TEST_SECRET", "x" * 40)

    audit = audit_secret("VECTOR_TEST_SECRET", min_length=32)

    data = audit.to_dict()
    assert audit.configured is True
    assert audit.source == "env"
    assert audit.strong is True
    assert "x" * 40 not in json.dumps(data)


def test_get_secret_falls_back_to_keyring(monkeypatch):
    monkeypatch.delenv("VECTOR_TEST_SECRET", raising=False)
    monkeypatch.setattr(secrets_manager, "_keyring_get", lambda name: "from-keyring")

    assert get_secret("VECTOR_TEST_SECRET") == "from-keyring"


def test_generate_secret_has_entropy_shape():
    value = generate_secret(32)

    assert isinstance(value, str)
    assert len(value) >= 32


def test_secret_event_audit_is_metadata_only(monkeypatch, tmp_path):
    monkeypatch.setattr(secrets_manager, "get_data_root", lambda: tmp_path)

    record_secret_event("rotate", "VECTOR_TEST_SECRET", "keyring", True)

    audit_file = tmp_path / "security" / "secrets_audit.jsonl"
    event = json.loads(audit_file.read_text(encoding="utf-8").strip())
    assert event["action"] == "rotate"
    assert event["name"] == "VECTOR_TEST_SECRET"
    assert "secret" not in event


def test_rotate_secret_rejects_env_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(secrets_manager, "get_data_root", lambda: tmp_path)

    with pytest.raises(ValueError):
        secrets_manager.rotate_secret("VECTOR_TEST_SECRET", backend="env")
