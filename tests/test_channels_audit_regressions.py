"""Regression tests for the 2026-10-06 channels audit."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest


def test_bulk_sender_preserves_explicit_zero_rate_override() -> None:
    from vectorcode.src.channels.bulk_sender import BulkSender

    channel = MagicMock()
    channel.channel_id = "telegram"
    sender = BulkSender(channel, rate_limit_override=0.0)
    assert sender._delay == 100.0


def test_telegram_empty_message_does_not_report_phantom_success(monkeypatch) -> None:
    from vectorcode.src.channels.telegram import TelegramChannel

    post = MagicMock()
    monkeypatch.setattr(httpx, "post", post)
    assert TelegramChannel(bot_token="token").send("123", " \n\t") is False
    post.assert_not_called()


def test_twitter_snowflake_comparison_is_numeric() -> None:
    from vectorcode.src.channels.twitter_channel import _is_newer_tweet_id

    assert _is_newer_tweet_id("100", "99") is True
    assert _is_newer_tweet_id("99", "100") is False


def test_gmail_token_write_is_atomic_utf8(tmp_path: Path, monkeypatch) -> None:
    from vectorcode.src.channels import gmail

    target = tmp_path / "token.json"
    replacements: list[tuple[str, Path]] = []
    real_replace = gmail.os.replace

    def record_replace(source: str, destination: Path) -> None:
        replacements.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(gmail.os, "replace", record_replace)
    gmail._atomic_write_text(str(target), '{"name":"VÉCTOR"}')
    assert target.read_text(encoding="utf-8") == '{"name":"VÉCTOR"}'
    assert replacements and replacements[0][1] == target
    assert Path(replacements[0][0]).parent == target.parent


def test_webhook_signature_matches_exact_transmitted_body(monkeypatch) -> None:
    import vectorcode.src.channels.webhook as webhook_module

    captured: dict[str, object] = {}

    class SafeResult:
        safe = True
        reason = ""

    monkeypatch.setattr(
        "core.security.ssrf_guard.SSRFGuard.check_url",
        lambda self, url: SafeResult(),
    )

    def request(method, url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "request", request)
    channel = webhook_module.WebhookChannel(
        url="https://example.com/hook",
        secret="secret",
    )
    assert channel.send("alerts", "café", metadata={"priority": 0}) is True
    body = captured["content"]
    headers = captured["headers"]
    assert isinstance(body, bytes)
    assert json.loads(body) == {
        "channel": "alerts",
        "content": "café",
        "metadata": {"priority": 0},
    }
    expected = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert headers["X-Signature-256"] == expected


async def test_social_adapters_do_not_treat_http_errors_as_success(monkeypatch) -> None:
    from vectorcode.src.channels.adapters.linkedin_adapter import LinkedInAdapter
    from vectorcode.src.channels.adapters.youtube_adapter import YouTubeAdapter

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            return httpx.Response(401, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "AsyncClient", FailingClient)
    with pytest.raises(httpx.HTTPStatusError):
        await LinkedInAdapter().get_profile()
    with pytest.raises(httpx.HTTPStatusError):
        await YouTubeAdapter().search("VECTOR")


def test_twitch_irc_values_reject_command_injection() -> None:
    from vectorcode.src.channels.adapters.twitch_adapter import _irc_value

    with pytest.raises(ValueError):
        _irc_value("hello\r\nPRIVMSG #victim :injected")


def test_irc_channel_rejects_command_injection_before_network(monkeypatch) -> None:
    from vectorcode.src.channels.irc_channel import IRCChannel

    socket_factory = MagicMock()
    monkeypatch.setattr("vectorcode.src.channels.irc_channel.socket.socket", socket_factory)
    channel = IRCChannel(server="irc.example.com", nick="vector")
    assert channel.send("#safe", "hello\r\nJOIN #private") is False
    socket_factory.assert_not_called()
