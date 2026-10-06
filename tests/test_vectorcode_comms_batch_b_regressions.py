"""Regression coverage for the batch-B VectorCode comms audit."""

from __future__ import annotations

import base64
import hashlib
import os
import xml.etree.ElementTree as ET

import pytest

from vectorcode.src.comms import signal_channel, yuanbao_media
from vectorcode.src.comms._abc import ChannelStatus
from vectorcode.src.comms.session_manager import SessionManager
from vectorcode.src.comms.twilio_sms import TwilioSMSChannel
from vectorcode.src.comms.twitch_channel import TwitchChannel
from vectorcode.src.comms.twitter_channel import TwitterChannel
from vectorcode.src.comms.wecom_callback import WeComCallback
from vectorcode.src.comms.wecom_crypto import DecryptError, WXBizMsgCrypt
from vectorcode.src.comms.yuanbao_sticker import StickerInfo, send_sticker


_TOKEN = "callback-token"
_CORP_ID = "corp-123"


def _crypto() -> WXBizMsgCrypt:
    aes_key = base64.b64encode(bytes(range(32))).decode("ascii").rstrip("=")
    return WXBizMsgCrypt(_TOKEN, aes_key, _CORP_ID)


def test_signal_channel_uses_comms_registry_and_event_types() -> None:
    assert signal_channel.BaseChannel.__module__ == "vectorcode.src.comms._abc"
    assert signal_channel.ChannelRegistry.__module__ == "vectorcode.src.vc_core.registry"


def test_channels_do_not_report_connected_with_incomplete_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "TWILIO_PHONE_NUMBER",
        "TWITCH_CLIENT_ID",
        "TWITTER_BOT_USER_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    twilio = TwilioSMSChannel(account_sid="sid", auth_token="token", phone_number="")
    twilio.connect()
    assert twilio.status() is ChannelStatus.ERROR

    twitch = TwitchChannel(access_token="token", client_id="", nick="sender")
    twitch.connect()
    assert twitch.status() is ChannelStatus.ERROR

    twitter = TwitterChannel(bearer_token="bearer", bot_user_id="")
    twitter.connect()
    assert twitter.status() is ChannelStatus.ERROR


def test_twitter_send_rejects_partial_oauth_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def unexpected_post(*_args, **_kwargs):
        nonlocal called
        called = True

    import httpx

    monkeypatch.setattr(httpx, "post", unexpected_post)
    channel = TwitterChannel(api_key="key", api_secret="", access_token="token", access_secret="secret")
    assert channel.send("", "hello") is False
    assert called is False


def test_expired_session_cannot_be_read_or_revived() -> None:
    manager = SessionManager()
    session = manager.get_or_create("telegram", "user", "chat")
    manager.append_message(session.session_id, "user", "secret")
    session.last_active = 0

    assert manager.get_history(session.session_id) == []
    manager.append_message(session.session_id, "user", "revive")
    assert manager.get(session.session_id) is None


def test_twilio_webhook_isolates_failing_handlers() -> None:
    channel = TwilioSMSChannel()
    received = []

    def fail(_message) -> None:
        raise RuntimeError("broken callback")

    channel.on_message(fail)
    channel.on_message(received.append)
    channel.handle_webhook("+15551234567", "hello", "SM123")

    assert len(received) == 1
    assert received[0].content == "hello"


def test_wecom_crypto_round_trip_and_rejects_truncated_payload() -> None:
    crypto = _crypto()
    envelope = crypto.encrypt("<xml><Content>hello</Content></xml>", nonce="fixed", timestamp="1")
    root = ET.fromstring(envelope)
    encrypted = root.findtext("Encrypt") or ""
    signature = root.findtext("MsgSignature") or ""

    assert crypto.decrypt(signature, "1", "fixed", encrypted) == (
        b"<xml><Content>hello</Content></xml>"
    )

    malformed = base64.b64encode(os.urandom(16)).decode("ascii")
    malformed_signature = hashlib.sha1(
        "".join(sorted([_TOKEN, "1", "fixed", malformed])).encode("utf-8")
    ).hexdigest()
    with pytest.raises(DecryptError):
        crypto.decrypt(malformed_signature, "1", "fixed", malformed)


def test_wecom_callback_verifies_echostr_and_receive_id() -> None:
    crypto = _crypto()
    envelope = crypto.encrypt("verified", nonce="nonce", timestamp="123")
    root = ET.fromstring(envelope)
    echo = root.findtext("Encrypt") or ""
    signature = root.findtext("MsgSignature") or ""
    callback = WeComCallback(_TOKEN, base64.b64encode(bytes(range(32))).decode("ascii").rstrip("="), _CORP_ID)

    assert callback.verify_url(signature, "123", "nonce", echo) == "verified"
    assert callback.verify_url(signature, "123", "nonce", echo + "A") is None
    wrong_corp = WeComCallback(_TOKEN, callback.encoding_aes_key, "other-corp")
    assert wrong_corp.verify_url(signature, "123", "nonce", echo) is None


@pytest.mark.asyncio
async def test_send_sticker_reports_failure_without_websocket() -> None:
    class Bot:
        _ws = None

    assert await send_sticker(Bot(), "user", StickerInfo("sticker", "pack")) is False


@pytest.mark.asyncio
async def test_yuanbao_media_checks_cos_put_result(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(b"not-really-an-image")

    class Response:
        def __init__(self, status_code: int, payload: dict | None = None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self) -> dict:
            return self._payload

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return Response(
                200,
                {
                    "code": 0,
                    "data": {
                        "bucket": "bucket.example",
                        "path": "/object",
                        "url": "https://cdn.example/object",
                    },
                },
            )

        async def put(self, *_args, **_kwargs):
            return Response(500)

    monkeypatch.setattr(yuanbao_media.httpx, "AsyncClient", Client)
    assert await yuanbao_media.upload_image(str(image), app_id="id", app_secret="secret") is None
