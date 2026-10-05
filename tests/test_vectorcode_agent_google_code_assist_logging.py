"""Regression for vectorcode/src/agent/google_code_assist.py:

1. The module correctly did `from loguru import logger` at the top, then
   immediately shadowed it a few lines later with
   `logger = logging.getLogger(__name__)` -- the classic shadow-import bug
   found repeatedly across vectorcode/src/ this audit cycle. Every %-style
   placeholder below it silently fails to substitute under loguru's
   {}-formatter once that shadow is removed, so this fix also converts all
   five affected call sites.

2. A wrong-variable bug: the HTTPError-detail-read except block caught its
   own exception as `_sve` but logged the OUTER exception `exc` instead --
   so if exc.read() itself failed, the debug log never showed why.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import inspect

from agent import google_code_assist


def test_no_stdlib_logging_import():
    src = inspect.getsource(google_code_assist)
    assert "import logging" not in src
    assert "logging.getLogger" not in src


def test_no_percent_style_placeholders_remain():
    src = inspect.getsource(google_code_assist)
    assert "%s" not in src
    assert "%d" not in src


def test_http_error_detail_read_failure_logs_the_actual_caught_exception():
    src = inspect.getsource(google_code_assist._post_json)
    assert 'suppressed Exception: {}", _sve)' in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
