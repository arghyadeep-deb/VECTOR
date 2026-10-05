"""Regression for vectorcode/src/agent/copilot_acp_client.py's three
suppressed-exception log calls: each used a stdlib %-style placeholder
(logger.debug(..., "%s", _sve)) under loguru, which silently does not
substitute %-style args -- the suppressed exception text was never
actually visible in the log line, only the literal "%s".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import inspect

from agent import copilot_acp_client


def test_no_percent_s_placeholders_remain():
    src = inspect.getsource(copilot_acp_client)
    assert "%s" not in src, "stdlib %-style placeholder found under loguru"


def test_suppressed_exception_messages_use_brace_placeholder():
    src = inspect.getsource(copilot_acp_client)
    assert src.count('suppressed Exception: {}') == 3


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
