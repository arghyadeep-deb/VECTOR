"""Regression for vectorcode/src/server/channel_bridge.py: stdlib
logging.getLogger(__name__) used instead of loguru, with %s placeholders
that silently break under loguru's {}-formatter.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import server.channel_bridge as channel_bridge_module


def test_module_uses_loguru_not_stdlib_logging():
    src = inspect.getsource(channel_bridge_module)
    assert "import logging" not in src
    assert "%s" not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
