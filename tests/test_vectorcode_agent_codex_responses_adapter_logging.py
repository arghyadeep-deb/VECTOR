"""Regression for vectorcode/src/agent/codex_responses_adapter.py: the module
used pure stdlib logging.getLogger(__name__) (no loguru import at all) with
%-style placeholders (%d, %r) -- violates the project's "loguru everywhere"
convention and, more importantly, the two call sites would silently stop
substituting if the logger object were ever swapped to loguru naively
(confirmed this exact failure mode live elsewhere this audit cycle).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import inspect

from agent import codex_responses_adapter


def test_no_stdlib_logging_import():
    src = inspect.getsource(codex_responses_adapter)
    assert "import logging" not in src
    assert "logging.getLogger" not in src


def test_uses_loguru_logger():
    assert codex_responses_adapter.logger.__class__.__module__.startswith("loguru")


def test_no_percent_style_placeholders_remain():
    src = inspect.getsource(codex_responses_adapter)
    assert "%d" not in src
    assert "%r" not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
