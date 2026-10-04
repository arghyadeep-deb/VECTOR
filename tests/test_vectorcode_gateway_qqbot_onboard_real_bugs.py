"""Regression for vectorcode/src/gateway/platforms/qqbot/onboard.py.

Bug fixed this cycle: stdlib `logging` instead of loguru (CLAUDE.md
rule 6) -- `import logging` + `logger = logging.getLogger(__name__)`,
plus 3 printf-style (%s/%d) placeholders that loguru's `{}`-style
formatting silently fails to substitute.

Checked and confirmed NOT a bug: the module's print() calls are
intentional terminal UI for an interactive one-time QR-scan setup flow
(mirrors feishu.qr_register()'s pattern), not production logging.
build_connect_url() URL-quotes task_id before interpolating into
QR_URL_TEMPLATE, so no injection risk there.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from gateway.platforms.qqbot.onboard import build_connect_url, BindStatus


def test_module_uses_loguru_not_stdlib_logging():
    import inspect
    from gateway.platforms.qqbot import onboard
    src = inspect.getsource(onboard)
    assert "import logging" not in src
    assert "from loguru import logger" in src
    assert "%s" not in src and "%d" not in src


def test_build_connect_url_quotes_task_id():
    # quote() uses the default safe="/" -- "/" passes through unescaped,
    # everything else (?, =, &) gets percent-encoded.
    url = build_connect_url("abc/def?evil=1")
    assert "abc/def%3Fevil%3D1" in url
    assert "?evil=1" not in url


def test_bind_status_values_unchanged():
    assert BindStatus.NONE == 0
    assert BindStatus.PENDING == 1
    assert BindStatus.COMPLETED == 2
    assert BindStatus.EXPIRED == 3


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
