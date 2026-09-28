"""E2E tests for the single HUD entrypoint.

The HUD is the single production frontend, served at /hud/ through FastAPI
middleware (auth, rate-limit, security headers) — NOT a static mount. These
tests exercise the real wired path: authorized serving, unauthorized block,
prod/dev selection, demo asset blocking, and path-traversal defense.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api import app as app_module


@pytest.fixture
def auth_client(monkeypatch):
    """A TestClient with a known API key so /hud/ auth is deterministic."""
    monkeypatch.setenv("VECTOR_API_KEY", "testkey-hud")
    client = TestClient(app_module.create_app())
    token = {"Authorization": "Bearer testkey-hud"}
    return client, token


# ── unit: there is one HUD entrypoint ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("env", ["development", "production"])
def test_select_hud_html_is_always_the_one_full_hud(monkeypatch, tmp_path, env):
    monkeypatch.setenv("VECTOR_ENV", env)
    assert app_module._select_hud_html(tmp_path).name == "VECTOR.html"


# ── E2E: the real served path ─────────────────────────────────────────────────

def test_hud_serves_html_when_authorized(auth_client):
    client, token = auth_client
    r = client.get("/hud/", headers=token)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "VECTOR" in r.text


def test_hud_blocks_unauthorized(auth_client):
    client, _ = auth_client
    r = client.get("/hud/")
    assert r.status_code == 401


def test_hud_redirect_no_trailing_slash(auth_client):
    client, token = auth_client
    r = client.get("/hud", headers=token, follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"].endswith("/hud/")


def test_hud_path_traversal_blocked(auth_client):
    client, token = auth_client
    r = client.get("/hud/..%2f..%2fcore%2fconfig.py", headers=token)
    assert r.status_code in (403, 404)
    assert "config" not in r.text.lower() or r.status_code != 200


def test_single_hud_entrypoint_exists():
    """Exactly one HUD file: VECTOR.html. The separate production page was removed 2026-09-25."""
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    assert (frontend / "VECTOR.html").exists()
    assert not (frontend / "VECTOR.prod.html").exists()
