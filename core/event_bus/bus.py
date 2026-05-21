from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from loguru import logger

from core.event_bus.base import EventBus, Subscription
from core.event_bus.types import Event, EventType


class AsyncEventBus(EventBus):

    def __init__(self, max_queue_size: int = 1000) -> None:
        self._queues: dict[EventType, asyncio.Queue] = {}
        self._subscribers: dict[str, Subscription] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size
        self._events_published = 0
        self._events_delivered = 0
        self._started = False

    async def start(self) -> None:
        self._started = True
        logger.info("[AsyncEventBus] started")

    async def stop(self) -> None:
        self._started = False
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=5.0)
        self._tasks.clear()
        self._subscribers.clear()
        self._queues.clear()
        logger.info("[AsyncEventBus] stopped")

    async def publish(self, event: Event) -> None:
        self._events_published += 1
        async with self._lock:
            matching = [
                sub for sub in self._subscribers.values()
                if sub.event_type is None or sub.event_type == event.event_type
            ]
            for sub in matching:
                queue = self._get_or_create_queue(sub.id, sub.event_type)
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("[AsyncEventBus] queue full for subscriber {} dropping event {}", sub.id[:8], event.event_type)
        logger.debug("[AsyncEventBus] published {} to {} subscriber(s)", event.event_type, len(matching))

    def _get_or_create_queue(self, sub_id: str, event_type: EventType | None) -> asyncio.Queue:
        key = f"{sub_id}:{event_type.value if event_type else '*'}"
        if key not in self._queues:
            self._queues[key] = asyncio.Queue(maxsize=self._max_queue_size)
        return self._queues[key]

    def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]) -> Subscription:
        sub = Subscription(event_type=event_type, handler=handler)
        self._subscribers[sub.id] = sub
        task = asyncio.create_task(self._consumer_loop(sub))
        self._tasks[sub.id] = task
        logger.debug("[AsyncEventBus] subscriber {} registered for {}", sub.id[:8], event_type)
        return sub

    def unsubscribe(self, subscription: Subscription) -> None:
        sub_id = subscription.id
        if sub_id in self._subscribers:
            del self._subscribers[sub_id]
        if sub_id in self._tasks:
            self._tasks[sub_id].cancel()
            del self._tasks[sub_id]
        logger.debug("[AsyncEventBus] subscriber {} unsubscribed", sub_id[:8])

    async def _consumer_loop(self, subscription: Subscription) -> None:
        sub_id = subscription.id
        event_type = subscription.event_type
        handler = subscription.handler
        while self._started:
            try:
                queue = self._get_or_create_queue(sub_id, event_type)
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                try:
                    result = handler(event)
                    if asyncio.iscoroutine(result):
                        await result
                    self._events_delivered += 1
                except Exception as exc:
                    logger.error("[AsyncEventBus] handler error for sub {}: {}", sub_id[:8], exc)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[AsyncEventBus] consumer loop error for sub {}: {}", sub_id[:8], exc)

    def get_stats(self) -> dict[str, Any]:
        return {
            "subscribers": len(self._subscribers),
            "events_published": self._events_published,
            "events_delivered": self._events_delivered,
            "queues": len(self._queues),
        }


_bus_instance: AsyncEventBus | None = None
_bus_lock = asyncio.Lock()


async def get_event_bus(max_queue_size: int = 1000) -> AsyncEventBus:
    global _bus_instance
    async with _bus_lock:
        if _bus_instance is None:
            _bus_instance = AsyncEventBus(max_queue_size=max_queue_size)
            await _bus_instance.start()
        return _bus_instance


async def reset_event_bus() -> None:
    global _bus_instance
    async with _bus_lock:
        if _bus_instance is not None:
            await _bus_instance.stop()
            _bus_instance = None
