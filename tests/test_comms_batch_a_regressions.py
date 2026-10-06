"""Regression tests for the batch-A ``vectorcode.src.comms`` audit."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest


def test_send_imessage_rejects_nonzero_osascript_exit(monkeypatch) -> None:
    from vectorcode.src.comms import imessage_daemon

    def failed_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stderr="not authorised")

    monkeypatch.setattr(imessage_daemon.subprocess, "run", failed_run)

    assert imessage_daemon.send_imessage("chat-id", "hello") is False


def test_message_deduplicator_enforces_max_size() -> None:
    from vectorcode.src.comms.gateway_helpers import MessageDeduplicator

    deduplicator = MessageDeduplicator(max_size=2, ttl=3600)
    for message_id in ("first", "second", "third"):
        assert deduplicator.is_duplicate(message_id) is False

    assert len(deduplicator._seen) == 2
    assert deduplicator.is_duplicate("first") is False


def test_pending_queue_save_uses_atomic_replace(tmp_path, monkeypatch) -> None:
    from vectorcode.src.comms import messenger

    pending_file = tmp_path / "pending.json"
    monkeypatch.setattr(messenger, "_MSG_DIR", tmp_path)
    monkeypatch.setattr(messenger, "_PENDING_FILE", pending_file)
    monkeypatch.setattr(messenger.MessagingHub, "_start_scheduler", lambda self: None)

    replaced = []
    real_replace = messenger.os.replace

    def recording_replace(source, destination):
        replaced.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(messenger.os, "replace", recording_replace)

    hub = messenger.MessagingHub()
    hub._pending = [{"channel": "email", "text": "hello", "priority": "normal"}]
    hub._save_pending()

    assert pending_file.read_text(encoding="utf-8").startswith("[")
    assert len(replaced) == 1
    assert replaced[0][1] == pending_file
    assert not replaced[0][0].exists()


@pytest.mark.asyncio
async def test_discord_hub_uses_webhook_adapter(tmp_path, monkeypatch) -> None:
    from vectorcode.src.comms import messenger
    from vectorcode.src.comms.discord_bot import DiscordWebhook

    monkeypatch.setattr(
        messenger,
        "CONFIG",
        {"discord": {"webhook_url": "https://discord.invalid/webhook"}},
    )
    monkeypatch.setattr(messenger, "_MSG_DIR", tmp_path)
    monkeypatch.setattr(messenger, "_PENDING_FILE", tmp_path / "pending.json")
    monkeypatch.setattr(messenger.MessagingHub, "_start_scheduler", lambda self: None)

    calls = []

    async def successful_send(self, content, **kwargs):
        calls.append((self.webhook_url, content))
        return {"success": True}

    monkeypatch.setattr(DiscordWebhook, "send", successful_send)

    hub = messenger.MessagingHub()
    result = await hub._send_discord("hello", "normal")

    assert result == {"status": "sent", "platform": "discord"}
    assert calls == [("https://discord.invalid/webhook", "hello")]


@pytest.mark.asyncio
async def test_notification_does_not_report_adapter_errors_as_sent(tmp_path, monkeypatch) -> None:
    from vectorcode.src.comms import messenger

    monkeypatch.setattr(messenger, "_MSG_DIR", tmp_path)
    monkeypatch.setattr(messenger, "_PENDING_FILE", tmp_path / "pending.json")
    monkeypatch.setattr(messenger.MessagingHub, "_start_scheduler", lambda self: None)
    hub = messenger.MessagingHub()

    async def failed_send(platform, text, priority):
        return {"status": "error", "platform": platform}

    monkeypatch.setattr(hub, "send_to_channel", failed_send)
    result = await hub.send_notification("hello")

    assert result["status"] == "queued"
    assert result["reason"] == "all configured platforms failed"
    assert len(hub._pending) == 1


@pytest.mark.asyncio
async def test_homeassistant_rejects_failed_auth_and_closes_resources(monkeypatch) -> None:
    from vectorcode.src.comms import homeassistant_bot

    class FakeWebSocket:
        def __init__(self):
            self.responses = iter(
                ['{"type": "auth_required"}', '{"type": "auth_invalid"}']
            )
            self.closed = False

        async def receive_str(self):
            return next(self.responses)

        async def send_str(self, payload):
            self.payload = payload

        async def close(self):
            self.closed = True

    class FakeSession:
        def __init__(self):
            self.websocket = FakeWebSocket()
            self.closed = False

        async def ws_connect(self, url):
            return self.websocket

        async def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(
        homeassistant_bot,
        "aiohttp",
        SimpleNamespace(ClientSession=lambda: session),
    )
    monkeypatch.setattr(homeassistant_bot, "_AIOHTTP", True)

    bot = homeassistant_bot.HomeAssistantBot("https://ha.invalid", "bad-token")

    assert await bot.connect() is False
    assert bot._ws is None
    assert session.websocket.closed is True
    assert session.closed is True
