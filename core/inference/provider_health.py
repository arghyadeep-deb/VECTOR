"""Provider health and circuit-breaker state for VECTOR inference."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "FailureKind",
    "ProviderHealthManager",
    "ProviderRouteState",
    "RouteHealth",
    "get_provider_health",
]


class RouteHealth(str, Enum):
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    HALF_OPEN = "half_open"
    DISABLED = "disabled"


class FailureKind(str, Enum):
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    SERVER_ERROR = "server_error"
    NETWORK = "network"
    BAD_REQUEST = "bad_request"
    UNKNOWN = "unknown"


@dataclass
class ProviderRouteState:
    provider: str
    model: str = "*"
    health: RouteHealth = RouteHealth.HEALTHY
    consecutive_failures: int = 0
    successes: int = 0
    failures: int = 0
    last_failure_kind: FailureKind | None = None
    last_error: str = ""
    next_retry_at: float = 0.0
    rolling_latency_ms: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def can_try(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if self.health == RouteHealth.DISABLED:
            return False
        if self.health == RouteHealth.COOLDOWN and now < self.next_retry_at:
            return False
        if self.health == RouteHealth.COOLDOWN and now >= self.next_retry_at:
            self.health = RouteHealth.HALF_OPEN
        return True


class ProviderHealthManager:
    def __init__(
        self,
        failure_threshold: int = 3,
        base_cooldown_seconds: int = 60,
        rate_limit_cooldown_seconds: int = 600,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.base_cooldown_seconds = base_cooldown_seconds
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._states: dict[tuple[str, str], ProviderRouteState] = {}

    def state(self, provider: str, model: str = "*") -> ProviderRouteState:
        key = (provider, model or "*")
        if key not in self._states:
            self._states[key] = ProviderRouteState(provider=provider, model=model or "*")
        return self._states[key]

    def can_try(self, provider: str, model: str = "*") -> bool:
        provider_state = self.state(provider, "*")
        model_state = self.state(provider, model)
        return provider_state.can_try() and model_state.can_try()

    def record_success(self, provider: str, model: str = "*", latency_ms: float = 0.0) -> ProviderRouteState:
        state = self.state(provider, model)
        state.successes += 1
        state.consecutive_failures = 0
        state.health = RouteHealth.HEALTHY
        state.next_retry_at = 0.0
        state.updated_at = time.time()
        if latency_ms > 0:
            state.rolling_latency_ms = (
                latency_ms if state.rolling_latency_ms <= 0 else state.rolling_latency_ms * 0.8 + latency_ms * 0.2
            )
        return state

    def record_failure(
        self,
        provider: str,
        model: str = "*",
        kind: FailureKind = FailureKind.UNKNOWN,
        error: str = "",
    ) -> ProviderRouteState:
        target = "*" if kind == FailureKind.AUTH else (model or "*")
        state = self.state(provider, target)
        state.failures += 1
        state.consecutive_failures += 1
        state.last_failure_kind = kind
        state.last_error = error[:300]
        state.updated_at = time.time()
        if kind == FailureKind.AUTH:
            state.health = RouteHealth.DISABLED
        elif kind == FailureKind.BAD_REQUEST:
            state.health = RouteHealth.HEALTHY
        elif kind == FailureKind.RATE_LIMIT or state.consecutive_failures >= self.failure_threshold:
            state.health = RouteHealth.COOLDOWN
            cooldown = self.rate_limit_cooldown_seconds if kind == FailureKind.RATE_LIMIT else self.base_cooldown_seconds
            state.next_retry_at = time.time() + cooldown
        return state

    def classify_error(self, error: BaseException | str) -> FailureKind:
        text = str(error).lower()
        if any(token in text for token in ("401", "403", "unauthorized", "invalid api key", "forbidden")):
            return FailureKind.AUTH
        if any(token in text for token in ("429", "rate limit", "quota exceeded", "too many requests")):
            return FailureKind.RATE_LIMIT
        if any(token in text for token in ("500", "502", "503", "504", "server error", "bad gateway")):
            return FailureKind.SERVER_ERROR
        if any(token in text for token in ("timeout", "connection", "network", "dns", "temporarily unavailable")):
            return FailureKind.NETWORK
        if any(token in text for token in ("400", "bad request", "invalid request", "context length")):
            return FailureKind.BAD_REQUEST
        return FailureKind.UNKNOWN

    def snapshot(self) -> list[dict]:
        return [
            {
                "provider": state.provider,
                "model": state.model,
                "health": state.health.value,
                "successes": state.successes,
                "failures": state.failures,
                "consecutive_failures": state.consecutive_failures,
                "last_failure_kind": state.last_failure_kind.value if state.last_failure_kind else None,
                "next_retry_at": state.next_retry_at,
                "rolling_latency_ms": round(state.rolling_latency_ms, 2),
            }
            for state in self._states.values()
        ]


_health: ProviderHealthManager | None = None


def get_provider_health() -> ProviderHealthManager:
    global _health
    if _health is None:
        _health = ProviderHealthManager()
    return _health
