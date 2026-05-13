"""Gateway delivery — message routing, hooks, event system."""

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class DeliveryRouter:
    def __init__(self):
        self._routes: dict[str, list[Callable]] = {}

    def route(self, channel: str, handler: Callable):
        self._routes.setdefault(channel, []).append(handler)

    async def deliver(self, channel: str, message: str, **kwargs):
        for handler in self._routes.get(channel, []):
            try: await handler(message, **kwargs)
            except Exception as e: logger.warning(f"Delivery to {channel} failed: {e}")


class EventHooks:
    def __init__(self):
        self._hooks: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable):
        self._hooks.setdefault(event, []).append(handler)

    async def fire(self, event: str, **kwargs):
        for handler in self._hooks.get(event, []):
            try: await handler(**kwargs)
            except Exception as e: logger.warning(f"Hook {event} failed: {e}")
