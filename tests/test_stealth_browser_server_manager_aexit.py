"""Regression for core/stealth_browser/server_manager.py's StealthBrowserServer.

__aexit__ unconditionally raised NotImplementedError("...must be implemented
by subclass") -- but the class's own module docstring documents direct use
as an async context manager (`async with StealthBrowserServer() as srv:`),
not via a subclass, and no subclass exists anywhere in the repo (confirmed
via grep). Following the documented usage would have crashed on exit.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.stealth_browser.server_manager import StealthBrowserServer


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_aexit_does_not_raise():
    server = StealthBrowserServer()
    result = _run(server.__aexit__(None, None, None))
    assert result is False


def test_aexit_does_not_suppress_a_real_exception():
    server = StealthBrowserServer()

    async def _raise_inside_with():
        async with _NoStartStealthBrowserServer() as srv:
            assert srv is not None
            raise ValueError("boom")

    class _NoStartStealthBrowserServer(StealthBrowserServer):
        async def __aenter__(self):
            return self  # skip the real ensure_running() subprocess start

    try:
        _run(_raise_inside_with())
        assert False, "expected ValueError to propagate"
    except ValueError as e:
        assert str(e) == "boom"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
