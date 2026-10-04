"""Regression for vectorcode/src/gateway/platforms/msgraph_webhook.py.

Bug fixed this cycle: stdlib `logging` instead of loguru (CLAUDE.md rule 6)
-- `import logging` + `logger = logging.getLogger(__name__)`, plus 3
printf-style (%s/%d/%r) placeholders left over from stdlib logging that
loguru's `{}`-style formatting silently fails to substitute.

Checked and confirmed NOT a bug this cycle:
- `_verify_client_state()` already used `hmac.compare_digest()`, not a bare
  `==`/`!=` -- timing-safe from the start.
- `DEFAULT_HOST = "0.0.0.0"` is a legitimate third-party webhook receiver
  (Microsoft Graph must reach it over the network); protected by optional
  `allowed_source_cidrs` IP allowlisting and `client_state` HMAC
  verification, same accepted pattern as gateway/platforms/wecom_callback.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from gateway.config import PlatformConfig
from gateway.platforms.msgraph_webhook import MSGraphWebhookAdapter


def _adapter(**extra) -> MSGraphWebhookAdapter:
    return MSGraphWebhookAdapter(PlatformConfig(enabled=True, extra=extra))


def test_module_uses_loguru_not_stdlib_logging():
    import inspect
    from gateway.platforms import msgraph_webhook
    src = inspect.getsource(msgraph_webhook)
    assert "import logging" not in src
    assert "from loguru import logger" in src
    assert "%s" not in src and "%d" not in src and "%r" not in src


def test_verify_client_state_uses_constant_time_compare():
    import inspect
    src = inspect.getsource(MSGraphWebhookAdapter._verify_client_state)
    assert "hmac.compare_digest" in src


def test_verify_client_state_accepts_matching_secret():
    adapter = _adapter(client_state="shared-secret-123")
    assert adapter._verify_client_state({"clientState": "shared-secret-123"}) is True


def test_verify_client_state_rejects_wrong_secret():
    adapter = _adapter(client_state="shared-secret-123")
    assert adapter._verify_client_state({"clientState": "wrong"}) is False


def test_verify_client_state_rejects_missing_when_required():
    adapter = _adapter(client_state="shared-secret-123")
    assert adapter._verify_client_state({}) is False


def test_verify_client_state_passthrough_when_not_configured():
    adapter = _adapter()
    assert adapter._verify_client_state({}) is True


def test_source_ip_allowlist_blocks_outside_cidr():
    adapter = _adapter(allowed_source_cidrs="10.0.0.0/8")

    class _FakeRequest:
        remote = "203.0.113.5"

    assert adapter._source_ip_allowed(_FakeRequest()) is False


def test_source_ip_allowlist_allows_inside_cidr():
    adapter = _adapter(allowed_source_cidrs="10.0.0.0/8")

    class _FakeRequest:
        remote = "10.1.2.3"

    assert adapter._source_ip_allowed(_FakeRequest()) is True


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
