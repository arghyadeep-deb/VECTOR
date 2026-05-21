"""
VECTOR OAuth Provider Configs — OAuth2 credentials and endpoint definitions.

Covers 20 major providers with full authorization + token URLs.
Credentials stored in core/config.py CONFIG dict (never hardcoded).
Add your OAuth app credentials to .env:

  OAUTH_GITHUB_CLIENT_ID=...
  OAUTH_GITHUB_CLIENT_SECRET=...
  OAUTH_GOOGLE_CLIENT_ID=...
  etc.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class OAuthProviderConfig:
    slug: str
    name: str
    auth_url: str
    token_url: str
    scopes: list[str]
    client_id: str = ""
    client_secret: str = ""
    extra_params: dict = field(default_factory=dict)
    pkce: bool = False          # True = use PKCE (no client_secret needed)
    user_info_url: str = ""

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret) or self.pkce

    def load_from_env(self) -> "OAuthProviderConfig":
        slug_upper = self.slug.upper()
        self.client_id = os.getenv(f"OAUTH_{slug_upper}_CLIENT_ID", self.client_id)
        self.client_secret = os.getenv(f"OAUTH_{slug_upper}_CLIENT_SECRET", self.client_secret)
        return self


# ── Provider definitions ───────────────────────────────────────────────────────

PROVIDERS: dict[str, OAuthProviderConfig] = {p.slug: p for p in [

    OAuthProviderConfig(
        slug="github",
        name="GitHub",
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        scopes=["repo", "read:user", "user:email", "notifications"],
        user_info_url="https://api.github.com/user",
    ),

    OAuthProviderConfig(
        slug="google",
        name="Google (Gmail + Calendar + Drive)",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=[
            "openid", "email", "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
        extra_params={"access_type": "offline", "prompt": "consent"},
        user_info_url="https://www.googleapis.com/oauth2/v2/userinfo",
    ),

    OAuthProviderConfig(
        slug="slack",
        name="Slack",
        auth_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        scopes=["channels:read", "chat:write", "users:read", "im:read", "im:write"],
        user_info_url="https://slack.com/api/auth.test",
    ),

    OAuthProviderConfig(
        slug="discord",
        name="Discord",
        auth_url="https://discord.com/api/oauth2/authorize",
        token_url="https://discord.com/api/oauth2/token",
        scopes=["identify", "email", "guilds", "messages.read"],
        user_info_url="https://discord.com/api/users/@me",
    ),

    OAuthProviderConfig(
        slug="notion",
        name="Notion",
        auth_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        scopes=[],  # Notion doesn't use scopes, uses internal integration
        extra_params={"response_type": "code", "owner": "user"},
    ),

    OAuthProviderConfig(
        slug="linear",
        name="Linear",
        auth_url="https://linear.app/oauth/authorize",
        token_url="https://api.linear.app/oauth/token",
        scopes=["read", "write", "issues:create"],
    ),

    OAuthProviderConfig(
        slug="twitter",
        name="Twitter / X",
        auth_url="https://twitter.com/i/oauth2/authorize",
        token_url="https://api.twitter.com/2/oauth2/token",
        scopes=["tweet.read", "tweet.write", "users.read", "offline.access"],
        pkce=True,
    ),

    OAuthProviderConfig(
        slug="linkedin",
        name="LinkedIn",
        auth_url="https://www.linkedin.com/oauth/v2/authorization",
        token_url="https://www.linkedin.com/oauth/v2/accessToken",
        scopes=["r_liteprofile", "r_emailaddress", "w_member_social"],
        user_info_url="https://api.linkedin.com/v2/me",
    ),

    OAuthProviderConfig(
        slug="spotify",
        name="Spotify",
        auth_url="https://accounts.spotify.com/authorize",
        token_url="https://accounts.spotify.com/api/token",
        scopes=["user-read-playback-state", "user-read-currently-playing",
                "playlist-read-private", "user-library-read"],
    ),

    OAuthProviderConfig(
        slug="jira",
        name="Jira (Atlassian)",
        auth_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        scopes=["read:jira-work", "write:jira-work", "offline_access"],
        extra_params={"audience": "api.atlassian.com", "prompt": "consent"},
    ),

    OAuthProviderConfig(
        slug="confluence",
        name="Confluence (Atlassian)",
        auth_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        scopes=["read:confluence-content.all", "write:confluence-content", "offline_access"],
        extra_params={"audience": "api.atlassian.com", "prompt": "consent"},
    ),

    OAuthProviderConfig(
        slug="asana",
        name="Asana",
        auth_url="https://app.asana.com/-/oauth_authorize",
        token_url="https://app.asana.com/-/oauth_token",
        scopes=[],
    ),

    OAuthProviderConfig(
        slug="trello",
        name="Trello",
        auth_url="https://trello.com/1/authorize",
        token_url="https://trello.com/1/OAuthGetAccessToken",
        scopes=["read", "write"],
        extra_params={"expiration": "never", "name": "VECTOR"},
    ),

    OAuthProviderConfig(
        slug="dropbox",
        name="Dropbox",
        auth_url="https://www.dropbox.com/oauth2/authorize",
        token_url="https://api.dropboxapi.com/oauth2/token",
        scopes=[],
        pkce=True,
        extra_params={"token_access_type": "offline"},
    ),

    OAuthProviderConfig(
        slug="stripe",
        name="Stripe",
        auth_url="https://connect.stripe.com/oauth/authorize",
        token_url="https://connect.stripe.com/oauth/token",
        scopes=["read_only"],
    ),

    OAuthProviderConfig(
        slug="microsoft",
        name="Microsoft (Outlook + OneDrive + Teams)",
        auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scopes=[
            "User.Read", "Mail.Read", "Mail.Send",
            "Calendars.Read", "Files.Read.All", "offline_access",
        ],
        user_info_url="https://graph.microsoft.com/v1.0/me",
    ),

    OAuthProviderConfig(
        slug="zoom",
        name="Zoom",
        auth_url="https://zoom.us/oauth/authorize",
        token_url="https://zoom.us/oauth/token",
        scopes=["meeting:read", "meeting:write", "recording:read", "user:read"],
    ),

    OAuthProviderConfig(
        slug="airtable",
        name="Airtable",
        auth_url="https://airtable.com/oauth2/v1/authorize",
        token_url="https://airtable.com/oauth2/v1/token",
        scopes=["data.records:read", "data.records:write", "schema.bases:read"],
        pkce=True,
    ),

    OAuthProviderConfig(
        slug="reddit",
        name="Reddit",
        auth_url="https://www.reddit.com/api/v1/authorize",
        token_url="https://www.reddit.com/api/v1/access_token",
        scopes=["read", "submit", "identity", "privatemessages"],
        extra_params={"duration": "permanent"},
    ),

    OAuthProviderConfig(
        slug="hubspot",
        name="HubSpot",
        auth_url="https://app.hubspot.com/oauth/authorize",
        token_url="https://api.hubapi.com/oauth/v1/token",
        scopes=["crm.objects.contacts.read", "crm.objects.deals.read", "content"],
    ),
]}


def get_provider(slug: str) -> OAuthProviderConfig | None:
    cfg = PROVIDERS.get(slug)
    if cfg:
        cfg.load_from_env()
    return cfg


def configured_providers() -> list[OAuthProviderConfig]:
    result = []
    for cfg in PROVIDERS.values():
        cfg.load_from_env()
        if cfg.is_configured():
            result.append(cfg)
    return result


if __name__ == "__main__":
    assert len(PROVIDERS) == 20
    gh = get_provider("github")
    assert gh is not None and "github.com" in gh.auth_url
    print(f"OK oauth/providers.py — {len(PROVIDERS)} providers defined")
