"""Regression for vectorcode/src/tools/feishu_doc_tool.py: a stray
`from loguru import logger` sat trapped inside the module docstring (dead
text, never executed), so the file actually used stdlib `logging.getLogger`
with a `%s`-style placeholder -- same bug shape already fixed in
vectorcode/src/tools/url_safety.py this cycle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import vectorcode.src.tools.feishu_doc_tool as feishu_doc_tool


def test_module_docstring_has_no_stray_import():
    assert "from loguru import logger" not in (feishu_doc_tool.__doc__ or "")


def test_logger_is_a_real_loguru_logger():
    # loguru's logger exposes .opt(); stdlib logging.Logger does not.
    assert hasattr(feishu_doc_tool.logger, "opt")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
