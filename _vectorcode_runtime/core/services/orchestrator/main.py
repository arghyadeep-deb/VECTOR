from __future__ import annotations

__all__ = [
    "create_orchestrator",
    "get_orchestrator",
    "Orchestrator",
    "start_orchestrator",
    "stop_orchestrator",
]


import asyncio
import time
from typing import Any

from loguru import logger

from core.event_bus.bus import get_event_bus, AsyncEventBus
from core.event_bus.types import Event, EventType
from core.event_bus.worker_pool import WorkerPool
from core.services.service_template import MicroService, ServiceRegistry


class Orchestrator(MicroService):

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__("orchestrator", config)
        self._worker_pool: WorkerPool | None = None
        self._background_tasks: list[asyncio.Task] = []
        self._event_count: dict[str, int] = {}

    async def start(self) -> None:
        self._bus = await get_event_bus(
            max_queue_size=self._config.get("max_queue_size", 1000)
        )
        self._worker_pool = WorkerPool(
            max_workers=self._config.get("worker_pool_size", 4),
            name="orchestrator"
        )
        self.register_event_handlers(self._bus)
        await super().start()
        bg_loop = asyncio.create_task(self._background_loop())
        self._background_tasks.append(bg_loop)
        logger.info("[Orchestrator] started with worker_pool={}", self._worker_pool.max_workers)

    async def stop(self) -> None:
        for task in self._background_tasks:
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        if self._worker_pool is not None:
            await self._worker_pool.shutdown(wait=True)
        await super().stop()
        logger.info("[Orchestrator] stopped")

    def register_event_handlers(self, bus: AsyncEventBus) -> None:
        for event_type in EventType:
            self._subscribe(event_type, self._on_any_event)

    async def _on_any_event(self, event: Event) -> None:
        self._event_count[event.event_type.value] = self._event_count.get(event.event_type.value, 0) + 1
        logger.debug("[Orchestrator] routing {} from {}", event.event_type, event.source)

    async def _background_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)
                stats = await self._get_routing_stats()
                logger.debug("[Orchestrator] routing stats: {}", stats)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[Orchestrator] background loop error: {}", exc)

    async def _get_routing_stats(self) -> dict[str, Any]:
        bus_stats = {}
        if self._bus is not None:
            bus_stats = self._bus.get_stats()
        pool_stats = {}
        if self._worker_pool is not None:
            pool_stats = self._worker_pool.get_stats()
        return {
            "events_routed": dict(self._event_count),
            "bus": bus_stats,
            "worker_pool": pool_stats,
        }

    async def health(self) -> dict[str, Any]:
        base = await super().health()
        base["events_processed"] = sum(self._event_count.values())
        base["event_types_seen"] = len(self._event_count)
        return base


_registry = ServiceRegistry()


async def create_orchestrator(config: dict[str, Any] | None = None) -> Orchestrator:
    orch = Orchestrator(config)
    _registry.register(orch)
    return orch


def get_orchestrator() -> Orchestrator | None:
    return _registry.get("orchestrator")


async def start_orchestrator(config: dict[str, Any] | None = None) -> Orchestrator:
    orch = await create_orchestrator(config)
    await orch.start()
    return orch


async def stop_orchestrator() -> None:
    orch = get_orchestrator()
    if orch is not None:
        await orch.stop()
