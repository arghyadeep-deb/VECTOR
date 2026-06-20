"""Tests for core/api/routers/keys.py provider-key endpoints.

Never touches the real .env — `_ENV_PATH` is monkeypatched to a tmp file for
every test that mutates state.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from core.api.routers import keys as keys_module


class _CsrfClient:
    """Wraps TestClient so every mutating call automatically carries a valid
    X-CSRF-Token (core/api/middleware.py enforces this on non-GET requests,
    independent of the VECTOR_API_KEY bearer auth)."""

    def __init__(self, inner: TestClient):
        self._inner = inner

    def _csrf_headers(self, headers: dict | None) -> dict:
        token = self._inner.get("/csrf-token").json()["csrf_token"]
        merged = dict(headers or {})
        merged["X-CSRF-Token"] = token
        return merged

    def get(self, *a, **kw):
        return self._inner.get(*a, **kw)

    def post(self, url, headers=None, **kw):
        return self._inner.post(url, headers=self._csrf_headers(headers), **kw)

    def delete(self, url, headers=None, **kw):
        return self._inner.delete(url, headers=self._csrf_headers(headers), **kw)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(keys_module, "_ENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text("", encoding="utf-8")
    monkeypatch.delenv("VECTOR_API_KEY", raising=False)
    for env_name in keys_module._PROVIDER_KEY_ALLOWLIST.values():
        monkeypatch.delenv(env_name, raising=False)

    from core.api.app import create_app

    return _CsrfClient(TestClient(create_app(), client=("127.0.0.1", 50000)))


def test_list_providers_returns_allowlist(client):
    r = client.get("/keys/providers")
    assert r.status_code == 200
    providers = r.json()["providers"]
    assert "anthropic" in providers
    assert providers["anthropic"]["configured"] is False
    assert providers["anthropic"]["env_name"] == "ANTHROPIC_KEY"


def test_list_providers_never_returns_raw_value(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_KEY", "sk-supersecretvalue12345")
    r = client.get("/keys/providers")
    body = r.text
    assert "supersecretvalue" not in body


def test_set_provider_key_writes_env_and_process(client, tmp_path):
    r = client.post("/keys/providers/anthropic", json={"value": "sk-test-123"})
    assert r.status_code == 200
    assert r.json()["env_name"] == "ANTHROPIC_KEY"
    assert os.environ["ANTHROPIC_KEY"] == "sk-test-123"
    assert "ANTHROPIC_KEY=sk-test-123" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_set_then_status_shows_configured(client):
    client.post("/keys/providers/groq", json={"value": "gsk-abc"})
    r = client.get("/keys/providers")
    assert r.json()["providers"]["groq"]["configured"] is True


def test_clear_provider_key_removes_it(client):
    client.post("/keys/providers/groq", json={"value": "gsk-abc"})
    r = client.delete("/keys/providers/groq")
    assert r.status_code == 200
    assert os.environ.get("GROQ_API_KEY", "") == ""
    r2 = client.get("/keys/providers")
    assert r2.json()["providers"]["groq"]["configured"] is False


def test_unknown_provider_rejected_on_set(client):
    r = client.post("/keys/providers/not_a_real_provider", json={"value": "x"})
    assert r.status_code == 404


def test_unknown_provider_rejected_on_clear(client):
    r = client.delete("/keys/providers/not_a_real_provider")
    assert r.status_code == 404


def test_internal_secret_not_settable_via_providers_endpoint(client):
    """VECTOR's own secrets must never be reachable through this allowlisted
    third-party-only endpoint — confirms the allowlist actually excludes them."""
    for name in ("vector_db", "vector_jwt", "mcp_kernel", "vector_brain"):
        r = client.post(f"/keys/providers/{name}", json={"value": "x"})
        assert r.status_code == 404, f"{name} should not be settable"


def test_empty_value_rejected(client):
    r = client.post("/keys/providers/anthropic", json={"value": "   "})
    assert r.status_code == 400


def test_newline_in_value_rejected(client):
    r = client.post("/keys/providers/anthropic", json={"value": "evil\nINJECTED=1"})
    assert r.status_code == 400


def test_set_requires_current_key_when_configured(client, monkeypatch):
    monkeypatch.setenv("VECTOR_API_KEY", "k" * 40)
    r = client.post("/keys/providers/anthropic", json={"value": "sk-x"})
    assert r.status_code == 401


def test_set_succeeds_with_correct_bearer_token(client, monkeypatch):
    monkeypatch.setenv("VECTOR_API_KEY", "k" * 40)
    r = client.post(
        "/keys/providers/anthropic",
        json={"value": "sk-x"},
        headers={"Authorization": "Bearer " + "k" * 40},
    )
    assert r.status_code == 200


if __name__ == "__main__":
    print("✅ test_provider_keys.py module loads")
