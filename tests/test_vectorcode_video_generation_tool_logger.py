"""Regression for vectorcode/src/tools/video_generation_tool.py: a real
`from loguru import logger` import was immediately shadowed by
`logger = logging.getLogger(__name__)` two lines later, so every logger
call in the file actually used stdlib logging with %s-style placeholders
under loguru's own formatter (same systemic bug class fixed 55+ times this
cycle, here via a shadowing import rather than a trapped-in-docstring one).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import tools.video_generation_tool as video_generation_tool


def test_logger_is_a_real_loguru_logger_not_shadowed_by_stdlib():
    assert hasattr(video_generation_tool.logger, "opt")


def test_no_stdlib_logging_getLogger_call_remains():
    import inspect
    src = inspect.getsource(video_generation_tool)
    assert "logging.getLogger" not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
