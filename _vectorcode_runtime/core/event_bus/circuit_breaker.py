from __future__ import annotations

import time
from enum import Enum
from typing import Any, Callable

from loguru import logger

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
]



class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Prevents cascading failure by stopping delivery to a failing subscriber."""

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._total_failures = 0
        self._total_successes = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and time.time() - self._last_failure_time >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            logger.info("[CB:{}] transitioning OPEN -> HALF_OPEN after {}s timeout", self.name, self.recovery_timeout)
        return self._state

    def call(self, fn: Callable[[], Any]) -> Any:
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")

        try:
            result = fn()
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise

    async def async_call(self, fn: Callable[[], Any]) -> Any:
        import asyncio
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")

        try:
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self._total_successes += 1
        if self._state == CircuitState.HALF_OPEN:
            logger.info("[CB:{}] HALF_OPEN probe succeeded -> CLOSED", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def _on_failure(self) -> None:
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning("[CB:{}] failure threshold {} reached -> OPEN", self.name, self.failure_threshold)

    def get_stats(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
        }

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0


class CircuitBreakerOpenError(Exception):
    pass
