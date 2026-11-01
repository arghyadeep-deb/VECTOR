from __future__ import annotations

__all__ = [
    "EventBus",
    "Subscription",
]


import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from core.event_bus.types import Event, EventType


@dataclass
class Subscription:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    event_type: EventType | None = None
    handler: Callable[[Event], Any] | None = None
    created_at: float = field(default_factory=time.time)


class EventBus(ABC):

    @abstractmethod
    async def publish(self, event: Event) -> None:
        ...

    @abstractmethod
    def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]) -> Subscription:
        ...

    @abstractmethod
    def unsubscribe(self, subscription: Subscription) -> None:
        ...

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        ...
