# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Strava connector — recent activities via REST API v3.

Uses OAuth2 tokens stored locally. Refresh handled automatically.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import httpx

from vectorcode.src.connectors._abc import BaseConnector, Document, SyncStatus
from vectorcode.src.vc_core.config import DEFAULT_CONFIG_DIR
from vectorcode.src.vc_core.registry import ConnectorRegistry

_STRAVA_API_BASE = "https://www.strava.com/api/v3"
_STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
_DEFAULT_TOKEN_PATH = str(DEFAULT_CONFIG_DIR / "connectors" / "strava.json")

def _strava_api_get(
    token: str, endpoint: str, params: Optional[Dict[str, Any]] = None
) -> Any:
    """Call a Strava API v3 endpoint."""
    resp = httpx.get(
        f"{_STRAVA_API_BASE}/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()

def _strava_refresh_token(
    client_id: str, client_secret: str, refresh_token: str
) -> Dict[str, Any]:
    """Refresh an expired Strava OAuth2 token."""
    resp = httpx.post(
        _STRAVA_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()

@ConnectorRegistry.register("strava")
class StravaConnector(BaseConnector):
    """Sync recent activities from Strava."""

    connector_id = "strava"
    display_name = "Strava"
    auth_type = "oauth"

    def __init__(self, *, token_path: str = _DEFAULT_TOKEN_PATH) -> None:
        self._token_path = Path(token_path)
        self._status = SyncStatus()

    def _load_tokens(self) -> Dict[str, str]:
        return json.loads(self._token_path.read_text(encoding="utf-8"))

    def _save_tokens(self, tokens: Dict[str, str]) -> None:
        self._token_path.write_text(json.dumps(tokens), encoding="utf-8")

    def _get_access_token(self) -> str:
        """Return a valid access token, refreshing it first if it has expired.

        Strava access tokens are short-lived (~6h). ``_strava_refresh_token``
        existed in this module but was never actually called anywhere --
        the module docstring's "Refresh handled automatically" claim was
        false, so every sync() after the token expired failed with a 401
        until the user manually re-authenticated. Wired here: refresh
        proactively (with a 60s safety margin) using the client_id/secret
        persisted at handle_callback() time, and persist the new tokens
        (including the next expires_at) so later calls see it too.
        """
        tokens = self._load_tokens()
        expires_at = tokens.get("expires_at")
        if (
            expires_at is not None
            and float(expires_at) > time.time() + 60
        ):
            return tokens["access_token"]

        client_id = tokens.get("client_id")
        client_secret = tokens.get("client_secret")
        refresh_token = tokens.get("refresh_token")
        if not (client_id and client_secret and refresh_token):
            # No way to refresh (e.g. pre-fix credentials file, or refresh
            # already attempted and the server didn't return one) -- fall
            # back to whatever access_token is on disk and let the API
            # call itself raise if it's actually expired.
            return tokens["access_token"]

        refreshed = _strava_refresh_token(client_id, client_secret, refresh_token)
        tokens["access_token"] = refreshed.get("access_token", tokens["access_token"])
        tokens["refresh_token"] = refreshed.get("refresh_token", refresh_token)
        if "expires_at" in refreshed:
            tokens["expires_at"] = refreshed["expires_at"]
        self._save_tokens(tokens)
        return tokens["access_token"]

    def is_connected(self) -> bool:
        return self._token_path.exists()

    def disconnect(self) -> None:
        if self._token_path.exists():
            self._token_path.unlink()

    def auth_url(self) -> str:
        """Return Strava OAuth authorization URL."""
        from urllib.parse import urlencode

        from vectorcode.src.connectors.oauth import (
            get_client_credentials,
            get_provider_for_connector,
        )

        provider = get_provider_for_connector("strava")
        if not provider:
            return "https://www.strava.com/settings/api"
        creds = get_client_credentials(provider)
        if not creds:
            return "https://www.strava.com/settings/api"
        client_id, _ = creds
        redirect_uri = f"http://{provider.callback_host}:{provider.callback_port}{provider.callback_path}"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(provider.scopes),
        }
        return f"{provider.auth_endpoint}?{urlencode(params)}"

    def handle_callback(self, code: str) -> None:
        """Exchange authorization code for tokens and save."""
        from vectorcode.src.connectors.oauth import (
            _CONNECTORS_DIR,
            _exchange_token,
            get_client_credentials,
            get_provider_for_connector,
            save_tokens,
        )

        provider = get_provider_for_connector("strava")
        creds = get_client_credentials(provider) if provider else None
        if not provider or not creds:
            raise RuntimeError("Strava client credentials not configured")
        client_id, client_secret = creds
        redirect_uri = f"http://{provider.callback_host}:{provider.callback_port}{provider.callback_path}"
        tokens = _exchange_token(provider, code, client_id, client_secret, redirect_uri)
        payload = {
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if "expires_at" in tokens:
            payload["expires_at"] = tokens["expires_at"]
        for filename in provider.credential_files:
            save_tokens(str(_CONNECTORS_DIR / filename), payload)

    def sync(
        self, *, since: Optional[datetime] = None, cursor: Optional[str] = None
    ) -> Iterator[Document]:
        token = self._get_access_token()
        after_epoch = int((since or datetime.now() - timedelta(days=7)).timestamp())

        activities = _strava_api_get(
            token,
            "athlete/activities",
            params={"after": str(after_epoch), "per_page": "50"},
        )

        for act in activities:
            ts = (
                datetime.fromisoformat(act["start_date_local"].replace("Z", "+00:00"))
                if "start_date_local" in act
                else datetime.now()
            )

            yield Document(
                doc_id=f"strava-{act['id']}",
                source="strava",
                doc_type=act.get("type", "Activity").lower(),
                content=json.dumps(act),
                title=act.get("name", "Untitled Activity"),
                timestamp=ts,
                metadata={
                    "distance_m": act.get("distance", 0),
                    "moving_time_s": act.get("moving_time", 0),
                    "sport_type": act.get("sport_type", ""),
                },
            )

        self._status.state = "idle"
        self._status.last_sync = datetime.now()

    def sync_status(self) -> SyncStatus:
        return self._status
