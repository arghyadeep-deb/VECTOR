"""Tests for OpenWA-inspired absorption:
- HMAC webhook signing (core/engine/webhook/)
- Bulk message sender (vectorcode/src/channels/bulk_sender.py)
- WhatsApp Business extensions (vectorcode/src/channels/whatsapp_business.py)

All tests are deterministic. No live network calls.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

from vectorcode.src.channels._abc import BaseChannel, ChannelStatus


# ── WebhookSigner ─────────────────────────────────────────────────────────────

class TestWebhookSigner:
    def setup_method(self):
        from core.engine.webhook.hmac_signer import WebhookSigner
        self.signer = WebhookSigner()
        self.secret = "super_secret_key"
        self.body = b'{"event":"message_sent","data":{"to":"919876543210"}}'

    def test_sign_returns_sha256_prefix(self):
        sig = self.signer.sign(self.body, self.secret)
        assert sig.startswith("sha256=")

    def test_sign_deterministic(self):
        assert self.signer.sign(self.body, self.secret) == self.signer.sign(self.body, self.secret)

    def test_sign_matches_stdlib_hmac(self):
        expected_hex = hmac.new(self.secret.encode(), self.body, hashlib.sha256).hexdigest()
        assert self.signer.sign(self.body, self.secret) == f"sha256={expected_hex}"

    def test_verify_correct_signature(self):
        sig = self.signer.sign(self.body, self.secret)
        assert self.signer.verify(self.body, sig, self.secret)

    def test_verify_wrong_secret_fails(self):
        sig = self.signer.sign(self.body, self.secret)
        assert not self.signer.verify(self.body, sig, "wrong_secret")

    def test_verify_tampered_body_fails(self):
        sig = self.signer.sign(self.body, self.secret)
        assert not self.signer.verify(b"tampered", sig, self.secret)

    def test_verify_bad_signature_format(self):
        assert not self.signer.verify(self.body, "not-a-sig", self.secret)

    def test_signed_headers_has_required_keys(self):
        headers = self.signer.signed_headers(self.body, self.secret)
        assert "X-Signature-256" in headers
        assert "X-Delivery-Id" in headers
        assert "X-Timestamp" in headers
        assert "Content-Type" in headers

    def test_signed_headers_signature_verifiable(self):
        headers = self.signer.signed_headers(self.body, self.secret)
        assert self.signer.verify(self.body, headers["X-Signature-256"], self.secret)

    def test_signed_headers_custom_delivery_id(self):
        headers = self.signer.signed_headers(self.body, self.secret, delivery_id="custom-id-123")
        assert headers["X-Delivery-Id"] == "custom-id-123"

    def test_different_secrets_different_sigs(self):
        sig1 = self.signer.sign(self.body, "secret_a")
        sig2 = self.signer.sign(self.body, "secret_b")
        assert sig1 != sig2

    def test_empty_body_signed(self):
        sig = self.signer.sign(b"", self.secret)
        assert sig.startswith("sha256=")
        assert self.signer.verify(b"", sig, self.secret)

    def test_get_signer_singleton(self):
        from core.engine.webhook.hmac_signer import get_signer
        a = get_signer()
        b = get_signer()
        assert a is b


# ── WebhookDelivery ───────────────────────────────────────────────────────────

class TestWebhookDelivery:
    def setup_method(self):
        from core.engine.webhook.hmac_signer import WebhookDelivery
        self.delivery = WebhookDelivery(max_retries=2, backoff_base=0.0)
        self.secret = "test_secret"
        self.payload = {"event": "test", "data": "hello"}

    def test_deliver_success(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
            result = self.delivery.deliver("https://example.com/hook", self.payload, self.secret)
        assert result.success
        assert result.status_code == 200
        assert result.attempt == 1

    def test_deliver_4xx_no_retry(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
            result = self.delivery.deliver("https://example.com/hook", self.payload)
        assert not result.success
        assert result.attempt == 1   # 4xx → no retry

    def test_deliver_5xx_retries(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 503
            mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
            result = self.delivery.deliver("https://example.com/hook", self.payload)
        assert not result.success
        assert result.attempt == 2   # retried up to max_retries

    def test_deliver_without_secret_no_signature_header(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_capture = mock_client_cls.return_value.__enter__.return_value.post
            mock_capture.return_value = mock_resp
            self.delivery.deliver("https://example.com/hook", self.payload, secret="")
            call_kwargs = mock_capture.call_args
            sent_headers = call_kwargs.kwargs.get("headers", {})
            assert "X-Signature-256" not in sent_headers

    def test_deliver_with_secret_adds_signature(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_capture = mock_client_cls.return_value.__enter__.return_value.post
            mock_capture.return_value = mock_resp
            self.delivery.deliver("https://example.com/hook", self.payload, self.secret)
            call_kwargs = mock_capture.call_args
            sent_headers = call_kwargs.kwargs.get("headers", {})
            assert "X-Signature-256" in sent_headers
            assert sent_headers["X-Signature-256"].startswith("sha256=")

    def test_deliver_to_many(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
            results = self.delivery.deliver_to_many(
                ["https://a.com/hook", "https://b.com/hook"],
                self.payload, self.secret,
            )
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_deliver_network_error_retries(self):
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.post.side_effect = ConnectionError("timeout")
            result = self.delivery.deliver("https://example.com/hook", self.payload)
        assert not result.success
        assert result.error != ""


# ── Webhook channel HMAC upgrade ──────────────────────────────────────────────

class TestWebhookChannelHmac:
    def test_webhook_channel_uses_hmac_when_secret_set(self):
        from vectorcode.src.channels.webhook import WebhookChannel
        ch = WebhookChannel(url="https://example.com/hook", secret="my_secret")
        ch.connect()
        with patch("httpx.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_req.return_value = mock_resp
            ch.send("webhook", "test message")
            call_kwargs = mock_req.call_args
            sent_headers = call_kwargs.kwargs.get("headers", {})
            # Should now send X-Signature-256 instead of plain X-Webhook-Secret
            assert "X-Signature-256" in sent_headers or "X-Webhook-Secret" in sent_headers


# ── BulkSender ────────────────────────────────────────────────────────────────

def _make_mock_channel(channel_id: str = "telegram", send_return: bool = True) -> MagicMock:
    ch = MagicMock(spec=BaseChannel)
    ch.channel_id = channel_id
    ch.send.return_value = send_return
    return ch


class TestBulkSender:
    def setup_method(self):
        from vectorcode.src.channels.bulk_sender import BulkSender, BulkMessage, _SentRegistry
        self.BulkSender = BulkSender
        self.BulkMessage = BulkMessage
        # The dedup registry is process-wide (one hour TTL), so a message sent by an earlier test would be
        # skipped as a duplicate here -- every test starts from an empty registry.
        _SentRegistry._entries.clear()

    def test_dry_run_all_skipped(self):
        ch = _make_mock_channel()
        sender = self.BulkSender(ch)
        msgs = [self.BulkMessage(f"user_{i}", f"hello {i}") for i in range(5)]
        result = sender.send_bulk(msgs, dry_run=True)
        assert len(result.skipped) == 5
        assert len(result.sent) == 0
        ch.send.assert_not_called()

    def test_send_all_success(self):
        ch = _make_mock_channel(send_return=True)
        sender = self.BulkSender(ch)
        msgs = [self.BulkMessage("recv_1", "msg 1"), self.BulkMessage("recv_2", "msg 2")]
        result = sender.send_bulk(msgs)
        assert result.sent == ["recv_1", "recv_2"]
        assert result.failed == []
        assert result.total == 2

    def test_send_partial_failure(self):
        ch = _make_mock_channel()
        ch.send.side_effect = [True, False, True]
        sender = self.BulkSender(ch)
        msgs = [self.BulkMessage(f"r{i}", f"m{i}") for i in range(3)]
        result = sender.send_bulk(msgs)
        assert len(result.sent) == 2
        assert len(result.failed) == 1

    def test_fail_fast_stops_on_first_failure(self):
        ch = _make_mock_channel()
        ch.send.side_effect = [False, True, True]
        sender = self.BulkSender(ch, fail_fast=True)
        msgs = [self.BulkMessage(f"r{i}", f"m{i}") for i in range(3)]
        result = sender.send_bulk(msgs)
        assert ch.send.call_count == 1

    def test_empty_list_returns_zero(self):
        ch = _make_mock_channel()
        sender = self.BulkSender(ch)
        result = sender.send_bulk([])
        assert result.total == 0
        assert result.sent == []

    def test_success_rate_all_sent(self):
        ch = _make_mock_channel(send_return=True)
        sender = self.BulkSender(ch)
        msgs = [self.BulkMessage(f"r{i}", "hi") for i in range(4)]
        result = sender.send_bulk(msgs)
        assert result.success_rate == 1.0

    def test_success_rate_no_messages(self):
        from vectorcode.src.channels.bulk_sender import BulkResult
        r = BulkResult()
        assert r.success_rate == 0.0

    def test_rate_limit_for_known_channels(self):
        assert self.BulkSender.rate_limit_for("telegram") == 30.0
        assert self.BulkSender.rate_limit_for("whatsapp") == 80.0
        assert self.BulkSender.rate_limit_for("slack") == 1.0

    def test_rate_limit_for_unknown_defaults(self):
        assert self.BulkSender.rate_limit_for("unknown_xyz") == 2.0

    def test_rate_limit_override(self):
        ch = _make_mock_channel()
        sender = self.BulkSender(ch, rate_limit_override=100.0)
        assert abs(sender._delay - 0.01) < 0.001   # 1/100 = 0.01s

    def test_exception_in_send_counted_as_failure(self):
        ch = _make_mock_channel()
        ch.send.side_effect = RuntimeError("unexpected")
        sender = self.BulkSender(ch)
        result = sender.send_bulk([self.BulkMessage("r1", "hi")])
        assert result.failed == ["r1"]

    def test_elapsed_seconds_populated(self):
        ch = _make_mock_channel(send_return=True)
        sender = self.BulkSender(ch)
        result = sender.send_bulk([self.BulkMessage("r1", "hi")])
        assert result.elapsed_seconds >= 0.0


# ── WhatsAppBusinessChannel ───────────────────────────────────────────────────

class TestWhatsAppBusinessChannel:
    def setup_method(self):
        from vectorcode.src.channels.whatsapp_business import WhatsAppBusinessChannel
        self.Ch = WhatsAppBusinessChannel

    def test_channel_id(self):
        ch = self.Ch()
        assert ch.channel_id == "whatsapp_business"

    def test_no_token_send_template_returns_false(self):
        ch = self.Ch()
        assert ch.send_template("919876543210", "hello_world") is False

    def test_no_token_send_image_returns_false(self):
        ch = self.Ch()
        assert ch.send_image("919876543210", "https://example.com/img.jpg") is False

    def test_no_token_send_reaction_returns_false(self):
        ch = self.Ch()
        assert ch.send_reaction("919876543210", message_id="wamid.abc", emoji="👍") is False

    def test_no_token_send_interactive_buttons_returns_false(self):
        ch = self.Ch()
        result = ch.send_interactive_buttons("to", "Pick:", [("Yes", "y"), ("No", "n")])
        assert result is False

    def test_no_token_send_interactive_list_returns_false(self):
        ch = self.Ch()
        result = ch.send_interactive_list("to", "Body", "Open", [])
        assert result is False

    def test_no_token_send_channel_message_returns_false(self):
        ch = self.Ch()
        assert ch.send_channel_message("channel_id_123", "Hello subscribers!") is False

    def test_send_template_posts_correct_payload(self):
        ch = self.Ch(access_token="fake_tok", phone_number_id="12345")
        ch.connect()
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            result = ch.send_template("919876543210", "hello_world", language="en_US")
        assert result is True
        call_kwargs = mock_post.call_args
        sent_payload = call_kwargs.kwargs["json"]
        assert sent_payload["type"] == "template"
        assert sent_payload["template"]["name"] == "hello_world"
        assert sent_payload["template"]["language"]["code"] == "en_US"

    def test_send_image_posts_correct_type(self):
        ch = self.Ch(access_token="fake_tok", phone_number_id="12345")
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            ch.send_image("919876543210", "https://cdn.example.com/img.jpg", caption="Look!")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "image"
        assert payload["image"]["caption"] == "Look!"

    def test_send_reaction_posts_correct_type(self):
        ch = self.Ch(access_token="fake_tok", phone_number_id="12345")
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            ch.send_reaction("919876543210", message_id="wamid.abc123", emoji="🎉")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "reaction"
        assert payload["reaction"]["emoji"] == "🎉"
        assert payload["reaction"]["message_id"] == "wamid.abc123"

    def test_send_interactive_buttons_max_3(self):
        ch = self.Ch(access_token="fake_tok", phone_number_id="12345")
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            ch.send_interactive_buttons("to", "Pick:", [
                ("A", "a"), ("B", "b"), ("C", "c"), ("D", "d"),  # 4 buttons — should cap at 3
            ])
        payload = mock_post.call_args.kwargs["json"]
        buttons = payload["interactive"]["action"]["buttons"]
        assert len(buttons) == 3

    def test_send_video(self):
        ch = self.Ch(access_token="tok", phone_number_id="123")
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = ch.send_video("to", "https://example.com/video.mp4", caption="Watch!")
        assert result is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "video"

    def test_send_document(self):
        ch = self.Ch(access_token="tok", phone_number_id="123")
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = ch.send_document("to", "https://example.com/file.pdf", filename="report.pdf")
        assert result is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "document"
        assert payload["document"]["filename"] == "report.pdf"

    def test_remove_reaction_sends_empty_emoji(self):
        ch = self.Ch(access_token="tok", phone_number_id="123")
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            ch.remove_reaction("to", message_id="wamid.xyz")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["reaction"]["emoji"] == ""

    def test_api_error_returns_false(self):
        ch = self.Ch(access_token="tok", phone_number_id="123")
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=400, text="Bad Request")
            result = ch.send_image("to", "https://example.com/img.jpg")
        assert result is False

    def test_inherits_base_send(self):
        from vectorcode.src.channels.whatsapp_business import WhatsAppBusinessChannel
        from vectorcode.src.channels.whatsapp import WhatsAppChannel
        assert issubclass(WhatsAppBusinessChannel, WhatsAppChannel)

    def test_registered_in_registry(self):
        from vectorcode.src.core.registry import ChannelRegistry
        assert "whatsapp_business" in ChannelRegistry._entries()
