"""Regression for vectorcode/src/server/cloud_router.py's _stream_google():

the Gemini API key was passed in the request URL's query string
(?key=<api_key>), which is logged by proxies, access logs, and any HTTP
client/request logging -- a header exists as the documented alternative
(x-goog-api-key). Fixed by moving the key to that header and dropping it
from the URL. Also fixed 4 logger.debug(...) calls using %s placeholders
that silently break under loguru's {}-style formatter (loguru was already
correctly imported in this file, just not used consistently).
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from server import cloud_router


def test_gemini_url_no_longer_contains_api_key():
    src = inspect.getsource(cloud_router._stream_google)
    assert "key={api_key}" not in src
    assert "x-goog-api-key" in src


def test_no_broken_percent_style_placeholders_remain():
    src = inspect.getsource(cloud_router)
    assert "suppressed Exception: %s" not in src
    assert src.count("suppressed Exception: {}") == 4


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
