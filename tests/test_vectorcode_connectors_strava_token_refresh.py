"""Regression for vectorcode/src/connectors/strava.py's StravaConnector:

_strava_refresh_token() existed in this module but had zero callers anywhere
in the repo -- the module's own docstring claimed "Refresh handled
automatically", but _get_access_token() just read the stored access_token
directly with no expiry check or refresh call. Strava access tokens expire
after ~6 hours, so every sync() after that point failed with a 401 until the
user manually re-authenticated.

Fixed: _get_access_token() now checks a persisted expires_at (with a 60s
safety margin) and calls _strava_refresh_token() to get a fresh token,
persisting the result. handle_callback() now also persists expires_at from
the initial token exchange.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.connectors.strava import StravaConnector


def _write_tokens(path: Path, **overrides) -> None:
    tokens = {
        "access_token": "stale-token",
        "refresh_token": "refresh-xyz",
        "client_id": "cid",
        "client_secret": "csecret",
        "expires_at": time.time() - 10,  # already expired
    }
    tokens.update(overrides)
    path.write_text(json.dumps(tokens), encoding="utf-8")


def test_get_access_token_refreshes_when_expired(tmp_path):
    token_path = tmp_path / "strava.json"
    _write_tokens(token_path)
    connector = StravaConnector(token_path=str(token_path))

    with patch(
        "vectorcode.src.connectors.strava._strava_refresh_token",
        return_value={
            "access_token": "fresh-token",
            "refresh_token": "refresh-xyz",
            "expires_at": time.time() + 21600,
        },
    ) as mock_refresh:
        token = connector._get_access_token()

    mock_refresh.assert_called_once_with("cid", "csecret", "refresh-xyz")
    assert token == "fresh-token"
    # The refreshed token must be persisted so subsequent calls see it.
    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved["access_token"] == "fresh-token"
    assert saved["expires_at"] > time.time()


def test_get_access_token_skips_refresh_when_still_valid(tmp_path):
    token_path = tmp_path / "strava.json"
    _write_tokens(token_path, expires_at=time.time() + 3600)
    connector = StravaConnector(token_path=str(token_path))

    with patch("vectorcode.src.connectors.strava._strava_refresh_token") as mock_refresh:
        token = connector._get_access_token()

    mock_refresh.assert_not_called()
    assert token == "stale-token"


def test_get_access_token_falls_back_without_refresh_credentials(tmp_path):
    token_path = tmp_path / "strava.json"
    token_path.write_text(
        json.dumps({"access_token": "legacy-token"}), encoding="utf-8"
    )
    connector = StravaConnector(token_path=str(token_path))

    with patch("vectorcode.src.connectors.strava._strava_refresh_token") as mock_refresh:
        token = connector._get_access_token()

    mock_refresh.assert_not_called()
    assert token == "legacy-token"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
