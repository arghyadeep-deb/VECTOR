"""Task 04 — comms service requires bearer auth on /send.

The comms bridge can bind 0.0.0.0, so unauthenticated callers must not be able
to trigger outbound messages. /status stays public.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_SERVICE = Path(__file__).resolve().parents[2] / "cloud" / "comms_service" / "service.py"
_KEY = "k" * 40


def _load_app():
    spec = importlib.util.spec_from_file_location("vector_comms_service_test", _SERVICE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VECTOR_API_KEY", _KEY)
    monkeypatch.delenv("VECTOR_ENV", raising=False)
    return TestClient(_load_app())


def test_status_is_public(client):
    r = client.get("/status")
    assert r.status_code == 200


def test_send_without_auth_is_401(client):
    r = client.post("/send", json={"platform": "telegram", "to": "x", "message": "hi"})
    assert r.status_code == 401


def test_send_wrong_token_is_401(client):
    r = client.post(
        "/send",
        json={"platform": "telegram", "to": "x", "message": "hi"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_send_correct_token_reaches_handler(client):
    r = client.post(
        "/send",
        json={"platform": "telegram", "to": "x", "message": "hi"},
        headers={"Authorization": f"Bearer {_KEY}"},
    )
    # handler reached (no channel configured in test → ok:false, but NOT 401)
    assert r.status_code == 200
    assert "ok" in r.json()


def test_production_without_key_fails_closed(monkeypatch):
    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.delenv("VECTOR_API_KEY", raising=False)
    c = TestClient(_load_app())
    r = c.post("/send", json={"platform": "telegram", "to": "x", "message": "hi"})
    assert r.status_code == 503


def test_dev_without_key_allows_localhost(monkeypatch):
    monkeypatch.delenv("VECTOR_ENV", raising=False)
    monkeypatch.delenv("VECTOR_API_KEY", raising=False)
    c = TestClient(_load_app())
    r = c.post("/send", json={"platform": "telegram", "to": "x", "message": "hi"})
    assert r.status_code == 200  # dev convenience, not 401/503
