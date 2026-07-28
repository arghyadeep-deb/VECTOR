"""Verify core/api/middleware.py's auth_middleware accepts a WebAuthn-issued
session JWT as an alternative to the static VECTOR_API_KEY, without
weakening the existing static-key check or accepting an unrelated JWT type
(type confusion with the separate collections-engine auth system)."""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def app_client(monkeypatch):
    monkeypatch.setenv("VECTOR_API_KEY", "the-real-static-key-0123456789")
    monkeypatch.setenv("VECTOR_JWT_SECRET", "test-jwt-secret-" + "y" * 40)

    from core.api import middleware
    import importlib
    importlib.reload(middleware)

    app = FastAPI()

    @app.get("/protected")
    async def protected():
        return {"ok": True}

    app.middleware("http")(middleware.auth_middleware)
    client = TestClient(app)
    return client, middleware


def test_static_key_still_works(app_client):
    client, _ = app_client
    resp = client.get("/protected", headers={"Authorization": "Bearer the-real-static-key-0123456789"})
    assert resp.status_code == 200


def test_no_credential_rejected(app_client):
    client, _ = app_client
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_wrong_static_key_rejected(app_client):
    client, _ = app_client
    resp = client.get("/protected", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_valid_webauthn_session_jwt_accepted(app_client):
    client, middleware = app_client
    from core.collections.auth import JWTManager
    jwt_mgr = JWTManager()
    token = jwt_mgr.issue({"sub": "vector-owner", "via": "webauthn"}, 3600, "webauthn_session")
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_expired_webauthn_jwt_rejected(app_client):
    client, middleware = app_client
    from core.collections.auth import JWTManager
    jwt_mgr = JWTManager(access_ttl=-10)
    token = jwt_mgr.issue({"sub": "vector-owner"}, -10, "webauthn_session")
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_wrong_token_type_rejected_type_confusion(app_client):
    """A JWT minted for a different purpose (e.g. the collections-engine's own
    'access' tokens) must NOT grant VECTOR API access just because it's
    signed with the same secret — expected_type='webauthn_session' must be
    enforced, not just 'any valid signature'."""
    client, middleware = app_client
    from core.collections.auth import JWTManager
    jwt_mgr = JWTManager()
    token = jwt_mgr.issue({"sub": "some-collections-user"}, 3600, "access")
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_garbage_token_rejected(app_client):
    client, _ = app_client
    resp = client.get("/protected", headers={"Authorization": "Bearer not.a.jwt.at.all"})
    assert resp.status_code == 401


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
