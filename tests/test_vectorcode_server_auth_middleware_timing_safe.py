"""Regression for vectorcode/src/server/auth_middleware.py's AuthMiddleware.dispatch():

the bearer-token check used a plain `!=` to compare the caller-supplied
token against the real API key -- a timing side-channel on a real
credential comparison. Fixed with secrets.compare_digest(). Also fixed
the module's stdlib logging.getLogger() (should be loguru per CLAUDE.md)
and a %s placeholder that would have silently broken under loguru's
{}-style formatter.
"""
import asyncio
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from server.auth_middleware import AuthMiddleware


def test_dispatch_uses_constant_time_compare_not_bare_noteq():
    src = inspect.getsource(AuthMiddleware.dispatch)
    assert "secrets.compare_digest" in src
    assert "token != self._api_key" not in src


def _make_middleware(api_key: str) -> AuthMiddleware:
    async def _app(scope, receive, send):
        pass

    return AuthMiddleware(_app, api_key=api_key)


class _FakeRequest:
    def __init__(self, path: str, auth_header: str):
        self.url = type("U", (), {"path": path})()
        self._auth_header = auth_header

    @property
    def headers(self):
        return {"Authorization": self._auth_header} if self._auth_header else {}


def test_valid_bearer_token_passes_through():
    mw = _make_middleware("secret-key-123")
    req = _FakeRequest("/v1/do-thing", "Bearer secret-key-123")

    called = {"next": False}

    async def call_next(_req):
        called["next"] = True
        return "ok"

    result = asyncio.run(mw.dispatch(req, call_next))
    assert called["next"] is True
    assert result == "ok"


def test_wrong_bearer_token_rejected():
    mw = _make_middleware("secret-key-123")
    req = _FakeRequest("/v1/do-thing", "Bearer wrong-key")

    async def call_next(_req):
        raise AssertionError("should not reach the real handler")

    result = asyncio.run(mw.dispatch(req, call_next))
    assert result.status_code == 401


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
