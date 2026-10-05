"""Regression for vectorcode/src/agent/bedrock_adapter.py's logging:

`from loguru import logger` was trapped inside the module's own docstring
(right after the opening line), so it never executed -- the real `logger`
name came from a plain `import logging; logger = logging.getLogger(__name__)`
a few lines later. Every %-style placeholder in this module's logger calls
would silently fail to substitute once that stdlib logger got swapped for
a real loguru one (loguru's {}-formatter does not understand %s/%r), making
every warning/debug call across stale-connection handling, tool-support
detection, and model-discovery failures silently print garbage.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from loguru import logger as _real_loguru_logger

from agent import bedrock_adapter


def test_module_uses_the_real_loguru_logger():
    assert bedrock_adapter.logger is _real_loguru_logger


def test_no_stdlib_logging_import_or_shadow():
    src = inspect.getsource(bedrock_adapter)
    assert "import logging" not in src
    assert "logging.getLogger" not in src


def test_no_percent_style_placeholders_remain():
    src = inspect.getsource(bedrock_adapter)
    import re
    # A %s/%d/%r/%.Nf inside a logger.*(...) call would silently fail to
    # substitute under loguru. Scan every logger.<level>(...) call site.
    for m in re.finditer(r"logger\.\w+\(([^)]*\))", src, re.DOTALL):
        call_text = m.group(0)
        assert not re.search(r"%[sdr]|%\.\d*f", call_text), (
            f"found a %-style placeholder in a logger call: {call_text!r}"
        )


def test_tool_support_warning_substitutes_model_name(capfd):
    _real_loguru_logger.remove()
    _real_loguru_logger.add(sys.stderr, format="{message}")
    try:
        kwargs = bedrock_adapter.build_converse_kwargs(
            model="deepseek.r1-v1:0",
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "x", "description": "d", "parameters": {}}}],
        )
    finally:
        _real_loguru_logger.remove()
        _real_loguru_logger.add(sys.stderr)

    assert "toolConfig" not in kwargs
    captured = capfd.readouterr()
    assert "deepseek.r1-v1:0" in captured.err
    assert "%s" not in captured.err


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
