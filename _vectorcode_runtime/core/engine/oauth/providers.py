"""
VECTOR OAuth Provider Registry — loads 80+ providers from providers.yaml.

Auth modes: oauth2 | oauth1 | api_key | basic
Credentials stored in core/config.py CONFIG dict (never hardcoded).
Add credentials to .env:

  OAUTH_GITHUB_CLIENT_ID=...
  OAUTH_GITHUB_CLIENT_SECRET=...
  OAUTH_OPENAI_API_KEY=...      # for api_key providers
"""
from __future__ import annotations

__all__ = [
    "ProviderConfig",
    "OAuthProviderConfig",    # backward-compat alias
    "OAuth1ProviderConfig",   # backward-compat alias
    "PROVIDERS",
    "configured_providers",
    "get_provider",
]

import os
from dataclasses import dataclass, field
from pathlib import Path


try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_YAML_PATH = Path(__file__).parent / "providers.yaml"


@dataclass
class ProviderConfig:
    slug: str
    name: str
    category: str = "other"
    auth_mode: str = "oauth2"          # oauth2 | oauth1 | api_key | basic

    # OAuth2 fields
    auth_url: str = ""
    token_url: str = ""
    scopes: list[str] = field(default_factory=list)
    user_info_url: str = ""
    extra_params: dict = field(default_factory=dict)
    pkce: bool = False

    # OAuth1 fields
    request_token_url: str = ""
    access_token_url: str = ""

    # API key / basic fields
    api_base: str = ""
    key_env: str = ""

    # Runtime credentials (populated by load_from_env)
    client_id: str = ""
    client_secret: str = ""

    def load_from_env(self) -> "ProviderConfig":
        slug_upper = self.slug.upper()
        if self.auth_mode in ("oauth2", "oauth1", "basic"):
            self.client_id = os.getenv(f"OAUTH_{slug_upper}_CLIENT_ID", self.client_id)
            self.client_secret = os.getenv(f"OAUTH_{slug_upper}_CLIENT_SECRET", self.client_secret)
        elif self.auth_mode == "api_key" and self.key_env:
            self.client_id = os.getenv(self.key_env, self.client_id)
        return self

    def is_configured(self) -> bool:
        if self.auth_mode == "api_key":
            return bool(self.client_id)
        if self.auth_mode == "basic":
            return bool(self.client_id and self.client_secret)
        # oauth2 / oauth1
        return bool(self.client_id and self.client_secret) or self.pkce

    @property
    def is_oauth1(self) -> bool:
        return self.auth_mode == "oauth1"

    @property
    def is_api_key(self) -> bool:
        return self.auth_mode == "api_key"


# Backward-compat type aliases
OAuthProviderConfig = ProviderConfig
OAuth1ProviderConfig = ProviderConfig


def _load_providers_from_yaml() -> dict[str, ProviderConfig]:
    if not _YAML_AVAILABLE:
        raise ImportError("PyYAML required: pip install pyyaml")
    if not _YAML_PATH.exists():
        raise FileNotFoundError(f"providers.yaml not found at {_YAML_PATH}")

    with open(_YAML_PATH, encoding="utf-8") as fh:
        raw: dict = _yaml.safe_load(fh)

    providers: dict[str, ProviderConfig] = {}
    for slug, data in raw.items():
        if not isinstance(data, dict):
            continue
        scopes_raw = data.get("scopes", [])
        scopes = list(scopes_raw) if scopes_raw else []

        providers[slug] = ProviderConfig(
            slug=slug,
            name=data.get("name", slug),
            category=data.get("category", "other"),
            auth_mode=data.get("auth_mode", "oauth2"),
            auth_url=data.get("auth_url", ""),
            token_url=data.get("token_url", ""),
            scopes=scopes,
            user_info_url=data.get("user_info_url", ""),
            extra_params=data.get("extra_params") or {},
            pkce=bool(data.get("pkce", False)),
            request_token_url=data.get("request_token_url", ""),
            access_token_url=data.get("access_token_url", data.get("token_url", "")),
            api_base=data.get("api_base", ""),
            key_env=data.get("key_env", ""),
        )
    return providers


def _load_providers_fallback() -> dict[str, ProviderConfig]:
    """Minimal hardcoded fallback when PyYAML is unavailable."""
    return {p.slug: p for p in [
        ProviderConfig(
            slug="github", name="GitHub", category="dev_tools",
            auth_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            scopes=["repo", "read:user", "user:email"],
            user_info_url="https://api.github.com/user",
        ),
        ProviderConfig(
            slug="google", name="Google", category="social",
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["openid", "email", "profile"],
            extra_params={"access_type": "offline", "prompt": "consent"},
            user_info_url="https://www.googleapis.com/oauth2/v2/userinfo",
        ),
    ]}


try:
    PROVIDERS: dict[str, ProviderConfig] = _load_providers_from_yaml()
except Exception:
    PROVIDERS = _load_providers_fallback()


def get_provider(slug: str) -> ProviderConfig | None:
    cfg = PROVIDERS.get(slug)
    if cfg:
        cfg.load_from_env()
    return cfg


def configured_providers() -> list[ProviderConfig]:
    result = []
    for cfg in PROVIDERS.values():
        cfg.load_from_env()
        if cfg.is_configured():
            result.append(cfg)
    return result


if __name__ == "__main__":
    assert len(PROVIDERS) >= 80, f"Expected 80+ providers, got {len(PROVIDERS)}"
    gh = get_provider("github")
    assert gh is not None and "github.com" in gh.auth_url
    tw1 = get_provider("twitter_v1")
    assert tw1 is not None and tw1.auth_mode == "oauth1"
    oai = get_provider("openai")
    assert oai is not None and oai.auth_mode == "api_key"
    cats = {p.category for p in PROVIDERS.values()}
    assert "dev_tools" in cats and "ai" in cats
    print(f"OK oauth/providers.py — {len(PROVIDERS)} providers loaded from YAML")
