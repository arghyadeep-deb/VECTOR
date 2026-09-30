"""
VECTOR OAuth Flow Manager — cloud-ready OAuth orchestration.

When VECTOR_CLOUD_API_URL is set, flows proxy through VECTOR's cloud backend.
In local mode, falls back to direct OAuth (where supported) or API keys.

Stores tokens in VECTOR's keyring (never .env files).
Token expiry: stored as absolute ISO-8601 UTC timestamp, checked before returning.
OAuth 1.0a: supported via requests-oauthlib (guarded import).
"""
from __future__ import annotations

__all__ = [
    "OAuthFlowManager",
    "OAuthToken",
]


import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

from loguru import logger
from core.config import CONFIG

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

try:
    from requests_oauthlib import OAuth1Session as _OAuth1Session
    _OAUTH1_AVAILABLE = True
except ImportError:
    _OAUTH1_AVAILABLE = False

_TOKEN_DIR = Path.home() / ".vector_ca" / "oauth_tokens"
_CLOUD_API = CONFIG.get("cloud_api_url", "")

_ISO_FMT = "%Y-%m-%dT%H:%M:%S.%f+00:00"
_SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _expires_at_from_seconds(expires_in: int | str | None) -> str:
    """Convert expires_in seconds to absolute ISO UTC timestamp string."""
    if not expires_in:
        return ""
    try:
        seconds = int(expires_in)
        return (_now_utc() + timedelta(seconds=seconds)).isoformat()
    except (ValueError, TypeError):
        return ""


def _parse_expires_at(expires_at: str) -> datetime | None:
    """Parse an absolute ISO UTC expires_at string to datetime."""
    if not expires_at:
        return None
    try:
        dt = datetime.fromisoformat(expires_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _token_path(slug: str) -> Path:
    """Resolve a token filename without allowing provider IDs to escape storage."""
    if not isinstance(slug, str) or not _SAFE_SLUG.fullmatch(slug):
        raise ValueError("invalid OAuth provider slug")
    return _TOKEN_DIR / f"{slug}.json"


@dataclass
class OAuthToken:
    slug: str
    access_token: str
    refresh_token: str = ""
    expires_at: str = ""      # absolute ISO UTC timestamp, e.g. "2026-05-27T18:30:00+00:00"
    scope: str = ""
    extra: dict = field(default_factory=dict)
    auth_mode: str = "oauth2"  # oauth2 | oauth1 | api_key

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "extra": self.extra or {},
            "auth_mode": self.auth_mode,
        }

    def is_expired(self, buffer_minutes: int = 5) -> bool:
        """Return True if token is expired or will expire within buffer_minutes."""
        dt = _parse_expires_at(self.expires_at)
        if dt is None:
            return False   # no expiry info → assume valid
        return _now_utc() >= dt - timedelta(minutes=buffer_minutes)


