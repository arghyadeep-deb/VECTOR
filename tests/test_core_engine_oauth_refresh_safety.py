"""Regression tests for OAuth refresh fail-closed behavior.

Expired credentials used to remain callable when refresh failed, and non-2xx
or malformed refresh responses were recorded as successful by reusing the old
access token.  Downstream callers must never receive that stale credential as
though it were valid.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from core.engine.oauth import flows
from core.engine.oauth.flows import OAuthFlowManager, OAuthToken
from core.engine.oauth.server import _error_html, _success_html


def _expired_token() -> OAuthToken:
    return OAuthToken(
        slug="github",
        access_token="stale-access-token",
        refresh_token="refresh-token",
        expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )


def test_expired_token_is_not_returned_when_refresh_fails(monkeypatch, tmp_path):
    """A provider failure must not turn an expired token into a usable result."""
    monkeypatch.setattr(flows, "_TOKEN_DIR", tmp_path)
    monkeypatch.setattr(flows, "_KEYRING_AVAILABLE", False)
    manager = OAuthFlowManager()
    manager.store_token("github", _expired_token())
    monkeypatch.setattr(manager, "_sync_refresh", lambda slug, token: None)

    assert manager.get_token("github") is None


def test_non_2xx_refresh_response_does_not_overwrite_stored_token(monkeypatch, tmp_path):
    """HTTP errors must be rejected before their JSON can masquerade as a refresh."""
    monkeypatch.setattr(flows, "_TOKEN_DIR", tmp_path)
    monkeypatch.setattr(flows, "_KEYRING_AVAILABLE", False)
    manager = OAuthFlowManager()
    original = _expired_token()
    manager.store_token("github", original)

    response = httpx.Response(
        401,
        json={"error": "invalid_grant"},
        request=httpx.Request("POST", "https://github.com/login/oauth/access_token"),
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)

    assert manager._sync_refresh("github", original) is None
    assert manager._load_raw("github").access_token == original.access_token


def test_refresh_requires_a_new_access_token(monkeypatch, tmp_path):
    """A 200 response without access_token must not renew stale credentials."""
    monkeypatch.setattr(flows, "_TOKEN_DIR", tmp_path)
    monkeypatch.setattr(flows, "_KEYRING_AVAILABLE", False)
    manager = OAuthFlowManager()
    original = _expired_token()
    manager.store_token("github", original)

    response = httpx.Response(
        200,
        json={"expires_in": 3600},
        request=httpx.Request("POST", "https://github.com/login/oauth/access_token"),
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)

    assert manager._sync_refresh("github", original) is None
    assert manager.get_token("github") is None


@pytest.mark.parametrize("operation", ["store", "load", "revoke"])
def test_provider_slug_cannot_escape_token_directory(monkeypatch, tmp_path, operation):
    """Windows path separators in a route slug must not reach filesystem I/O."""
    monkeypatch.setattr(flows, "_TOKEN_DIR", tmp_path / "oauth_tokens")
    monkeypatch.setattr(flows, "_KEYRING_AVAILABLE", False)
    flows._TOKEN_DIR.mkdir()
    manager = OAuthFlowManager()
    malicious_slug = r"..\escaped"

    with pytest.raises(ValueError, match="invalid OAuth provider slug"):
        if operation == "store":
            manager.store_api_key(malicious_slug, "attacker-controlled")
        elif operation == "load":
            manager.get_token(malicious_slug)
        else:
            manager.revoke_token(malicious_slug)

    assert not (tmp_path / "escaped.json").exists()


@pytest.mark.parametrize("renderer", [_error_html, _success_html])
def test_oauth_html_escapes_provider_controlled_text(renderer):
    """OAuth callback text must not execute script in the localhost server origin."""
    rendered = renderer('<script>fetch("/oauth/revoke/github", {method:"POST"})</script>')

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


if __name__ == "__main__":
    raise SystemExit("Run with: pytest tests/test_core_engine_oauth_refresh_safety.py -v")
