"""Regression for vectorcode/src/channels/webhook.py's WebhookChannel:

send() posted to self._url via httpx with zero SSRF validation -- a
caller-configured URL pointing at a private/metadata address (e.g.
http://169.254.169.254/) would be fetched directly. Same bug class fixed
in core/browser/, core/seo/, core/vision_control/ this cycle. Fixed with
SSRFGuard(resolve_dns=True) before the real httpx call.

Also fixed in this same file (part of a 31-file systemic sweep across
vectorcode/src/channels/+cron/): stdlib logging.getLogger(__name__)
instead of loguru (shadowed the loguru import), same class already
fixed 23 times in sibling vectorcode directories.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.channels.webhook import WebhookChannel


def test_send_blocks_private_ip_target():
    chan = WebhookChannel(url="http://169.254.169.254/latest/meta-data/")
    with patch("httpx.request") as mock_request:
        result = chan.send("general", "hello")
    assert result is False
    mock_request.assert_not_called()


def test_send_blocks_localhost_target():
    chan = WebhookChannel(url="http://127.0.0.1:8080/admin")
    with patch("httpx.request") as mock_request:
        result = chan.send("general", "hello")
    assert result is False
    mock_request.assert_not_called()


def test_send_allows_legitimate_public_url():
    chan = WebhookChannel(url="https://example.com/webhook")
    fake_resp = MagicMock(status_code=200)
    with patch("httpx.request", return_value=fake_resp) as mock_request:
        result = chan.send("general", "hello")
    assert result is True
    mock_request.assert_called_once()


def test_logger_is_loguru_not_stdlib():
    import vectorcode.src.channels.webhook as mod
    assert mod.logger.__class__.__module__.startswith("loguru")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
