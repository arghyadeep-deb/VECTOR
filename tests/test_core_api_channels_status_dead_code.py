"""Regression for core/api/routers/channels.py's /channels/status endpoint.

Found while verifying a channels/ vs. vectorcode/src/channels/ duplication
question: channels_status()'s FIRST attempt at listing active channels
imported `vectorcode.src.channels.channel_directory.ChannelDirectory` --
that module path doesn't exist (the real file is
vectorcode/src/gateway/channel_directory.py, module-level functions only,
no ChannelDirectory class) -- confirmed it raised ModuleNotFoundError on
every single call, silently caught by a bare `except Exception` using the
same "[VECTOR] suppressed exception (fallback degraded)" + exc_info=True
placeholder pattern fixed 70+ times elsewhere this cycle (and a no-op
under this file's own loguru logger).

Removed the always-broken first attempt (it never once succeeded, so
removing it changes nothing about real runtime behavior) and fixed the
logging. FLAGGED, not fixed: the remaining ChannelRuntime fallback also
has no real active-channel-listing capability (confirmed:
core.engine.channels.runtime.ChannelRuntime only has submit_sync()/stop(),
no active_channels() method) -- the hasattr() guard degrades this
gracefully instead of raising, but this endpoint has always reported
active_channels=[]/status="inactive" regardless of real channel state.
A real fix needs an owner call on the actual intended data source.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers.channels import channels_status


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_channels_status_does_not_raise():
    result = _run(channels_status())
    assert result is not None


def test_channels_status_currently_always_reports_inactive():
    # Honest regression lock on current (broken) behavior -- this SHOULD
    # start failing the moment a real data source is wired in, which is
    # the point: it documents the gap rather than hiding it.
    result = _run(channels_status())
    assert result.active_channels == []
    assert result.status == "inactive"


def test_no_import_of_nonexistent_channel_directory_module():
    import inspect
    from core.api.routers import channels as mod
    src = inspect.getsource(mod)
    assert "from vectorcode.src.channels.channel_directory import" not in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
