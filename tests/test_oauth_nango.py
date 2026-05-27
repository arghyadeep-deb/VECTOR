"""Tests for nango-inspired OAuth improvements:
- YAML provider registry (80+ providers)
- OAuthToken.is_expired()
- refresh_expiring_tokens() (no live network)
- OAuth 1.0a guarded import
- expires_at stored as absolute ISO timestamp
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Provider Registry (YAML-backed) ──────────────────────────────────────────

class TestProviderRegistry:
    def setup_method(self):
        from core.engine.oauth.providers import PROVIDERS, get_provider, ProviderConfig
        self.PROVIDERS = PROVIDERS
        self.get_provider = get_provider
        self.ProviderConfig = ProviderConfig

    def test_provider_count_at_least_80(self):
        assert len(self.PROVIDERS) >= 80, (
            f"Expected 80+ providers, got {len(self.PROVIDERS)}"
        )

    def test_github_is_oauth2(self):
        p = self.get_provider("github")
        assert p is not None
        assert p.auth_mode == "oauth2"
        assert "github.com" in p.auth_url
        assert "github.com" in p.token_url

    def test_twitter_v1_is_oauth1(self):
        p = self.get_provider("twitter_v1")
        assert p is not None
        assert p.auth_mode == "oauth1"
        assert p.request_token_url != ""

    def test_openai_is_api_key(self):
        p = self.get_provider("openai")
        assert p is not None
        assert p.auth_mode == "api_key"
        assert p.key_env != ""

    def test_all_providers_have_name(self):
        for slug, p in self.PROVIDERS.items():
            assert p.name, f"Provider {slug} has no name"

    def test_all_providers_have_valid_auth_mode(self):
        valid = {"oauth2", "oauth1", "api_key", "basic"}
        for slug, p in self.PROVIDERS.items():
            assert p.auth_mode in valid, (
                f"Provider {slug} has invalid auth_mode: {p.auth_mode}"
            )

    def test_oauth2_providers_have_auth_url(self):
        for slug, p in self.PROVIDERS.items():
            if p.auth_mode == "oauth2":
                assert p.auth_url.startswith("https://"), (
                    f"oauth2 provider {slug} missing auth_url"
                )

    def test_oauth1_providers_have_request_token_url(self):
        for slug, p in self.PROVIDERS.items():
            if p.auth_mode == "oauth1":
                assert p.request_token_url.startswith("https://"), (
                    f"oauth1 provider {slug} missing request_token_url"
                )

    def test_api_key_providers_have_key_env(self):
        for slug, p in self.PROVIDERS.items():
            if p.auth_mode == "api_key":
                assert p.key_env, f"api_key provider {slug} missing key_env"

    def test_categories_cover_expected_domains(self):
        cats = {p.category for p in self.PROVIDERS.values()}
        for expected in ("dev_tools", "productivity", "communication", "social", "ai"):
            assert expected in cats, f"Missing category: {expected}"

    def test_unknown_slug_returns_none(self):
        assert self.get_provider("this_does_not_exist_xyz") is None

    def test_provider_config_backward_compat_alias(self):
        from core.engine.oauth.providers import OAuthProviderConfig, ProviderConfig
        assert OAuthProviderConfig is ProviderConfig

    def test_oauth1_alias(self):
        from core.engine.oauth.providers import OAuth1ProviderConfig, ProviderConfig
        assert OAuth1ProviderConfig is ProviderConfig

    def test_pkce_providers_flagged(self):
        # Airtable, Dropbox, Twitter use PKCE — at least one should be flagged
        pkce_providers = [p for p in self.PROVIDERS.values()
                          if p.auth_mode == "oauth2" and p.pkce]
        assert len(pkce_providers) >= 1

    def test_load_from_env_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("OAUTH_GITHUB_CLIENT_ID", "test_id_123")
        monkeypatch.setenv("OAUTH_GITHUB_CLIENT_SECRET", "test_secret_xyz")
        p = self.get_provider("github")
        assert p.client_id == "test_id_123"
        assert p.client_secret == "test_secret_xyz"
        assert p.is_configured()

    def test_api_key_load_from_env(self, monkeypatch):
        p = self.get_provider("openai")
        monkeypatch.setenv(p.key_env, "sk-test-abc123")
        p.load_from_env()
        assert p.client_id == "sk-test-abc123"
        assert p.is_configured()


# ── OAuthToken expiry ──────────────────────────────────────────────────────────

class TestOAuthTokenExpiry:
    def _make_token(self, expires_at: str = "") -> "OAuthToken":
        from core.engine.oauth.flows import OAuthToken
        return OAuthToken(slug="github", access_token="tok", expires_at=expires_at)

    def test_no_expiry_not_expired(self):
        token = self._make_token("")
        assert not token.is_expired()

    def test_past_timestamp_is_expired(self):
        past = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
        assert self._make_token(past).is_expired()

    def test_future_timestamp_not_expired(self):
        future = (datetime.now(tz=timezone.utc) + timedelta(hours=2)).isoformat()
        assert not self._make_token(future).is_expired()

    def test_within_buffer_is_expired(self):
        # 3 minutes from now — within default buffer of 5 minutes
        soon = (datetime.now(tz=timezone.utc) + timedelta(minutes=3)).isoformat()
        assert self._make_token(soon).is_expired(buffer_minutes=5)

    def test_outside_buffer_not_expired(self):
        # 10 minutes from now — outside buffer of 5 minutes
        later = (datetime.now(tz=timezone.utc) + timedelta(minutes=10)).isoformat()
        assert not self._make_token(later).is_expired(buffer_minutes=5)

    def test_custom_buffer(self):
        # 2 hours from now — outside 30-minute buffer but inside 3-hour buffer
        two_hours = (datetime.now(tz=timezone.utc) + timedelta(hours=2)).isoformat()
        assert not self._make_token(two_hours).is_expired(buffer_minutes=30)
        assert self._make_token(two_hours).is_expired(buffer_minutes=180)

    def test_invalid_expires_at_not_expired(self):
        assert not self._make_token("not-a-date").is_expired()

    def test_to_dict_preserves_expires_at(self):
        ts = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
        token = self._make_token(ts)
        d = token.to_dict()
        assert d["expires_at"] == ts


# ── _expires_at_from_seconds ──────────────────────────────────────────────────

class TestExpiresAtFromSeconds:
    def setup_method(self):
        from core.engine.oauth.flows import _expires_at_from_seconds
        self.fn = _expires_at_from_seconds

    def test_3600_returns_future_iso(self):
        result = self.fn(3600)
        assert result != ""
        dt = datetime.fromisoformat(result)
        assert dt > datetime.now(tz=timezone.utc)

    def test_string_seconds(self):
        result = self.fn("1800")
        assert result != ""

    def test_none_returns_empty(self):
        assert self.fn(None) == ""

    def test_empty_string_returns_empty(self):
        assert self.fn("") == ""

    def test_zero_returns_past_or_now(self):
        result = self.fn(0)
        # 0 seconds is now — just confirm it's a valid ISO string
        assert result == "" or "T" in result


# ── Token storage round-trip ──────────────────────────────────────────────────

class TestTokenStorageRoundTrip:
    def test_absolute_timestamp_survives_round_trip(self, tmp_path):
        import core.engine.oauth.flows as flows_mod
        orig_dir = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        try:
            from core.engine.oauth.flows import OAuthFlowManager, OAuthToken
            mgr = OAuthFlowManager()
            ts = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
            tok = OAuthToken(slug="github", access_token="abc", expires_at=ts)
            mgr.store_token("github", tok)
            retrieved = mgr._load_raw("github")
            assert retrieved is not None
            assert retrieved.expires_at == ts
            assert not retrieved.is_expired()
        finally:
            flows_mod._TOKEN_DIR = orig_dir

    def test_auth_mode_survives_round_trip(self, tmp_path):
        import core.engine.oauth.flows as flows_mod
        orig_dir = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        try:
            from core.engine.oauth.flows import OAuthFlowManager, OAuthToken
            mgr = OAuthFlowManager()
            tok = OAuthToken(slug="twitter_v1", access_token="oauth_tok",
                             auth_mode="oauth1",
                             extra={"oauth_token_secret": "secret_xyz"})
            mgr.store_token("twitter_v1", tok)
            retrieved = mgr._load_raw("twitter_v1")
            assert retrieved.auth_mode == "oauth1"
            assert retrieved.extra.get("oauth_token_secret") == "secret_xyz"
        finally:
            flows_mod._TOKEN_DIR = orig_dir


# ── refresh_expiring_tokens (no live network) ─────────────────────────────────

class TestRefreshExpiringTokens:
    def test_no_tokens_returns_empty(self, tmp_path):
        import core.engine.oauth.flows as flows_mod
        orig = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        try:
            from core.engine.oauth.flows import OAuthFlowManager
            mgr = OAuthFlowManager()
            result = mgr.refresh_expiring_tokens(threshold_minutes=60)
            assert result == []
        finally:
            flows_mod._TOKEN_DIR = orig

    def test_fresh_token_not_refreshed(self, tmp_path):
        import core.engine.oauth.flows as flows_mod
        orig = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        try:
            from core.engine.oauth.flows import OAuthFlowManager, OAuthToken
            mgr = OAuthFlowManager()
            future = (datetime.now(tz=timezone.utc) + timedelta(hours=5)).isoformat()
            tok = OAuthToken(slug="github", access_token="abc",
                             expires_at=future, refresh_token="ref")
            mgr.store_token("github", tok)
            result = mgr.refresh_expiring_tokens(threshold_minutes=60)
            assert result == []
        finally:
            flows_mod._TOKEN_DIR = orig

    def test_expired_no_refresh_token_skipped(self, tmp_path):
        import core.engine.oauth.flows as flows_mod
        orig = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        try:
            from core.engine.oauth.flows import OAuthFlowManager, OAuthToken
            mgr = OAuthFlowManager()
            past = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
            tok = OAuthToken(slug="github", access_token="abc",
                             expires_at=past, refresh_token="")
            mgr.store_token("github", tok)
            result = mgr.refresh_expiring_tokens(threshold_minutes=60)
            assert result == []
        finally:
            flows_mod._TOKEN_DIR = orig


# ── OAuth 1.0a guarded import ─────────────────────────────────────────────────

class TestOAuth1GuardedImport:
    """OAuth 1.0a methods must raise ImportError when requests-oauthlib is missing."""

    def test_get_request_token_raises_without_lib(self, tmp_path, monkeypatch):
        import core.engine.oauth.flows as flows_mod
        orig_dir = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        orig_avail = flows_mod._OAUTH1_AVAILABLE
        flows_mod._OAUTH1_AVAILABLE = False
        try:
            from core.engine.oauth.flows import OAuthFlowManager
            mgr = OAuthFlowManager()
            with pytest.raises(ImportError, match="requests-oauthlib"):
                mgr.get_oauth1_request_token("twitter_v1", callback_url="http://localhost/cb")
        finally:
            flows_mod._TOKEN_DIR = orig_dir
            flows_mod._OAUTH1_AVAILABLE = orig_avail

    def test_complete_oauth1_raises_without_lib(self, tmp_path, monkeypatch):
        import core.engine.oauth.flows as flows_mod
        orig_dir = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        orig_avail = flows_mod._OAUTH1_AVAILABLE
        flows_mod._OAUTH1_AVAILABLE = False
        try:
            from core.engine.oauth.flows import OAuthFlowManager
            mgr = OAuthFlowManager()
            with pytest.raises(ImportError, match="requests-oauthlib"):
                mgr.complete_oauth1("twitter_v1", "tok", "secret", "verifier")
        finally:
            flows_mod._TOKEN_DIR = orig_dir
            flows_mod._OAUTH1_AVAILABLE = orig_avail

    def test_get_oauth1_session_raises_without_lib(self, tmp_path, monkeypatch):
        import core.engine.oauth.flows as flows_mod
        orig_dir = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        orig_avail = flows_mod._OAUTH1_AVAILABLE
        flows_mod._OAUTH1_AVAILABLE = False
        try:
            from core.engine.oauth.flows import OAuthFlowManager
            mgr = OAuthFlowManager()
            with pytest.raises(ImportError, match="requests-oauthlib"):
                mgr.get_oauth1_session("twitter_v1")
        finally:
            flows_mod._TOKEN_DIR = orig_dir
            flows_mod._OAUTH1_AVAILABLE = orig_avail


# ── Refresh Scheduler ─────────────────────────────────────────────────────────

class TestRefreshScheduler:
    def test_scheduler_no_crash_without_apscheduler(self, monkeypatch):
        import core.engine.oauth.refresh_scheduler as sched_mod
        orig = sched_mod._APSCHEDULER_AVAILABLE
        sched_mod._APSCHEDULER_AVAILABLE = False
        try:
            from core.engine.oauth.refresh_scheduler import OAuthRefreshScheduler
            sched = OAuthRefreshScheduler()
            sched.start()   # should log warning, not raise
            sched.stop()    # no-op
        finally:
            sched_mod._APSCHEDULER_AVAILABLE = orig

    def test_run_now_no_crash(self, tmp_path):
        import core.engine.oauth.flows as flows_mod
        orig = flows_mod._TOKEN_DIR
        flows_mod._TOKEN_DIR = tmp_path
        try:
            from core.engine.oauth.refresh_scheduler import OAuthRefreshScheduler
            sched = OAuthRefreshScheduler()
            sched.run_now()  # no tokens stored → just logs debug
        finally:
            flows_mod._TOKEN_DIR = orig


# ── Server: provider count exposed via /oauth/providers ───────────────────────

def test_server_providers_endpoint_count():
    """Smoke: FastAPI test client hits /oauth/providers and asserts 80+ listed."""
    try:
        from fastapi.testclient import TestClient
        from core.engine.oauth.server import create_app
        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/oauth/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 80, f"Expected 80+ providers, got {data['total']}"
    except ImportError:
        pytest.skip("fastapi/httpx not installed")
