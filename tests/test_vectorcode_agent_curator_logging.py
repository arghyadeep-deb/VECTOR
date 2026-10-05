"""Regression for vectorcode/src/agent/curator.py's logging:

Unlike bedrock_adapter.py/anthropic_adapter.py/model_metadata.py, this
module's `from loguru import logger` was a real, correctly-placed top-level
import -- but 17 logger.debug(...) calls still used stdlib %-style
placeholders (silently fail to substitute under loguru's {}-formatter), and
12 calls passed stdlib's exc_info=True kwarg, which loguru's .debug()
silently ignores (use logger.opt(exception=True) instead).
"""
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from agent import curator


def test_no_percent_style_placeholders_in_logger_calls():
    src = inspect.getsource(curator)
    for m in re.finditer(r"logger\.\w+\(([\s\S]*?)\)(?=\n)", src, re.MULTILINE):
        call_text = m.group(0)
        assert not re.search(r"%[sdr]|%\.\d*f", call_text), (
            f"found a %-style placeholder in a logger call: {call_text!r}"
        )


def test_no_exc_info_kwarg_on_bare_logger_calls():
    """exc_info=True on a bare logger.<level>(...) call is a loguru no-op --
    must go through logger.opt(exception=True) instead."""
    src = inspect.getsource(curator)
    assert "exc_info=True" not in src


def test_threading_usage_is_flagged_with_a_comment():
    """The one threading.Thread call site must carry an explicit FLAGGED
    comment explaining why it isn't converted to asyncio (whole module is
    synchronous), per this audit's convention for deliberate exceptions."""
    src = inspect.getsource(curator)
    idx = src.index("threading.Thread(target=_llm_pass")
    preceding = src[max(0, idx - 700):idx]
    assert "FLAGGED, not fixed" in preceding


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
