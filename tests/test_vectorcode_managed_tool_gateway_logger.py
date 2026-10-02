"""Regression for vectorcode/src/tools/managed_tool_gateway.py: a real
`from loguru import logger` import was immediately shadowed by
`logger = logging.getLogger(__name__)` two lines later -- same bug class
fixed via other variants (trapped-in-docstring / shadowing) in
feishu_doc_tool.py, video_generation_tool.py, and
environments/ssh.py this cycle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import tools.managed_tool_gateway as managed_tool_gateway


def test_logger_is_a_real_loguru_logger_not_shadowed_by_stdlib():
    assert hasattr(managed_tool_gateway.logger, "opt")


def test_no_stdlib_logging_getLogger_call_remains():
    import inspect
    src = inspect.getsource(managed_tool_gateway)
    assert "logging.getLogger" not in src
    assert "%s" not in src
    assert "%d" not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
