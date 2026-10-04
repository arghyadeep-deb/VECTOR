"""Regression for a batch of loguru-shadowed-by-stdlib-logging and broken
%-style placeholder bugs across several vectorcode/src/server/ files:

- api_routes.py, ws_bridge.py, upload_router.py, app.py: module-level
  `logger = logging.getLogger(__name__)` instead of loguru.
- stream_bridge.py: loguru was already correctly imported at module
  level, but two except-blocks locally shadowed it with a fresh
  `logging.getLogger("vector.server")` (one rebinding the name `logger`
  itself, one under `_logger`), using exc_info=True (a stdlib-only kwarg)
  and %s placeholders.
- app.py: a trace-store init failure was logged as the literal, content-
  free message "[VECTOR] silent swallow" -- replaced with a real
  diagnostic message including the actual exception.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import server.api_routes as api_routes_module
import server.app as app_module
import server.stream_bridge as stream_bridge_module
import server.upload_router as upload_router_module
import server.ws_bridge as ws_bridge_module


def test_api_routes_no_stdlib_logging_or_percent_placeholders():
    src = inspect.getsource(api_routes_module)
    assert "logging.getLogger" not in src
    assert "%s" not in src


def test_ws_bridge_no_stdlib_logging_or_percent_placeholders():
    src = inspect.getsource(ws_bridge_module)
    assert "logging.getLogger" not in src
    assert "%s" not in src


def test_upload_router_no_stdlib_logging_or_percent_placeholders():
    src = inspect.getsource(upload_router_module)
    assert "logging.getLogger" not in src
    assert "%d" not in src
    assert "%s" not in src


def test_app_no_stdlib_logging_or_percent_placeholders():
    src = inspect.getsource(app_module)
    assert "logging.getLogger" not in src
    assert "%s" not in src
    assert "silent swallow" not in src


def test_stream_bridge_no_local_stdlib_logging_shadow():
    src = inspect.getsource(stream_bridge_module)
    assert "logging.getLogger" not in src
    assert "%s" not in src
    assert "exc_info=True" not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
