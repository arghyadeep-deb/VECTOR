from __future__ import annotations

__all__ = [
    "AsyncEventBus",
    "get_event_bus",
    "reset_event_bus",
]


import asyncio
import time
from collections import deque
from typing import Any, Callable

from loguru import logger

from core.event_bus.base import EventBus, Subscription
from core.event_bus.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from core.event_bus.rate_limiter import RateLimiter
from core.event_bus.types import DirectMessage, Event, EventType


class AsyncEventBus(EventBus):

    def __init__(self, max_queue_size: int = 1000, dlq_maxlen: int = 100) -> None:
        self._queues: dict[EventType, asyncio.Queue] = {}
        self._subscribers: dict[str, Subscription] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._rate_limiters: dict[str, RateLimiter] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._direct_handlers: dict[str, Callable] = {}
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size
        self._events_published = 0
        self._events_delivered = 0
        self._events_dropped = 0
        self._direct_messages_sent = 0
        self._dead_letters: dict[str, deque] = {}
        self._dlq_maxlen = dlq_maxlen
        self._throttle_warning_pct = 0.9
        self._started = False

    async def start(self) -> None:
        self._started = True
        logger.info("[AsyncEventBus] started")

    async def stop(self) -> None:
        self._started = False
        tasks = list(self._tasks.values())
        current_loop = asyncio.get_running_loop()
        waitable_tasks = []
        for task in tasks:
            task_loop = task.get_loop()
            if task.done() or task_loop.is_closed() or task_loop is not current_loop:
                continue
            task.cancel()
            waitable_tasks.append(task)
        if waitable_tasks:
            await asyncio.wait(waitable_tasks, timeout=5.0)
        self._tasks.clear()
        self._subscribers.clear()
        self._queues.clear()
        self._rate_limiters.clear()
        self._circuit_breakers.clear()
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
                qsize = queue.qsize()
                if qsize >= int(self._max_queue_size * self._throttle_warning_pct):
                    logger.warning("[AsyncEventBus] subscriber {} queue at {}% capacity ({}/{}), event_type={}",
                                   sub.id[:8], int(qsize / self._max_queue_size * 100), qsize, self._max_queue_size, event.event_type)
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Push oldest event to DLQ
                    dlq_key = f"{sub.id}:{sub.event_type.value if sub.event_type else '*'}"
                    if dlq_key not in self._dead_letters:
                        self._dead_letters[dlq_key] = deque(maxlen=self._dlq_maxlen)
                    try:
                        dropped = queue.get_nowait()
                        self._dead_letters[dlq_key].append(dropped)
                    except asyncio.QueueEmpty:
                        pass
                    # Retry the new event
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        self._events_dropped += 1
                        logger.warning("[AsyncEventBus] subscriber {} queue full, event {} dropped (total dropped={})",
                                       sub.id[:8], event.event_type, self._events_dropped)
        logger.debug("[AsyncEventBus] published {} to {} subscriber(s)", event.event_type, len(matching))

    def _get_or_create_queue(self, sub_id: str, event_type: EventType | None) -> asyncio.Queue:
        key = f"{sub_id}:{event_type.value if event_type else '*'}"
        if key not in self._queues:
            self._queues[key] = asyncio.Queue(maxsize=self._max_queue_size)
        return self._queues[key]

    def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]) -> Subscription:
        sub = Subscription(event_type=event_type, handler=handler)
        self._subscribers[sub.id] = sub
        self._rate_limiters[sub.id] = RateLimiter(name=sub.id, max_rate=100, time_window=1.0)
        self._circuit_breakers[sub.id] = CircuitBreaker(name=sub.id, failure_threshold=5, recovery_timeout=30.0)
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
        self._rate_limiters.pop(sub_id, None)
        self._circuit_breakers.pop(sub_id, None)
        # The queue created for this subscriber in _get_or_create_queue()
        # (keyed by sub_id, never changes after creation) was never removed
        # here -- every subscribe/unsubscribe cycle (e.g. one per WebSocket
        # connection in core/api/routers/notifications.py+websocket.py)
        # leaked a stale asyncio.Queue entry forever.
        queue_key = f"{sub_id}:{subscription.event_type.value if subscription.event_type else '*'}"
        self._queues.pop(queue_key, None)
        self._dead_letters.pop(queue_key, None)
        logger.debug("[AsyncEventBus] subscriber {} unsubscribed", sub_id[:8])

    async def _consumer_loop(self, subscription: Subscription) -> None:
        sub_id = subscription.id
        event_type = subscription.event_type
        handler = subscription.handler
        while self._started:
            try:
                queue = self._get_or_create_queue(sub_id, event_type)
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                rl = self._rate_limiters.get(sub_id)
                if rl and not rl.allow():
                    logger.debug("[AsyncEventBus] rate limited sub {} skipping event", sub_id[:8])
                    continue
                cb = self._circuit_breakers.get(sub_id)
                if cb:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await cb.async_call(lambda h=handler, e=event: h(e))
                        else:
                            cb.call(lambda h=handler, e=event: h(e))
                        self._events_delivered += 1
                    except CircuitBreakerOpenError:
                        logger.warning("[AsyncEventBus] circuit breaker OPEN for sub {}, dropping event", sub_id[:8])
                else:
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

    def register_direct_handler(self, agent_id: str, handler: Callable) -> None:
        self._direct_handlers[agent_id] = handler
        logger.debug("[AsyncEventBus] direct handler registered for agent {}", agent_id[:8])

    def unregister_direct_handler(self, agent_id: str) -> None:
        self._direct_handlers.pop(agent_id, None)
        logger.debug("[AsyncEventBus] direct handler unregistered for agent {}", agent_id[:8])

    def deliver_direct(self, message: DirectMessage) -> bool:
        handler = self._direct_handlers.get(message.recipient)
        if handler is None:
            logger.warning("[AsyncEventBus] no direct handler for agent {}", message.recipient[:8])
            return False
        try:
            result = handler(message)
            if asyncio.iscoroutine(result):
                # asyncio.ensure_future(result) alone fires-and-forgets --
                # any exception raised inside the coroutine is never
                # retrieved, silently dropped (the classic asyncio "Task
                # exception was never retrieved" gotcha), unlike the sync
                # handler path below which logs via except Exception.
                # Attach a done-callback so an async handler's failure is
                # visible the same way.
                task = asyncio.ensure_future(result)
                recipient = message.recipient

                def _log_if_failed(t: asyncio.Task, recipient: str = recipient) -> None:
                    if t.cancelled():
                        return
                    exc = t.exception()
                    if exc is not None:
                        logger.error("[AsyncEventBus] async direct handler error for agent {}: {}",
                                     recipient[:8], exc)

                task.add_done_callback(_log_if_failed)
            self._direct_messages_sent += 1
            return True
        except Exception as exc:
            logger.error("[AsyncEventBus] direct handler error for agent {}: {}", message.recipient[:8], exc)
            return False

    def get_circuit_breaker(self, sub_id: str) -> CircuitBreaker | None:
        return self._circuit_breakers.get(sub_id)

    def get_rate_limiter(self, sub_id: str) -> RateLimiter | None:
        return self._rate_limiters.get(sub_id)

    def get_stats(self) -> dict[str, Any]:
        return {
            "subscribers": len(self._subscribers),
            "events_published": self._events_published,
            "events_delivered": self._events_delivered,
            "events_dropped": self._events_dropped,
            "queues": len(self._queues),
            "dead_letters": sum(len(dq) for dq in self._dead_letters.values()),
            "queue_depths": {
                k.rsplit(":", 1)[-1]: q.qsize()
                for k, q in self._queues.items()
            },
            "rate_limiters": {
                k[:8]: v.get_stats() for k, v in self._rate_limiters.items()
            },
            "circuit_breakers": {
                k[:8]: v.get_stats() for k, v in self._circuit_breakers.items()
            },
            "direct_handlers": len(self._direct_handlers),
            "direct_messages_sent": self._direct_messages_sent,
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
