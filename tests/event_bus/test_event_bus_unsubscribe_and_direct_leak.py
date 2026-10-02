"""Regression for two bugs found in core/event_bus/bus.py during the Phase 3
whole-repo audit (2026-10-02):

1. unsubscribe() removed the subscriber/task/rate-limiter/circuit-breaker
   but never removed the queue entry it created in _get_or_create_queue()
   -- every subscribe/unsubscribe cycle (one per WebSocket connection in
   core/api/routers/notifications.py + websocket.py) leaked a stale
   asyncio.Queue entry in self._queues forever.

2. deliver_direct()'s async-handler path called asyncio.ensure_future(result)
   with no done-callback -- any exception raised inside that coroutine was
   silently dropped (asyncio's "Task exception was never retrieved" gotcha),
   unlike the sync handler path a few lines below which logs via
   except Exception.
"""
import asyncio
from unittest.mock import patch

import pytest

from core.event_bus.types import Event, EventType, DirectMessage
from core.event_bus.bus import AsyncEventBus


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue_entry():
    bus = AsyncEventBus()
    await bus.start()
    sub = bus.subscribe(EventType.TASK_SCHEDULED, lambda e: None)
    # _get_or_create_queue() is called lazily inside the consumer task's
    # first loop iteration, not by subscribe() itself -- yield once so the
    # scheduled task actually runs and creates its queue entry.
    await asyncio.sleep(0)
    assert len(bus._queues) == 1
    bus.unsubscribe(sub)
    assert len(bus._queues) == 0
    await bus.stop()


@pytest.mark.asyncio
async def test_repeated_subscribe_unsubscribe_does_not_accumulate_queues():
    bus = AsyncEventBus()
    await bus.start()
    for _ in range(10):
        sub = bus.subscribe(EventType.TASK_SCHEDULED, lambda e: None)
        await asyncio.sleep(0)
        bus.unsubscribe(sub)
    assert len(bus._queues) == 0
    await bus.stop()


@pytest.mark.asyncio
async def test_deliver_direct_async_handler_exception_is_logged():
    bus = AsyncEventBus()
    await bus.start()

    async def failing_handler(message):
        raise RuntimeError("boom")

    bus.register_direct_handler("agent-1", failing_handler)
    with patch("core.event_bus.bus.logger") as mock_logger:
        ok = bus.deliver_direct(DirectMessage(recipient="agent-1", sender="agent-0"))
        assert ok is True  # fire-and-forget still returns True immediately
        # Let the scheduled task run and its done-callback fire.
        await asyncio.sleep(0.05)
    error_calls = [c for c in mock_logger.error.call_args_list
                   if "async direct handler error" in c.args[0]]
    assert len(error_calls) == 1
    assert error_calls[0].args[2].args == ("boom",) or "boom" in str(error_calls[0].args[2])
    await bus.stop()


@pytest.mark.asyncio
async def test_deliver_direct_async_handler_success_not_logged_as_error():
    bus = AsyncEventBus()
    await bus.start()

    async def ok_handler(message):
        return "fine"

    bus.register_direct_handler("agent-2", ok_handler)
    with patch("core.event_bus.bus.logger") as mock_logger:
        bus.deliver_direct(DirectMessage(recipient="agent-2", sender="agent-0"))
        await asyncio.sleep(0.05)
    error_calls = [c for c in mock_logger.error.call_args_list
                   if "async direct handler error" in c.args[0]]
    assert len(error_calls) == 0
    await bus.stop()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
