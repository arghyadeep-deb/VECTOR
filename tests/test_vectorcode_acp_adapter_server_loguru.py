"""Regression: vectorcode/src/acp_adapter/server.py used stdlib
logging.getLogger(__name__) instead of loguru (CLAUDE.md rule 6), with
%s/%d-style placeholders throughout and exc_info=True on 9 except-blocks
-- loguru silently no-ops on an unrecognized exc_info= kwarg (verified
elsewhere this cycle with a standalone repro), so every one of those 9
sites was dropping the real exception. Also found 2 bare except blocks
(_cmd_tools, _cmd_compact) that returned the error text to the caller but
never logged it server-side at all.

Package has a hard dependency on the external agent-client-protocol (acp)
package, not installed in this sandbox -- verified via source inspection,
same approach as this package's other files this cycle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_SRC = (Path(__file__).parent.parent / "vectorcode" / "src" / "acp_adapter" / "server.py").read_text(encoding="utf-8")


def test_imports_loguru_not_stdlib_logging():
    assert "from loguru import logger" in _SRC
    assert "import logging" not in _SRC
    assert "logging.getLogger" not in _SRC


def test_no_percent_style_placeholders_remain():
    assert "%s" not in _SRC
    assert "%d" not in _SRC


def test_no_exc_info_kwarg_remains():
    assert "exc_info=True" not in _SRC


def test_cmd_tools_and_compact_now_log_their_errors():
    assert '"ACP /tools command failed: {}"' in _SRC
    assert '"ACP /compact command failed: {}"' in _SRC


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
