"""Regression for vectorcode/src/server/routes.py: three exception handlers
used logging.getLogger("vector.server") directly (stdlib) instead of the
module's own loguru logger, with exc_info=True/%s placeholders that are
either stdlib-only or silently broken under loguru's {}-formatter.
Converted all three to logger.opt(exception=...).
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import server.routes as routes_module


def test_module_does_not_use_stdlib_logging_directly():
    src = inspect.getsource(routes_module)
    assert "logging.getLogger" not in src
    assert "import logging" not in src
    assert "%s" not in src


def test_module_uses_loguru_opt_exception_for_exc_info_sites():
    src = inspect.getsource(routes_module)
    assert src.count("logger.opt(exception=") >= 3


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
