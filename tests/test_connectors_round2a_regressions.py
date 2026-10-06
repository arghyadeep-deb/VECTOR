"""Regression tests for the connector round 2a audit."""

import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from vectorcode.src.connectors import (
    gcontacts,
    gdrive,
    github_notifications,
    gmail,
    google_tasks,
    spotify,
)


def test_spotify_refreshes_and_persists_expired_token(tmp_path, monkeypatch):
    token_path = tmp_path / "spotify.json"
    token_path.write_text(
        json.dumps(
            {
                "access_token": "expired",
                "refresh_token": "refresh",
                "client_id": "client",
                "client_secret": "secret",
                "expires_at": time.time() - 1,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        spotify,
        "_spotify_refresh_token",
        lambda *_args: {"access_token": "fresh", "expires_in": 3600},
    )

    connector = spotify.SpotifyConnector(token_path=str(token_path))
    assert connector._get_access_token() == "fresh"
    persisted = json.loads(token_path.read_text(encoding="utf-8"))
    assert persisted["access_token"] == "fresh"
    assert persisted["refresh_token"] == "refresh"
    assert persisted["expires_at"] > time.time()


@pytest.mark.parametrize(
    ("connector", "module", "api_name"),
    [
        (spotify.SpotifyConnector, spotify, "_spotify_api_get"),
        (google_tasks.GoogleTasksConnector, google_tasks, "_tasks_api_get"),
        (
            github_notifications.GitHubNotificationsConnector,
            github_notifications,
            "_github_api_get",
        ),
    ],
)
def test_api_failure_sets_distinguishable_error_status(
    tmp_path, monkeypatch, connector, module, api_name
):
    credentials = tmp_path / "credentials.json"
    if connector is github_notifications.GitHubNotificationsConnector:
        credentials.write_text('{"token":"token"}', encoding="utf-8")
        instance = connector(token_path=str(credentials))
    elif connector is spotify.SpotifyConnector:
        credentials.write_text('{"access_token":"token"}', encoding="utf-8")
        instance = connector(token_path=str(credentials))
    else:
        credentials.write_text('{"access_token":"token"}', encoding="utf-8")
        instance = connector(credentials_path=str(credentials))

    def fail(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(module, api_name, fail)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        list(instance.sync())
    assert instance.sync_status().state == "error"
    assert instance.sync_status().error == "provider unavailable"


@pytest.mark.parametrize(
    ("connector", "module", "api_name"),
    [
        (gmail.GmailConnector, gmail, "_gmail_api_list_messages"),
        (gdrive.GDriveConnector, gdrive, "_gdrive_api_list_files"),
        (gcontacts.GContactsConnector, gcontacts, "_gcontacts_api_list"),
    ],
)
def test_google_connector_failure_is_reported(
    tmp_path, monkeypatch, connector, module, api_name
):
    credentials = tmp_path / "credentials.json"
    credentials.write_text('{"access_token":"token"}', encoding="utf-8")
    instance = connector(credentials_path=str(credentials))

    def fail(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(module, api_name, fail)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        list(instance.sync())
    assert instance.sync_status().state == "error"
    assert instance.sync_status().error == "provider unavailable"


def test_gmail_repeated_page_token_fails_instead_of_looping(tmp_path, monkeypatch):
    credentials = tmp_path / "credentials.json"
    credentials.write_text('{"access_token":"token"}', encoding="utf-8")
    connector = gmail.GmailConnector(credentials_path=str(credentials))
    monkeypatch.setattr(
        gmail,
        "_gmail_api_list_messages",
        lambda *_args, **_kwargs: {"messages": [], "nextPageToken": "repeat"},
    )

    with pytest.raises(RuntimeError, match="repeated page token"):
        list(connector.sync(cursor="repeat"))
    assert connector.sync_status().state == "error"


def test_drive_export_failure_is_not_indexed_as_placeholder(tmp_path, monkeypatch):
    credentials = tmp_path / "credentials.json"
    credentials.write_text('{"access_token":"token"}', encoding="utf-8")
    connector = gdrive.GDriveConnector(credentials_path=str(credentials))
    monkeypatch.setattr(
        gdrive,
        "_gdrive_api_list_files",
        lambda *_args, **_kwargs: {
            "files": [
                {
                    "id": "doc-1",
                    "name": "Important",
                    "mimeType": "application/vnd.google-apps.document",
                }
            ]
        },
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("export unavailable")

    monkeypatch.setattr(gdrive, "_gdrive_api_export", fail)
    with pytest.raises(RuntimeError, match="export unavailable"):
        list(connector.sync())
    assert connector.sync_status().state == "error"


@pytest.mark.parametrize(
    ("connector", "module", "api_name"),
    [
        (google_tasks.GoogleTasksConnector, google_tasks, "_tasks_api_get"),
        (
            github_notifications.GitHubNotificationsConnector,
            github_notifications,
            "_github_api_get",
        ),
    ],
)
def test_aware_since_uses_valid_utc_rfc3339(
    tmp_path, monkeypatch, connector, module, api_name
):
    credentials = tmp_path / "credentials.json"
    token_key = "token" if connector is github_notifications.GitHubNotificationsConnector else "access_token"
    credentials.write_text(json.dumps({token_key: "token"}), encoding="utf-8")
    instance = (
        connector(token_path=str(credentials))
        if connector is github_notifications.GitHubNotificationsConnector
        else connector(credentials_path=str(credentials))
    )
    captured = {}
    calls = 0

    def fake(*_args, **kwargs):
        nonlocal calls
        calls += 1
        captured.update(kwargs.get("params", {}))
        if connector is github_notifications.GitHubNotificationsConnector:
            return []
        return {"items": [{"id": "list", "title": "Tasks"}]} if calls == 1 else {"items": []}

    monkeypatch.setattr(module, api_name, fake)
    since = datetime(2026, 1, 2, 3, 4, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    list(instance.sync(since=since))
    key = "since" if connector is github_notifications.GitHubNotificationsConnector else "updatedMin"
    assert captured[key] == "2026-01-01T21:34:00Z"
