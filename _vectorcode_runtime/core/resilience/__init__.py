"""ResilienceLayer — facade wrapping circuit breakers, bulkheads, failover, degradation, and chaos."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from loguru import logger

from core.config import CONFIG
from core.resilience.bulkhead_executor import BulkheadConfig, BulkheadExecutor, BulkheadRegistry
from core.resilience.chaos_monkey import ChaosMonkey
from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerRegistry
from core.resilience.graceful_degradation import GracefulDegradation, ServiceTier
from core.resilience.hot_failover import HotFailover
from core.resilience.metrics import ResilienceMetrics
from core.resilience.recovery_playbooks import run_all_playbooks


class ResilienceLayer:
    def __init__(self):
        config = CONFIG.get("resilience", {})
        self.circuit_breakers = CircuitBreakerRegistry()
        self.bulkheads = BulkheadRegistry()
        self.degradation = GracefulDegradation()
        self.failover = HotFailover(is_primary=True)
        self.chaos = ChaosMonkey()
        self.metrics = ResilienceMetrics()
        self._enabled = config.get("enabled", True)
        self._monitor_task: asyncio.Task | None = None

        self._setup_defaults()

        logger.info("[ResilienceLayer] initialized (enabled={})", self._enabled)

    def _setup_defaults(self) -> None:
        self.circuit_breakers.register("ollama", CircuitBreakerConfig(name="ollama", failure_threshold=3, recovery_timeout=30))
        self.circuit_breakers.register("memory_db", CircuitBreakerConfig(name="memory_db", failure_threshold=5, recovery_timeout=60))
        self.circuit_breakers.register("vector_db", CircuitBreakerConfig(name="vector_db", failure_threshold=5, recovery_timeout=60))
        self.circuit_breakers.register("cloud_api", CircuitBreakerConfig(name="cloud_api", failure_threshold=3, recovery_timeout=120))
        self.circuit_breakers.register("research_web", CircuitBreakerConfig(name="research_web", failure_threshold=3, recovery_timeout=30))
        self.circuit_breakers.register("tts", CircuitBreakerConfig(name="tts", failure_threshold=3, recovery_timeout=30))
        self.circuit_breakers.register("asr", CircuitBreakerConfig(name="asr", failure_threshold=3, recovery_timeout=30))

        self.bulkheads.register("voice", BulkheadConfig(name="voice", max_concurrent=2, max_queue=5))
        self.bulkheads.register("inference", BulkheadConfig(name="inference", max_concurrent=4, max_queue=10))
        self.bulkheads.register("research", BulkheadConfig(name="research", max_concurrent=2, max_queue=10))
        self.bulkheads.register("memory", BulkheadConfig(name="memory", max_concurrent=4, max_queue=20))
        self.bulkheads.register("comms", BulkheadConfig(name="comms", max_concurrent=2, max_queue=5))

    async def wrap_call(self, breaker_name: str, bulkhead_name: str | None, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        if not self._enabled:
            return await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)

        async def _call() -> Any:
            cb = self.circuit_breakers.get(breaker_name)
            if cb:
                return await cb.call(fn, *args, **kwargs)
            return await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)

        if bulkhead_name:
            bh = self.bulkheads.get(bulkhead_name)
            if bh:
                return await bh.execute(_call)
        return await _call()

    async def run_monitor_cycle(self) -> None:
        cb_snapshots = self.circuit_breakers.get_all_snapshots()
        bh_stats = await self.bulkheads.get_all_stats()
        self.metrics.record_circuit_breaker(cb_snapshots)
        self.metrics.record_bulkheads(bh_stats)

        tier = await self.degradation.auto_degrade()
        if tier is not None:
            self.metrics.record_degradation({"new_tier": tier.name, "timestamp": __import__("time").time()})

        tier_up = await self.degradation.auto_escalate()
        if tier_up is not None:
            self.metrics.record_degradation({"new_tier": tier_up.name, "timestamp": __import__("time").time()})

    async def start_monitor(self, interval_sec: float = 30.0) -> None:
        async def _loop():
            while True:
                try:
                    await self.run_monitor_cycle()
                except Exception as e:
                    logger.debug("[ResilienceLayer] monitor cycle error: {}", e)
                await asyncio.sleep(interval_sec)

        self._monitor_task = asyncio.create_task(_loop())
        logger.info("[ResilienceLayer] monitor started (interval={}s)", interval_sec)

    async def stop_monitor(self) -> None:
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None

    def get_health(self) -> dict[str, Any]:
        return self.metrics.get_health_summary()
