"""Regression test for the 2026-09-24 external review's Phase 1 finding:
db_guardian.py's security-quarantine alert and content_arm.py's
"reel ready to post" notification imported modules that never existed, so
the owner-facing notification silently never sent (the surrounding except
swallowed the ImportError). Verifies the real send path is reached, not
just that the import resolves.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.mark.asyncio
async def test_core_notify_pushover_sends_via_httpx_when_configured():
    from core.notify import pushover

    with patch("core.notify.CONFIG", {"api_keys": {"pushover_token": "t", "pushover_user": "u"}}), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=AsyncMock(status_code=200))
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        await pushover("test message", priority=1)

    assert mock_client.post.await_count == 1
    call_kwargs = mock_client.post.await_args
    assert call_kwargs.args[0] == "https://api.pushover.net/1/messages.json"
    assert call_kwargs.kwargs["data"]["message"] == "test message"


@pytest.mark.asyncio
async def test_core_notify_pushover_noop_when_unconfigured():
    from core.notify import pushover

    with patch("core.notify.CONFIG", {"api_keys": {}}), \
         patch("httpx.AsyncClient") as mock_client_cls:
        await pushover("should not send")
    mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_cloud_notify_owner_delegates_to_core_notify_pushover():
    from core.cloud.notify import notify_owner

    with patch("core.cloud.notify.pushover", new=AsyncMock()) as mock_pushover:
        await notify_owner("db quarantine alert", priority=2)
    mock_pushover.assert_awaited_once_with("db quarantine alert", priority=2)


@pytest.mark.asyncio
async def test_db_guardian_alert_owner_reaches_real_notify_path():
    """The original bug: _alert_owner imported a nonexistent module and the
    except swallowed it -- notify_owner() was never actually called."""
    from core.memory.db_guardian import _alert_owner

    with patch("core.cloud.notify.notify_owner", new=AsyncMock()) as mock_notify:
        await _alert_owner("test quarantine alert")
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_content_arm_notify_owner_to_post_awaits_pushover():
    """The original bug: pushover() was called without await (a coroutine
    was created and immediately discarded, never executed)."""
    from districts.growth.content_arm import ContentArm

    arm = ContentArm.__new__(ContentArm)  # bypass __init__, method doesn't need agent state
    with patch("core.notify.pushover", new=AsyncMock()) as mock_pushover:
        await arm._notify_owner_to_post("test_reel.mp4")
    mock_pushover.assert_awaited_once()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
