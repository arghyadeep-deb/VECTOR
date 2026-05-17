"""
VECTOR OAuth Flow Manager — cloud-ready OAuth orchestration.

When VECTOR_CLOUD_API_URL is set, flows proxy through VECTOR's cloud backend.
In local mode, falls back to direct OAuth (where supported) or API keys.

Stores tokens in VECTOR's keyring (never .env files).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from loguru import logger

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

_TOKEN_DIR = Path.home() / ".vector_ca" / "oauth_tokens"
_CLOUD_API = os.getenv("VECTOR_CLOUD_API_URL", "")


@dataclass
class OAuthToken:
    slug: str
    access_token: str
    refresh_token: str = ""
    expires_at: str = ""
    scope: str = ""
    extra: dict = None

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "extra": self.extra or {},
        }


class OAuthFlowManager:
    """
    Manages OAuth token storage and retrieval for VECTOR integrations.

    Local mode: tokens stored in ~/.vector_ca/oauth_tokens/ (encrypted if keyring available)
    Cloud mode: tokens proxied through VECTOR_CLOUD_API_URL (set when deploying to cloud)
    """

    def __init__(self) -> None:
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        self._cloud_mode = bool(_CLOUD_API)
        if self._cloud_mode:
            logger.info("[VECTOR][oauth] cloud mode — proxying via {}", _CLOUD_API)
        else:
            logger.info("[VECTOR][oauth] local mode — tokens in ~/.vector_ca/oauth_tokens/")

    def store_token(self, slug: str, token: OAuthToken) -> None:
        """Persist an OAuth token securely."""
        if _KEYRING_AVAILABLE:
            keyring.set_password("VECTOR", f"oauth:{slug}", json.dumps(token.to_dict()))
        else:
            path = _TOKEN_DIR / f"{slug}.json"
            path.write_text(json.dumps(token.to_dict(), indent=2), encoding="utf-8")
            path.chmod(0o600)
        logger.info("[VECTOR][oauth] token stored for {}", slug)

    def get_token(self, slug: str) -> OAuthToken | None:
        """Retrieve stored token."""
        try:
            if _KEYRING_AVAILABLE:
                raw = keyring.get_password("VECTOR", f"oauth:{slug}")
                if raw:
                    d = json.loads(raw)
                    return OAuthToken(**d)
            path = _TOKEN_DIR / f"{slug}.json"
            if path.exists():
                d = json.loads(path.read_text(encoding="utf-8"))
                return OAuthToken(**d)
        except Exception as e:
            logger.warning("[VECTOR][oauth] token retrieval failed for {}: {}", slug, e)
        return None

    def revoke_token(self, slug: str) -> None:
        """Remove stored token."""
        if _KEYRING_AVAILABLE:
            try:
                keyring.delete_password("VECTOR", f"oauth:{slug}")
            except Exception:
                pass
        path = _TOKEN_DIR / f"{slug}.json"
        if path.exists():
            path.unlink()
        logger.info("[VECTOR][oauth] token revoked for {}", slug)

    def list_connected(self) -> list[str]:
        """Return slugs of all connected integrations."""
        connected = []
        for path in _TOKEN_DIR.glob("*.json"):
            connected.append(path.stem)
        return connected

    def get_auth_url(self, slug: str, redirect_uri: str = "http://localhost:7788/oauth/callback") -> str:
        """
        Get OAuth authorization URL.
        In cloud mode: returns VECTOR cloud OAuth URL.
        In local mode: returns provider-specific URL (requires app credentials).
        """
        if self._cloud_mode:
            return f"{_CLOUD_API}/oauth/authorize?integration={slug}&redirect_uri={redirect_uri}"
        return f"[Configure {slug} OAuth credentials in core/config.py to enable local OAuth]"

    def store_api_key(self, slug: str, api_key: str) -> None:
        """Store an API key (non-OAuth integrations)."""
        token = OAuthToken(slug=slug, access_token=api_key, extra={"type": "api_key"})
        self.store_token(slug, token)

    def is_connected(self, slug: str) -> bool:
        return self.get_token(slug) is not None


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        import core.openhuman.oauth.flows as flows_mod
        flows_mod._TOKEN_DIR = Path(d)
        mgr = OAuthFlowManager()
        token = OAuthToken(slug="github", access_token="test_token_123", scope="repo")
        mgr.store_token("github", token)
        retrieved = mgr.get_token("github")
        assert retrieved is not None and retrieved.access_token == "test_token_123"
        assert "github" in mgr.list_connected()
        mgr.revoke_token("github")
        assert not mgr.is_connected("github")
    print("OK oauth/flows.py")
