"""Regression tests for cleanup after cancelling owned background tasks."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from gateway.platforms.wecom_callback import WecomCallbackAdapter
from gateway.platforms.yuanbao import ConnectionManager


async def test_wecom_callback_disconnect_finishes_cleanup_after_poll_cancel() -> None:
    adapter = WecomCallbackAdapter.__new__(WecomCallbackAdapter)
    adapter._running = True
    adapter._poll_task = asyncio.create_task(asyncio.sleep(60))
    cleaned = False
    disconnected = False

    async def cleanup() -> None:
        nonlocal cleaned
        cleaned = True

    def mark_disconnected() -> None:
        nonlocal disconnected
        disconnected = True

    adapter._cleanup = cleanup
    adapter._mark_disconnected = mark_disconnected

    await adapter.disconnect()

    assert cleaned is True
    assert disconnected is True
    assert adapter._poll_task is None


async def test_yuanbao_connection_close_continues_after_owned_task_cancellation() -> None:
    manager = ConnectionManager.__new__(ConnectionManager)
    manager._heartbeat_task = asyncio.create_task(asyncio.sleep(60))
    manager._recv_task = asyncio.create_task(asyncio.sleep(60))
    manager._pending_acks = {}
    cleaned = False

    async def cleanup_ws() -> None:
        nonlocal cleaned
        cleaned = True

    manager._cleanup_ws = cleanup_ws

    await manager.close()

    assert cleaned is True
    assert manager._heartbeat_task is None
    assert manager._recv_task is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
