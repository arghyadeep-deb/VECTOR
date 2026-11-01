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

import re
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
        failure_threshold: int | None = None,
        base_cooldown_seconds: int | None = None,
        rate_limit_cooldown_seconds: int | None = None,
    ) -> None:
        # Read from CONFIG if not explicitly provided (use 'is None' to allow 0)
        ph_cfg = __import__("core.config", fromlist=["CONFIG"]).CONFIG.get("provider_health", {})
        self.failure_threshold = failure_threshold if failure_threshold is not None else ph_cfg.get("failure_threshold", 3)
        self.base_cooldown_seconds = base_cooldown_seconds if base_cooldown_seconds is not None else ph_cfg.get("base_cooldown_seconds", 60)
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds if rate_limit_cooldown_seconds is not None else ph_cfg.get("rate_limit_cooldown_seconds", 600)
        self._registry = get_registry()
        self._meta: dict[tuple[str, str], ProviderRouteState] = {}
        # AUTH failures permanently disable a route until manual reset —
        # a state CircuitBreaker doesn't model (it only knows OPEN-with-
        # a-timeout), so it's tracked here as an explicit override.
        self._disabled: set[tuple[str, str]] = set()
        self._lock = __import__("threading").Lock()  # protects _meta + _disabled

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
        with self._lock:
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
        # Pure-read check on BOTH breakers — would_allow() does NOT mutate
        # state (no OPEN→HALF_OPEN transition, no _half_open_retries bump).
        # Previously this called can_proceed() on both breakers, which
        # consumed 2 of the 3 half-open retry slots per single can_try()
        # call, causing the breaker to re-lock to OPEN after 1-2 probes
        # instead of the intended 3.
        provider_cb = self._breaker(*provider_key)
        model_cb = self._breaker(*model_key)
        if not provider_cb.would_allow() or not model_cb.would_allow():
            return False
        # Both breakers would allow — consume exactly ONE retry slot on
        # the model-level breaker (the one that receives the matching
        # record_success/record_failure for this attempt).  When model=="*"
        # the two keys are identical so only one slot is consumed either way.
        return await model_cb.can_proceed()

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
        target_model = model or "*"
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
            # 2026-07-23 (responsiveness latency pass): distinct from generic
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
        """Manual override — clears a permanent AUTH/UNKNOWN_MODEL disable.
        Must target the same (provider, model) key that record_failure() added."""
        self._disabled.discard(self._key(provider, model))

    @staticmethod
    def _has_status_code(text: str, code: str) -> bool:
        """Check for a numeric HTTP status code with word boundaries.

        Plain substring ``"400" in text`` matches inside model names
        (``gpt-oss-1200b`` → "1**400**b"), token counts ("processed 400
        tokens"), URLs/ports, etc. A 500 error whose message happens to
        mention "400" would be misclassified as BAD_REQUEST — which does
        NOT trip the circuit breaker (line 192-196 sets HEALTHY), so
        genuine server failures get silently retried forever without
        backoff. Word-boundary matching prevents all of these.
        """
        return bool(re.search(rf"\b{code}\b", text))

    def classify_error(self, error: BaseException | str) -> FailureKind:
        text = str(error).lower()
        if (any(token in text for token in ("unauthorized", "invalid api key", "forbidden"))
                or any(self._has_status_code(text, c) for c in ("401", "403"))):
            return FailureKind.AUTH
        if (any(token in text for token in ("rate limit", "quota exceeded", "too many requests"))
                or self._has_status_code(text, "429")):
            return FailureKind.RATE_LIMIT
        if (any(token in text for token in ("server error", "bad gateway"))
                or any(self._has_status_code(text, c) for c in ("500", "502", "503", "504"))):
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
        if (any(token in text for token in ("bad request", "invalid request", "context length"))
                or self._has_status_code(text, "400")):
            # But if text explicitly says success, it's not an error at all
            if any(token in text for token in ("success", "successfully")):
                return FailureKind.UNKNOWN
            return FailureKind.BAD_REQUEST
        return FailureKind.UNKNOWN

    def snapshot(self) -> list[dict]:
        result = []
        with self._lock:
            items = list(self._meta.items())
            disabled = set(self._disabled)
        for key, meta in items:
            cb = self._breaker(*key)
            health = RouteHealth.DISABLED if key in disabled else _STATE_TO_HEALTH[cb.state]
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
_health_lock = __import__("threading").Lock()


def get_provider_health() -> ProviderHealthManager:
    global _health
    if _health is None:
        with _health_lock:
            if _health is None:
                _health = ProviderHealthManager()
    return _health
