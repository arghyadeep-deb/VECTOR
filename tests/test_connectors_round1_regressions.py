from __future__ import annotations

import json
import sys
import types
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

import pytest
import httpx

from vectorcode.src.connectors._abc import BaseConnector, Document, SyncStatus
from vectorcode.src.connectors.attachment_store import AttachmentStore
from vectorcode.src.connectors.apple_music import AppleMusicConnector
from vectorcode.src.connectors.gcalendar import GCalendarConnector
from vectorcode.src.connectors.gmail_imap import GmailIMAPConnector
from vectorcode.src.connectors.notion import NotionConnector
from vectorcode.src.connectors.oauth import (
    _wait_for_callback_code,
    build_google_auth_url,
    load_tokens,
    save_tokens,
)
from vectorcode.src.connectors.sync_engine import SyncEngine
from vectorcode.src.connectors.slack_connector import SlackConnector


def test_attachment_store_rejects_non_digest_lookup(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_bytes(b"private")
    store = AttachmentStore(str(tmp_path / "blobs"))
    try:
        assert store.get_content("../../secret") is None
    finally:
        store.close()


def test_oauth_token_save_replaces_complete_json(tmp_path: Path) -> None:
    target = tmp_path / "tokens.json"
    save_tokens(str(target), {"access_token": "secret", "expires_in": 0})
    assert load_tokens(str(target)) == {"access_token": "secret", "expires_in": 0}
    assert not list(tmp_path.glob(".tokens.json.*"))


def test_google_auth_url_includes_supplied_state() -> None:
    url = build_google_auth_url("client", state="nonce")
    assert "state=nonce" in url


def test_oauth_callback_rejects_wrong_state_and_honors_deadline(monkeypatch) -> None:
    class FakeServer:
        def __init__(self, _address, handler):
            self.handler = handler
            self.timeout = None

        def handle_request(self):
            request = self.handler.__new__(self.handler)
            request.path = "/callback?code=attacker&state=wrong"
            request.wfile = BytesIO()
            request.send_response = lambda _status: None
            request.send_header = lambda *_args: None
            request.end_headers = lambda: None
            request.do_GET()

        def server_close(self):
            pass

    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr("http.server.HTTPServer", FakeServer)
    monkeypatch.setattr("vectorcode.src.connectors.oauth.time.sleep", lambda _delay: None)
    monkeypatch.setattr(
        "vectorcode.src.connectors.oauth.time.monotonic", lambda: next(ticks)
    )
    with pytest.raises(RuntimeError, match="timed out"):
        _wait_for_callback_code(timeout=1, expected_state="expected")


def test_imap_zero_limit_does_not_expand_to_full_mailbox(monkeypatch) -> None:
    class FakeIMAP:
        fetch_calls = 0

        def __init__(self, _host):
            pass

        def login(self, _email, _password):
            pass

        def select(self, *_args, **_kwargs):
            pass

        def search(self, *_args):
            return "OK", [b"1 2 3"]

        def fetch(self, *_args):
            type(self).fetch_calls += 1
            raise AssertionError("zero limit must not fetch")

        def logout(self):
            pass

    monkeypatch.setattr("vectorcode.src.connectors.gmail_imap.imaplib.IMAP4_SSL", FakeIMAP)
    connector = GmailIMAPConnector("a@example.com", "pw", max_messages=0)
    assert list(connector.sync()) == []
    assert FakeIMAP.fetch_calls == 0


def test_notion_rejects_non_advancing_cursor(monkeypatch, tmp_path: Path) -> None:
    token_path = tmp_path / "notion.json"
    token_path.write_text(json.dumps({"token": "token"}), encoding="utf-8")
    monkeypatch.setattr(
        "vectorcode.src.connectors.notion._notion_api_search",
        lambda *_args, **_kwargs: {"results": [], "has_more": True, "next_cursor": "same"},
    )
    connector = NotionConnector(credentials_path=str(token_path))
    with pytest.raises(RuntimeError, match="without a new cursor"):
        list(connector.sync(cursor="same"))


def test_calendar_event_failure_is_not_reported_as_empty_success(
    monkeypatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "google.json"
    token_path.write_text(json.dumps({"access_token": "token"}), encoding="utf-8")
    monkeypatch.setattr(
        "vectorcode.src.connectors.gcalendar._gcal_api_calendars_list",
        lambda _token: {"items": [{"id": "primary"}]},
    )
    response = httpx.Response(401, request=httpx.Request("GET", "https://example.test"))
    monkeypatch.setattr(
        "vectorcode.src.connectors.gcalendar._gcal_api_events_list",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            httpx.HTTPStatusError("unauthorized", request=response.request, response=response)
        ),
    )
    connector = GCalendarConnector(credentials_path=str(token_path))
    with pytest.raises(httpx.HTTPStatusError):
        list(connector.sync())


def test_slack_collection_failure_is_not_reported_as_success(
    monkeypatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "slack.json"
    token_path.write_text(json.dumps({"token": "token"}), encoding="utf-8")
    monkeypatch.setattr(
        "vectorcode.src.connectors.slack_connector._slack_api_users_list",
        lambda _token: {"ok": True, "members": []},
    )
    monkeypatch.setattr(
        "vectorcode.src.connectors.slack_connector._slack_api_conversations_list",
        lambda *_args, **_kwargs: {"ok": False, "error": "invalid_auth"},
    )
    connector = SlackConnector(credentials_path=str(token_path))
    with pytest.raises(RuntimeError, match="invalid_auth"):
        list(connector.sync())


def test_apple_music_query_failure_propagates(monkeypatch) -> None:
    monkeypatch.setattr(
        "vectorcode.src.connectors.apple_music._run_osascript", lambda _script: None
    )
    connector = AppleMusicConnector()
    with pytest.raises(RuntimeError, match="AppleScript query failed"):
        list(connector.sync())
    assert connector.sync_status().state == "error"


class _CursorConnector(BaseConnector):
    connector_id = "cursor-test"
    display_name = "Cursor Test"
    auth_type = "local"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.status = SyncStatus(cursor="new-cursor")

    def is_connected(self) -> bool:
        return True

    def disconnect(self) -> None:
        return None

    def sync(self, *, since=None, cursor=None):
        if self.fail:
            raise RuntimeError("boom")
        yield Document("doc", "test", "text", "body")

    def sync_status(self) -> SyncStatus:
        return self.status


class _Pipeline:
    def ingest(self, docs) -> int:
        return len(docs)


def test_sync_engine_persists_connector_cursor_and_keeps_failure_boundary() -> None:
    engine = SyncEngine(_Pipeline(), state_db=":memory:")
    connector = _CursorConnector()
    engine.sync(connector)
    first = engine.get_checkpoint(connector.connector_id)
    assert first and first["cursor"] == "new-cursor"
    first_boundary = first["last_sync"]

    connector.fail = True
    connector.status.cursor = "failure-cursor"
    with pytest.raises(RuntimeError, match="boom"):
        engine.sync(connector)
    failed = engine.get_checkpoint(connector.connector_id)
    assert failed and failed["last_sync"] == first_boundary
    assert failed["cursor"] == "failure-cursor"
    assert failed["error"] == "boom"


def test_embedding_store_hashes_chunk_id_and_rejects_legacy_escape(
    monkeypatch, tmp_path: Path
) -> None:
    saved_paths: list[str] = []

    fake_torch = types.SimpleNamespace(
        save=lambda _embedding, path: (saved_paths.append(path), Path(path).write_bytes(b"tensor")),
        load=lambda *_args, **_kwargs: b"tensor",
        Tensor=object,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    from vectorcode.src.connectors.embedding_store import EmbeddingStore

    store = EmbeddingStore(str(tmp_path / "embeddings"))
    try:
        store.store("../../escape", object())
        row = store._conn.execute(
            "SELECT filename FROM embedding_index WHERE chunk_id = ?", ("../../escape",)
        ).fetchone()
        assert row and "/" not in row[0] and "\\" not in row[0]
        store._conn.execute(
            "INSERT OR REPLACE INTO embedding_index (chunk_id, filename) VALUES (?, ?)",
            ("legacy", "../../outside.pt"),
        )
        store._conn.commit()
        assert store.get("legacy") is None
        assert store.delete("legacy") is False
    finally:
        store.close()
