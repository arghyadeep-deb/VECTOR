"""Semaphore-based service pool isolation — one failing service can't starve others."""

from __future__ import annotations

__all__ = [
    "BulkheadConfig",
    "BulkheadExecutor",
    "BulkheadRegistry",
    "BulkheadRejectedError",
]


import asyncio
import time
from typing import Any, Callable



class BulkheadConfig:
    def __init__(
        self,
        name: str = "default",
        max_concurrent: int = 4,
        max_queue: int = 10,
        queue_timeout: float = 30.0,
    ):
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self.queue_timeout = queue_timeout


class BulkheadExecutor:
    def __init__(self, config: BulkheadConfig | None = None):
        self.config = config or BulkheadConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self._current_count = 0
        self._queue_count = 0
        self._total_processed = 0
        self._total_rejected = 0
        self._total_errors = 0
        self._lock = asyncio.Lock()

    async def execute(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            # Only reject when semaphore is saturated AND the waiting queue is full.
            # Checking both atomically prevents rejecting the very first call when max_queue=0.
            slots_full = self._current_count >= self.config.max_concurrent
            if slots_full and self._queue_count >= self.config.max_queue:
                self._total_rejected += 1
                raise BulkheadRejectedError(f"Bulkhead '{self.config.name}' queue full ({self.config.max_queue})")
            self._queue_count += 1

        try:
            async with self._semaphore:
                async with self._lock:
                    self._queue_count -= 1
                    self._current_count += 1

                try:
                    if asyncio.iscoroutinefunction(fn):
                        result = await fn(*args, **kwargs)
                    else:
                        result = fn(*args, **kwargs)
                    async with self._lock:
                        self._total_processed += 1
                    return result
                except Exception:
                    async with self._lock:
                        self._total_errors += 1
                    raise
                finally:
                    async with self._lock:
                        self._current_count -= 1
        finally:
            pass

    async def get_stats(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "name": self.config.name,
                "max_concurrent": self.config.max_concurrent,
                "max_queue": self.config.max_queue,
                "current_concurrent": self._current_count,
                "queue_depth": self._queue_count,
                "total_processed": self._total_processed,
                "total_rejected": self._total_rejected,
                "total_errors": self._total_errors,
                "utilization_pct": (self._current_count / self.config.max_concurrent * 100) if self.config.max_concurrent else 0,
            }


class BulkheadRejectedError(Exception):
    """Raised when a bulkhead rejects a call due to capacity limits."""


class BulkheadRegistry:
    def __init__(self):
        self._executors: dict[str, BulkheadExecutor] = {}

    def register(self, name: str, config: BulkheadConfig | None = None) -> BulkheadExecutor:
        if name in self._executors:
            return self._executors[name]
        bh = BulkheadExecutor(config or BulkheadConfig(name=name))
        self._executors[name] = bh
        return bh

    def get(self, name: str) -> BulkheadExecutor | None:
        return self._executors.get(name)

    async def get_all_stats(self) -> dict[str, Any]:
        results = {}
        for name, bh in self._executors.items():
            results[name] = await bh.get_stats()
        return results
