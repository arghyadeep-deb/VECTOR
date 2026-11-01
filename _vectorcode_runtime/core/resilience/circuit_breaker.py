"""3-state circuit breaker with configurable thresholds and auto-recovery."""

from __future__ import annotations

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitBreakerRegistry",
    "CircuitState",
]


import asyncio
import time
from enum import Enum
from typing import Any, Callable

from loguru import logger


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerConfig:
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_retries: int = 3,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_retries = half_open_max_retries
        self.success_threshold = success_threshold


class CircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig | None = None):
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
        self._half_open_retries = 0
        self._lock = asyncio.Lock()

    async def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        if not await self.can_proceed():
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.config.name}' is {self.state.value}"
            )
        try:
            result = await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)
            await self.on_success()
            return result
        except Exception as e:
            await self.on_failure()
            raise

    async def can_proceed(self) -> bool:
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                    logger.info("[CircuitBreaker] {} transitioning OPEN → HALF_OPEN", self.config.name)
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self._half_open_retries = 0
                    self.last_state_change = time.time()
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                if self._half_open_retries < self.config.half_open_max_retries:
                    self._half_open_retries += 1
                    return True
                return False
            return False

    def would_allow(self) -> bool:
        """Pure-read check — returns whether a call *would* be allowed right
        now WITHOUT mutating state (no OPEN→HALF_OPEN transition, no
        _half_open_retries increment).  Use this for pre-flight gating where
        the caller will consume exactly one slot separately via can_proceed()."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            return time.time() - self.last_failure_time >= self.config.recovery_timeout
        if self.state == CircuitState.HALF_OPEN:
            return self._half_open_retries < self.config.half_open_max_retries
        return False

    async def _can_proceed(self) -> bool:
        """Backward-compatible alias for older tests/callers."""
        return await self.can_proceed()

    async def on_success(self) -> None:
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    logger.info("[CircuitBreaker] {} recovered: HALF_OPEN → CLOSED", self.config.name)
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.last_state_change = time.time()
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    async def on_failure(self) -> None:
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
                logger.warning("[CircuitBreaker] {} tripped: CLOSED → OPEN ({} failures)", self.config.name, self.failure_count)
                self.state = CircuitState.OPEN
                self.last_state_change = time.time()
            elif self.state == CircuitState.HALF_OPEN:
                logger.warning("[CircuitBreaker] {} half-open retry failed: HALF_OPEN → OPEN", self.config.name)
                self.state = CircuitState.OPEN
                self.last_state_change = time.time()

    async def force_open(self) -> None:
        async with self._lock:
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()
            self.last_failure_time = time.time()  # prevent immediate OPEN→HALF_OPEN transition
            logger.info("[CircuitBreaker] {} manually forced OPEN", self.config.name)

    async def force_close(self) -> None:
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_state_change = time.time()
            logger.info("[CircuitBreaker] {} manually forced CLOSED", self.config.name)

    def get_state_snapshot(self) -> dict[str, Any]:
        return {
            "name": self.config.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_state_change": self.last_state_change,
            "failure_threshold": self.config.failure_threshold,
            "recovery_timeout": self.config.recovery_timeout,
        }


class CircuitBreakerOpenError(Exception):
    """Raised when a circuit breaker prevents a call from proceeding."""


class CircuitBreakerRegistry:
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def register(self, name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
        if name in self._breakers:
            return self._breakers[name]
        cb = CircuitBreaker(config or CircuitBreakerConfig(name=name))
        self._breakers[name] = cb
        return cb

    def get(self, name: str) -> CircuitBreaker | None:
        return self._breakers.get(name)

    def get_all_snapshots(self) -> dict[str, dict[str, Any]]:
        return {name: cb.get_state_snapshot() for name, cb in self._breakers.items()}

    async def reset_all(self) -> None:
        for cb in self._breakers.values():
            await cb.force_close()

    @property
    def open_count(self) -> int:
        return sum(1 for cb in self._breakers.values() if cb.state == CircuitState.OPEN)

    @property
    def half_open_count(self) -> int:
        return sum(1 for cb in self._breakers.values() if cb.state == CircuitState.HALF_OPEN)