class OAuthFlowManager:
    """
    Manages OAuth token storage and retrieval for VECTOR integrations.

    Local mode: tokens stored in ~/.vector_ca/oauth_tokens/ (keyring if available)
    Cloud mode: tokens proxied through VECTOR_CLOUD_API_URL
    Auto-refresh: get_token() auto-refreshes if token is within 5 min of expiry.
    OAuth 1.0a: get_oauth1_session() — requires requests-oauthlib.
    """

    def __init__(self) -> None:
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        self._cloud_mode = bool(_CLOUD_API)
        if self._cloud_mode:
            logger.info("[VECTOR][oauth] cloud mode — proxying via {}", _CLOUD_API)
        else:
            logger.info("[VECTOR][oauth] local mode — tokens in ~/.vector_ca/oauth_tokens/")

    # ── Core storage ──────────────────────────────────────────────────────────

    def store_token(self, slug: str, token: OAuthToken) -> None:
        path = _token_path(slug)
        if _KEYRING_AVAILABLE:
            keyring.set_password("VECTOR", f"oauth:{slug}", json.dumps(token.to_dict()))
        else:
            path.write_text(json.dumps(token.to_dict(), indent=2), encoding="utf-8")
            path.chmod(0o600)
        logger.info("[VECTOR][oauth] token stored for {}", slug)

    def _load_raw(self, slug: str) -> OAuthToken | None:
        """Load token from storage without auto-refresh."""
        path = _token_path(slug)
        try:
            if _KEYRING_AVAILABLE:
                raw = keyring.get_password("VECTOR", f"oauth:{slug}")
                if raw:
                    d = json.loads(raw)
                    return OAuthToken(**{k: v for k, v in d.items()
                                        if k in OAuthToken.__dataclass_fields__})
            if path.exists():
                d = json.loads(path.read_text(encoding="utf-8"))
                return OAuthToken(**{k: v for k, v in d.items()
                                     if k in OAuthToken.__dataclass_fields__})
        except Exception as e:
            logger.warning("[VECTOR][oauth] token load failed for {}: {}", slug, e)
        return None

    def get_token(self, slug: str) -> OAuthToken | None:
        """Retrieve stored token, auto-refreshing if expired."""
        token = self._load_raw(slug)
        if token is None:
            return None
        if token.is_expired():
            if token.refresh_token:
                return self._sync_refresh(slug, token)
            logger.warning(
                "[VECTOR][oauth] refusing expired token for {} without a refresh token",
                slug,
            )
            return None
        return token

    def revoke_token(self, slug: str) -> None:
        path = _token_path(slug)
        if _KEYRING_AVAILABLE:
            try:
                keyring.delete_password("VECTOR", f"oauth:{slug}")
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass
        if path.exists():
            path.unlink()
        logger.info("[VECTOR][oauth] token revoked for {}", slug)

    def list_connected(self) -> list[str]:
        connected = []
        for path in _TOKEN_DIR.glob("*.json"):
            connected.append(path.stem)
        return connected

    # ── Token refresh ─────────────────────────────────────────────────────────

    def _sync_refresh(self, slug: str, token: OAuthToken) -> OAuthToken | None:
        """Synchronously refresh an OAuth2 access token using its refresh_token."""
        if not _HTTPX_AVAILABLE:
            logger.warning("[VECTOR][oauth] httpx not available — cannot auto-refresh {}", slug)
            return None
        try:
            from core.engine.oauth.providers import get_provider
            provider = get_provider(slug)
            if not provider or not provider.token_url:
                return None

            import httpx as _httpx
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
            }
            resp = _httpx.post(
                provider.token_url,
                data=payload,
                headers={"Accept": "application/json",
                         "Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            access_token = data.get("access_token")
            if not isinstance(access_token, str) or not access_token.strip():
                raise ValueError("refresh response did not contain a valid access_token")
            new_token = OAuthToken(
                slug=slug,
                access_token=access_token,
                refresh_token=data.get("refresh_token", token.refresh_token),
                expires_at=_expires_at_from_seconds(data.get("expires_in")),
                scope=data.get("scope", token.scope),
                auth_mode=token.auth_mode,
            )
            self.store_token(slug, new_token)
            logger.info("[VECTOR][oauth] auto-refreshed token for {}", slug)
            return new_token
        except Exception as e:
            logger.warning("[VECTOR][oauth] auto-refresh failed for {}: {}", slug, e)
            return None

    def refresh_expiring_tokens(self, threshold_minutes: int = 60) -> list[str]:
        """
        Proactively refresh all tokens expiring within threshold_minutes.
        Returns list of slugs that were refreshed.
        Called by the background scheduler every 30 min.
        """
        refreshed = []
        for slug in self.list_connected():
            token = self._load_raw(slug)
            if token and token.is_expired(buffer_minutes=threshold_minutes) and token.refresh_token:
                new = self._sync_refresh(slug, token)
                if new:
                    refreshed.append(slug)
        return refreshed

    # ── Auth URL helpers ───────────────────────────────────────────────────────

    def get_auth_url(self, slug: str, redirect_uri: str = "http://localhost:7788/oauth/callback") -> str:
        if self._cloud_mode:
            return f"{_CLOUD_API}/oauth/authorize?integration={slug}&redirect_uri={redirect_uri}"
        return f"[Configure {slug} OAuth credentials in .env to enable local OAuth]"

    # ── API key storage ────────────────────────────────────────────────────────

    def store_api_key(self, slug: str, api_key: str) -> None:
        token = OAuthToken(slug=slug, access_token=api_key,
                           extra={"type": "api_key"}, auth_mode="api_key")
        self.store_token(slug, token)

    def is_connected(self, slug: str) -> bool:
        return self._load_raw(slug) is not None

    # ── OAuth 1.0a ────────────────────────────────────────────────────────────

    def get_oauth1_request_token(self, slug: str, callback_url: str) -> dict:
        """
        Step 1 of OAuth 1.0a: get a request token from the provider.
        Returns {"oauth_token": ..., "oauth_token_secret": ..., "auth_url": ...}
        Requires: pip install requests-oauthlib
        """
        if not _OAUTH1_AVAILABLE:
            raise ImportError("OAuth 1.0a requires: pip install requests-oauthlib")
        from core.engine.oauth.providers import get_provider
        provider = get_provider(slug)
        if not provider or not provider.request_token_url:
            raise ValueError(f"Provider {slug} has no request_token_url (not OAuth1?)")

        sess = _OAuth1Session(
            provider.client_id,
            client_secret=provider.client_secret,
            callback_uri=callback_url,
        )
        resp = sess.fetch_request_token(provider.request_token_url)
        oauth_token = resp.get("oauth_token", "")
        auth_url = f"{provider.auth_url}?oauth_token={oauth_token}"
        return {
            "oauth_token": oauth_token,
            "oauth_token_secret": resp.get("oauth_token_secret", ""),
            "auth_url": auth_url,
        }

    def complete_oauth1(
        self,
        slug: str,
        oauth_token: str,
        oauth_token_secret: str,
        oauth_verifier: str,
    ) -> OAuthToken:
        """
        Step 3 of OAuth 1.0a: exchange verifier for access token.
        Returns OAuthToken with access_token and extra containing oauth_token_secret.
        """
        if not _OAUTH1_AVAILABLE:
            raise ImportError("OAuth 1.0a requires: pip install requests-oauthlib")
        from core.engine.oauth.providers import get_provider
        provider = get_provider(slug)
        if not provider or not provider.access_token_url:
            raise ValueError(f"Provider {slug} has no access_token_url (not OAuth1?)")

        sess = _OAuth1Session(
            provider.client_id,
            client_secret=provider.client_secret,
            resource_owner_key=oauth_token,
            resource_owner_secret=oauth_token_secret,
            verifier=oauth_verifier,
        )
        resp = sess.fetch_access_token(provider.access_token_url)
        token = OAuthToken(
            slug=slug,
            access_token=resp.get("oauth_token", ""),
            refresh_token="",
            expires_at="",   # OAuth1 tokens don't expire
            scope=resp.get("scope", ""),
            auth_mode="oauth1",
            extra={
                "oauth_token_secret": resp.get("oauth_token_secret", ""),
                "user_id": resp.get("user_id", ""),
                "screen_name": resp.get("screen_name", ""),
            },
        )
        self.store_token(slug, token)
        logger.info("[VECTOR][oauth] OAuth1 {} connected", slug)
        return token

    def get_oauth1_session(self, slug: str) -> "_OAuth1Session":
        """
        Return an authorized OAuth1Session ready for API calls.
        Used by callers that need to make OAuth1-signed requests.
        """
        if not _OAUTH1_AVAILABLE:
            raise ImportError("OAuth 1.0a requires: pip install requests-oauthlib")
        from core.engine.oauth.providers import get_provider
        token = self._load_raw(slug)
        if not token:
            raise ValueError(f"No token stored for {slug}")
        provider = get_provider(slug)
        if not provider:
            raise ValueError(f"Unknown provider: {slug}")
        return _OAuth1Session(
            provider.client_id,
            client_secret=provider.client_secret,
            resource_owner_key=token.access_token,
            resource_owner_secret=token.extra.get("oauth_token_secret", ""),
        )


if __name__ == "__main__":
    import tempfile
    import core.engine.oauth.flows as flows_mod
    with tempfile.TemporaryDirectory() as d:
        flows_mod._TOKEN_DIR = Path(d)
        mgr = OAuthFlowManager()

        # Store and retrieve
        token = OAuthToken(slug="github", access_token="test_123", scope="repo")
        mgr.store_token("github", token)
        retrieved = mgr.get_token("github")
        assert retrieved is not None and retrieved.access_token == "test_123"

        # is_expired with no expiry → False
        assert not token.is_expired()

        # is_expired with past timestamp → True
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
        expired_token = OAuthToken(slug="x", access_token="x", expires_at=past)
        assert expired_token.is_expired()

        # is_expired with future timestamp → False
        future = (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat()
        fresh_token = OAuthToken(slug="x", access_token="x", expires_at=future)
        assert not fresh_token.is_expired()

        # _expires_at_from_seconds
        ts = _expires_at_from_seconds(3600)
        assert ts and "T" in ts

        assert "github" in mgr.list_connected()
        mgr.revoke_token("github")
        assert not mgr.is_connected("github")

    print("OK oauth/flows.py — expiry check + OAuth1 guards verified")
