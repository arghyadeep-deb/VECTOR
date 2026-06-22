"""Coverage tests for core/security/secrets_manager.py"""

import os
import pytest

from core.security.secrets_manager import (
    audit_secret,
    audit_secrets,
    generate_secret,
    get_secret,
    record_secret_event,
    rotate_secret,
)


class TestGetSecret:
    def test_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("VECTOR_TEST_SECRET", "my-secret-value")
        assert get_secret("VECTOR_TEST_SECRET") == "my-secret-value"

    def test_returns_default_when_missing(self):
        assert get_secret("NONEXISTENT_SECRET_X", default="fallback") == "fallback"

    def test_returns_empty_default(self):
        assert get_secret("NONEXISTENT_SECRET_Y") == ""


class TestAuditSecret:
    def test_audits_env_secret(self, monkeypatch):
        monkeypatch.setenv("VECTOR_TEST_AUDIT", "a" * 40)
        result = audit_secret("VECTOR_TEST_AUDIT")
        assert result.configured is True
        assert result.source == "env"
        assert result.strong is True
        assert result.length == 40

    def test_audits_weak_secret(self, monkeypatch):
        monkeypatch.setenv("VECTOR_TEST_WEAK", "changeme")
        result = audit_secret("VECTOR_TEST_WEAK")
        assert result.configured is True
        assert result.strong is False

    def test_audits_short_secret(self, monkeypatch):
        monkeypatch.setenv("VECTOR_TEST_SHORT", "abc")
        result = audit_secret("VECTOR_TEST_SHORT")
        assert result.configured is True
        assert result.strong is False
        assert result.length == 3

    def test_audits_missing_secret(self):
        result = audit_secret("NONEXISTENT_AUDIT")
        assert result.configured is False
        assert result.source == "missing"

    def test_audit_multiple_secrets(self, monkeypatch):
        monkeypatch.setenv("SECRET_A", "x" * 32)
        monkeypatch.setenv("SECRET_B", "weak")
        results = audit_secrets(["SECRET_A", "SECRET_B", "SECRET_C"])
        assert len(results) == 3
        assert results[0].configured is True
        assert results[1].configured is True
        assert results[1].strong is False
        assert results[2].configured is False


class TestGenerateSecret:
    def test_generates_urlsafe_secret(self):
        secret = generate_secret(48)
        assert len(secret) >= 48
        assert isinstance(secret, str)

    def test_different_calls_different(self):
        s1 = generate_secret(32)
        s2 = generate_secret(32)
        assert s1 != s2


class TestRotateSecret:
    def test_rotate_fails_without_keyring(self, monkeypatch):
        monkeypatch.setattr("core.security.secrets_manager._keyring_set", lambda n, v: False)
        with pytest.raises(RuntimeError, match="OS keyring is unavailable"):
            rotate_secret("TEST_ROTATE", length=32)

    def test_rotate_rejects_non_keyring_backend(self):
        with pytest.raises(ValueError, match="Only keyring rotation is supported"):
            rotate_secret("TEST_ROTATE", backend="file")


class TestRecordEvent:
    def test_record_event_does_not_crash(self):
        record_secret_event("audit", "TEST_SECRET", "test", ok=True)
        record_secret_event("rotate", "OTHER_SECRET", "keyring", ok=False)
