"""Regression for vectorcode/src/agent/anthropic_adapter.py's logging:

`from loguru import logger` was trapped inside the module's own docstring
(right after the opening line, never executes) -- the real `logger` name
came from a plain `import logging; logging.getLogger(__name__)` a few
lines later. Every %-style placeholder in this module's logger calls
(credential-read failures, OAuth token refresh, keychain reads) would
silently fail to substitute once a real loguru logger replaced the
stdlib one.
"""
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from loguru import logger as _real_loguru_logger

from agent import anthropic_adapter


def test_module_uses_the_real_loguru_logger():
    assert anthropic_adapter.logger is _real_loguru_logger


def test_no_stdlib_logging_import_or_shadow():
    src = inspect.getsource(anthropic_adapter)
    assert "import logging" not in src
    assert "logging.getLogger" not in src


def test_no_percent_style_placeholders_remain():
    src = inspect.getsource(anthropic_adapter)
    for m in re.finditer(r"logger\.\w+\(([^)]*\))", src, re.DOTALL):
        call_text = m.group(0)
        assert not re.search(r"%[sdr]|%\.\d*f", call_text), (
            f"found a %-style placeholder in a logger call: {call_text!r}"
        )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
