"""Provider health for VECTOR inference — built on the real, already-wired
core.resilience.circuit_breaker.CircuitBreaker (async-locked, 8 production
callers across the codebase) rather than reimplementing a parallel state
machine.

This module's job is the genuinely-new layer on top: per-(provider, model)
granularity, failure-kind classification (rate limit vs auth vs server
error vs network vs bad request), differentiated cooldown durations per
kind, permanent provider-disable on auth failure (a state CircuitBreaker
itself doesn't model — it only knows OPEN-with-a-timeout), and latency
tracking. The CLOSED/OPEN/HALF_OPEN state machine and its locking are
delegated entirely to CircuitBreaker.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from core.breaker_registry import get_registry
from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

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
    UNKNOWN_MODEL = "unknown_model"
    UNKNOWN = "unknown"


_STATE_TO_HEALTH = {
    CircuitState.CLOSED: RouteHealth.HEALTHY,
    CircuitState.OPEN: RouteHealth.COOLDOWN,
    CircuitState.HALF_OPEN: RouteHealth.HALF_OPEN,
}


@dataclass
class ProviderRouteState:
    """Observability snapshot — lifetime counters CircuitBreaker doesn't
    track itself (it only tracks consecutive failures for its own
    transition logic), plus the mapped health enum for API compatibility."""
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
        self._registry = get_registry()
        self._meta: dict[tuple[str, str], ProviderRouteState] = {}
        # AUTH failures permanently disable a route until manual reset —
        # a state CircuitBreaker doesn't model (it only knows OPEN-with-
        # a-timeout), so it's tracked here as an explicit override.
        self._disabled: set[tuple[str, str]] = set()

    def _key(self, provider: str, model: str = "*") -> tuple[str, str]:
        return (provider, model or "*")

    def _breaker(self, provider: str, model: str = "*") -> CircuitBreaker:
        provider, model = self._key(provider, model)
        name = f"provider_health:{provider}:{model}"
        cb = self._registry.get(name)
        if cb is None:
            cb = self._registry.register(
                name,
                CircuitBreakerConfig(
                    name=name,
                    failure_threshold=self.failure_threshold,
                    recovery_timeout=self.base_cooldown_seconds,
                ),
            )
        return cb

    def _route_meta(self, provider: str, model: str = "*") -> ProviderRouteState:
        key = self._key(provider, model)
        if key not in self._meta:
            self._meta[key] = ProviderRouteState(provider=key[0], model=key[1])
        return self._meta[key]

    def state(self, provider: str, model: str = "*") -> ProviderRouteState:
        """Read-only snapshot combining the real breaker's state with
        this manager's own lifetime counters."""
        key = self._key(provider, model)
        meta = self._route_meta(*key)
        cb = self._breaker(*key)
        meta.health = RouteHealth.DISABLED if key in self._disabled else _STATE_TO_HEALTH[cb.state]
        if cb.state == CircuitState.OPEN:
            meta.next_retry_at = cb.last_failure_time + cb.config.recovery_timeout
        return meta

    async def can_try(self, provider: str, model: str = "*") -> bool:
        provider_key = self._key(provider, "*")
        model_key = self._key(provider, model)
        if provider_key in self._disabled or model_key in self._disabled:
            return False
        provider_ok = await self._breaker(*provider_key).can_proceed()
        model_ok = await self._breaker(*model_key).can_proceed()
        return provider_ok and model_ok

    async def record_success(self, provider: str, model: str = "*", latency_ms: float = 0.0) -> ProviderRouteState:
        key = self._key(provider, model)
        await self._breaker(*key).on_success()
        meta = self._route_meta(*key)
        meta.successes += 1
        meta.consecutive_failures = 0
        meta.health = RouteHealth.HEALTHY
        meta.next_retry_at = 0.0
        meta.updated_at = time.time()
        if latency_ms > 0:
            meta.rolling_latency_ms = (
                latency_ms if meta.rolling_latency_ms <= 0 else meta.rolling_latency_ms * 0.8 + latency_ms * 0.2
            )
        return meta

    async def record_failure(
        self,
        provider: str,
        model: str = "*",
        kind: FailureKind = FailureKind.UNKNOWN,
        error: str = "",
    ) -> ProviderRouteState:
        target_model = "*" if kind == FailureKind.AUTH else (model or "*")
        key = self._key(provider, target_model)
        meta = self._route_meta(*key)
        meta.failures += 1
        meta.consecutive_failures += 1
        meta.last_failure_kind = kind
        meta.last_error = error[:300]
        meta.updated_at = time.time()

        if kind == FailureKind.AUTH:
            self._disabled.add(key)
            meta.health = RouteHealth.DISABLED
            return meta
        if kind == FailureKind.UNKNOWN_MODEL:
            # 2026-07-23 (JARVIS-parity latency pass): distinct from generic
            # BAD_REQUEST below. A provider saying "I don't recognize this
            # model" (e.g. github_models rejecting openai/gpt-5, openai/o3,
            # openai/o4-mini with "unknown_model" — a known, permanent
            # mismatch documented in model_catalog.yaml's own comment,
            # "gpt-5/o3/o4-mini return 400 (kept; fallback covers)") is NOT
            # content-dependent — the identical (provider, model) pair will
            # 400 again on every future call regardless of what's asked, so
            # unlike a genuinely malformed one-off request, retrying it is
            # pure wasted latency (confirmed live: these fired on nearly
            # every "coding"/"saas"/"reasoning"/"council" tier call, each
            # costing a full round trip before falling through to the next
            # provider). Permanently disable just this (provider, model)
            # pair — sibling models on the same provider (Codestral,
            # DeepSeek-R1, etc.) are unaffected since disabling is scoped to
            # `key`, not the provider as a whole. `reset()` still works if
            # ever needed to force a retry (e.g. after the owner confirms a
            # provider added support for the model).
            self._disabled.add(key)
            meta.health = RouteHealth.DISABLED
            return meta
        if kind == FailureKind.BAD_REQUEST:
            # Caller's fault (malformed request), not the provider's —
            # must not trip the circuit.
            meta.health = RouteHealth.HEALTHY
            return meta

        cb = self._breaker(*key)
        cb.config.recovery_timeout = (
            self.rate_limit_cooldown_seconds if kind == FailureKind.RATE_LIMIT else self.base_cooldown_seconds
        )
        await cb.on_failure()
        meta.health = _STATE_TO_HEALTH[cb.state]
        if cb.state == CircuitState.OPEN:
            meta.next_retry_at = cb.last_failure_time + cb.config.recovery_timeout
        return meta

    def reset(self, provider: str, model: str = "*") -> None:
        """Manual override — clears a permanent AUTH disable."""
        self._disabled.discard(self._key(provider, model))

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
        # Checked before the generic BAD_REQUEST bucket below: "this model
        # doesn't exist / isn't available on this provider" is a permanent,
        # content-independent mismatch (see the UNKNOWN_MODEL branch in
        # record_failure() for the full rationale and the live evidence).
        if any(token in text for token in (
            "unknown_model", "unknown model", "model not found",
            "model_not_found",
        )):
            return FailureKind.UNKNOWN_MODEL
        if any(token in text for token in ("400", "bad request", "invalid request", "context length")):
            return FailureKind.BAD_REQUEST
        return FailureKind.UNKNOWN

    def snapshot(self) -> list[dict]:
        result = []
        for key, meta in self._meta.items():
            cb = self._breaker(*key)
            health = RouteHealth.DISABLED if key in self._disabled else _STATE_TO_HEALTH[cb.state]
            result.append({
                "provider": meta.provider,
                "model": meta.model,
                "health": health.value,
                "successes": meta.successes,
                "failures": meta.failures,
                "consecutive_failures": meta.consecutive_failures,
                "last_failure_kind": meta.last_failure_kind.value if meta.last_failure_kind else None,
                "next_retry_at": meta.next_retry_at,
                "rolling_latency_ms": round(meta.rolling_latency_ms, 2),
            })
        return result


_health: ProviderHealthManager | None = None


def get_provider_health() -> ProviderHealthManager:
    global _health
    if _health is None:
        _health = ProviderHealthManager()
    return _health
