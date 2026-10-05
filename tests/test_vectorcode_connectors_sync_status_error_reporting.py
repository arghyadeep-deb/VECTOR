"""Regression for vectorcode/src/connectors/{oura,weather,hackernews,granola}.py:

SyncStatus.state defaults to "idle" (see _abc.py), which is ALSO the value
each of these connectors' sync() set on success. None of the four wrapped
their generator body in a try/except, so a mid-sync exception (expired
token, API down, malformed credentials file) left self._status.state (or,
for granola, the freshly-constructed SyncStatus) looking exactly like
"never synced" -- sync_status().error was always None and state was always
"idle", even right after a crash. A caller polling sync_status() after a
failed sync had no way to tell a crash apart from "nothing synced yet".

Fixed: each sync() now wraps its body in try/except Exception, setting
state="error" + error=str(exc) before re-raising. Granola (which uses loose
instance attributes instead of a SyncStatus object) got a new
self._last_error attribute that sync_status() now surfaces.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.connectors.granola import GranolaConnector
from vectorcode.src.connectors.hackernews import HackerNewsConnector
from vectorcode.src.connectors.oura import OuraConnector
from vectorcode.src.connectors.weather import WeatherConnector


def test_oura_sync_failure_reports_error_status(tmp_path):
    # No token file written -> _load_token() raises FileNotFoundError.
    token_path = tmp_path / "oura.json"
    connector = OuraConnector(token_path=str(token_path))

    assert connector.sync_status().state == "idle"
    assert connector.sync_status().error is None

    with __import__("pytest").raises(Exception):
        list(connector.sync())

    status = connector.sync_status()
    assert status.state == "error"
    assert status.error is not None


def test_weather_sync_failure_reports_error_status(tmp_path):
    token_path = tmp_path / "weather.json"
    connector = WeatherConnector(token_path=str(token_path))

    with __import__("pytest").raises(Exception):
        list(connector.sync())

    status = connector.sync_status()
    assert status.state == "error"
    assert status.error is not None


def test_hackernews_sync_failure_reports_error_status():
    connector = HackerNewsConnector()

    with patch(
        "vectorcode.src.connectors.hackernews._hn_top_story_ids",
        side_effect=RuntimeError("HN API down"),
    ):
        with __import__("pytest").raises(RuntimeError):
            list(connector.sync())

    status = connector.sync_status()
    assert status.state == "error"
    assert status.error == "HN API down"


def test_granola_sync_failure_reports_error_status():
    connector = GranolaConnector(api_key="test-key")

    with patch(
        "vectorcode.src.connectors.granola._granola_api_list_notes",
        side_effect=RuntimeError("Granola API down"),
    ):
        with __import__("pytest").raises(RuntimeError):
            list(connector.sync())

    status = connector.sync_status()
    assert status.state == "error"
    assert status.error == "Granola API down"


def test_granola_sync_success_clears_prior_error():
    connector = GranolaConnector(api_key="test-key")
    connector._last_error = "stale error from a previous failed sync"

    with patch(
        "vectorcode.src.connectors.granola._granola_api_list_notes",
        return_value={"notes": [], "hasMore": False},
    ):
        list(connector.sync())

    status = connector.sync_status()
    assert status.state == "idle"
    assert status.error is None


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
