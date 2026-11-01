from __future__ import annotations

__all__ = [
    "MicroService",
    "ServiceRegistry",
]


import time
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from core.event_bus.base import EventBus, Subscription
from core.event_bus.types import Event, EventType


class MicroService(ABC):

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        self._name = name
        self._config = config or {}
        self._bus: EventBus | None = None
        self._subscriptions: list[Subscription] = []
        self._started_at: float | None = None
        logger.info("[Service][{}] initialized", self._name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def bus(self) -> EventBus | None:
        return self._bus

    @bus.setter
    def bus(self, value: EventBus) -> None:
        self._bus = value

    async def start(self) -> None:
        self._started_at = time.time()
        logger.info("[Service][{}] started", self._name)
        if self._bus is not None:
            self.register_event_handlers(self._bus)

    async def stop(self) -> None:
        logger.info("[Service][{}] stopping", self._name)
        for sub in self._subscriptions:
            if self._bus is not None:
                self._bus.unsubscribe(sub)
        self._subscriptions.clear()
        self._started_at = None
        logger.info("[Service][{}] stopped", self._name)

    async def health(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "alive": self._started_at is not None,
            "uptime_sec": (time.time() - self._started_at) if self._started_at else 0,
            "subscriptions": len(self._subscriptions),
        }

    def register_event_handlers(self, bus: EventBus) -> None:
        self._bus = bus

    def _subscribe(self, event_type: EventType, handler) -> Subscription:
        if self._bus is None:
            logger.warning("[Service][{}] no bus set, cannot subscribe", self._name)
            raise RuntimeError("EventBus not set on service")
        sub = self._bus.subscribe(event_type, handler)
        self._subscriptions.append(sub)
        return sub


class ServiceRegistry:
    _instance: ServiceRegistry | None = None

    def __new__(cls) -> ServiceRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._services: dict[str, MicroService] = {}
        return cls._instance

    def register(self, service: MicroService) -> None:
        self._services[service.name] = service
        logger.info("[ServiceRegistry] registered {}", service.name)

    def get(self, name: str) -> MicroService | None:
        return self._services.get(name)

    def get_all(self) -> list[MicroService]:
        return list(self._services.values())

    async def start_all(self) -> None:
        for svc in self._services.values():
            await svc.start()

    async def stop_all(self) -> None:
        for svc in self._services.values():
            await svc.stop()

    async def health_all(self) -> dict[str, Any]:
        results = {}
        for name, svc in self._services.items():
            try:
                results[name] = await svc.health()
            except Exception as exc:
                results[name] = {"name": name, "alive": False, "error": str(exc)}
        return results
