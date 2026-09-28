"""/clear-site-data: recovery for a browser stuck on a removed HUD page (2026-09-25).

The removed "VECTOR Production" page lived on in the owner's Chrome (cached page + offline worker). The route needs no
auth, sends the Clear-Site-Data header for cache, cookies and storage, and only ever redirects to a same-origin path."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch):
    from core.api.app import create_app

    monkeypatch.setenv("VECTOR_API_KEY", "test-key")
    return TestClient(create_app(), client=("127.0.0.1", 50000))


def test_route_is_public_and_clears_cache_cookies_and_storage(monkeypatch):
    r = _client(monkeypatch).get("/clear-site-data")
    assert r.status_code == 200
    header = r.headers["clear-site-data"]
    assert '"cache"' in header and '"cookies"' in header and '"storage"' in header
    assert r.headers["cache-control"] == "no-store"


def test_redirect_only_stays_on_this_origin(monkeypatch):
    body = _client(monkeypatch).get("/clear-site-data").text
    # the script refuses anything that is not a single-slash path (no //evil.example, no full URLs)
    assert "n.charAt(0)!=='/'" in body and "n.charAt(1)==='/'" in body and "'/login'" in body


def test_route_exposes_no_vector_data(monkeypatch):
    body = _client(monkeypatch).get("/clear-site-data").text.lower()
    assert "agent" not in body and "goal" not in body and "api_key" not in body
