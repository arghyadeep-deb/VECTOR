"""FL-033 — Google Tasks token refresh (owner decision 2026-10-11: build the
refresh/retry/persistence logic now; a real authenticated probe against the
owner's own Google account is separate, owner-only follow-up).

Before this fix, GoogleTasksConnector._get_access_token() had no expiry
check or refresh at all (the method's own removed DESIGN NOTE said so
explicitly) -- sync() started failing with a 401 after Google's ~1h access
token lifetime until the owner manually re-authenticated. Mirrors the
already-working strava.py/spotify.py proactive-refresh pattern, using a new
shared refresh_google_token() helper in oauth.py (reusable by any
Google-based connector, not just Tasks).
"""
from __future__ import annotations

import json
import time

import httpx
import pytest

from vectorcode.src.connectors import google_tasks
from vectorcode.src.connectors import oauth as oauth_module


def _write_tokens(path, **overrides):
    tokens = {
        "access_token": "old-access",
        "refresh_token": "refresh-xyz",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "expires_at": time.time() - 1,  # already expired
    }
    tokens.update(overrides)
    path.write_text(json.dumps(tokens), encoding="utf-8")
    return tokens


def test_expired_token_is_refreshed_and_persisted(tmp_path, monkeypatch):
    credentials = tmp_path / "google_tasks.json"
    _write_tokens(credentials)

    monkeypatch.setattr(
        google_tasks,
        "refresh_google_token",
        lambda client_id, client_secret, refresh_token: {
            "access_token": "new-access",
            "refresh_token": "refresh-xyz",
            "expires_in": 3600,
        },
    )

    connector = google_tasks.GoogleTasksConnector(credentials_path=str(credentials))
    token = connector._get_access_token()

    assert token == "new-access"
    persisted = json.loads(credentials.read_text(encoding="utf-8"))
    assert persisted["access_token"] == "new-access"
    assert persisted["expires_at"] > time.time()


def test_fresh_token_is_not_refreshed(tmp_path, monkeypatch):
    credentials = tmp_path / "google_tasks.json"
    _write_tokens(credentials, access_token="still-fresh", expires_at=time.time() + 3600)

    called = []
    monkeypatch.setattr(
        google_tasks,
        "refresh_google_token",
        lambda *a, **k: called.append(1) or {"access_token": "should-not-be-used"},
    )

    connector = google_tasks.GoogleTasksConnector(credentials_path=str(credentials))
    token = connector._get_access_token()

    assert token == "still-fresh"
    assert called == []


def test_missing_refresh_pair_falls_back_to_existing_token(tmp_path):
    credentials = tmp_path / "google_tasks.json"
    credentials.write_text(json.dumps({"access_token": "legacy-token"}), encoding="utf-8")

    connector = google_tasks.GoogleTasksConnector(credentials_path=str(credentials))
    token = connector._get_access_token()

    assert token == "legacy-token"


def test_sync_retries_once_on_real_401_then_succeeds(tmp_path, monkeypatch):
    credentials = tmp_path / "google_tasks.json"
    _write_tokens(credentials, access_token="stale-but-looked-fresh", expires_at=time.time() + 3600)

    monkeypatch.setattr(
        google_tasks,
        "refresh_google_token",
        lambda *a, **k: {"access_token": "post-401-token", "expires_in": 3600},
    )

    calls = []

    def fake_api_get(token, endpoint, params=None):
        calls.append(token)
        if token == "stale-but-looked-fresh":
            request = httpx.Request("GET", "https://tasks.googleapis.com/x")
            response = httpx.Response(401, request=request)
            raise httpx.HTTPStatusError("unauthorized", request=request, response=response)
        return {"items": []}

    monkeypatch.setattr(google_tasks, "_tasks_api_get", fake_api_get)

    connector = google_tasks.GoogleTasksConnector(credentials_path=str(credentials))
    result = list(connector.sync())

    assert result == []
    assert calls == ["stale-but-looked-fresh", "post-401-token"]
    assert connector.sync_status().state == "idle"


def test_sync_does_not_retry_on_a_non_401_error(tmp_path, monkeypatch):
    credentials = tmp_path / "google_tasks.json"
    _write_tokens(credentials, expires_at=time.time() + 3600)

    def fake_api_get(token, endpoint, params=None):
        request = httpx.Request("GET", "https://tasks.googleapis.com/x")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    monkeypatch.setattr(google_tasks, "_tasks_api_get", fake_api_get)

    connector = google_tasks.GoogleTasksConnector(credentials_path=str(credentials))
    with pytest.raises(httpx.HTTPStatusError):
        list(connector.sync())
    assert connector.sync_status().state == "error"


def test_refresh_google_token_posts_the_refresh_grant(monkeypatch):
    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "new", "expires_in": 3600}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return _FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    result = oauth_module.refresh_google_token("cid", "csecret", "rtoken")

    assert result["access_token"] == "new"
    assert captured["url"] == "https://oauth2.googleapis.com/token"
    assert captured["data"]["grant_type"] == "refresh_token"
    assert captured["data"]["refresh_token"] == "rtoken"
    assert captured["data"]["client_id"] == "cid"
    assert captured["data"]["client_secret"] == "csecret"


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
