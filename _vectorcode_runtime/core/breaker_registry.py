"""Shared singleton registry for circuit breakers, used across all integration call sites."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

_Registry: type | None = None
_CircuitBreakerConfig: type | None = None
_lock = threading.Lock()
_instance: object | None = None


def _lazy_load():
    global _Registry, _CircuitBreakerConfig
    if _Registry is not None:
        return
    from core.resilience.circuit_breaker import (
        CircuitBreakerConfig as _CircuitBreakerConfig,
        CircuitBreakerRegistry as _Registry,
    )


def get_registry():
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is not None:
            return _instance
        _lazy_load()
        reg = _Registry()
        defaults = [
            ("ollama", dict(failure_threshold=3, recovery_timeout=30)),
            ("episodic_memory", dict(failure_threshold=5, recovery_timeout=60)),
            ("district_llm", dict(failure_threshold=3, recovery_timeout=30)),
            ("gemini", dict(failure_threshold=3, recovery_timeout=60)),
            ("anthropic", dict(failure_threshold=3, recovery_timeout=60)),
            ("openrouter", dict(failure_threshold=3, recovery_timeout=60)),
            ("memory_db", dict(failure_threshold=5, recovery_timeout=60)),
            ("vector_db", dict(failure_threshold=5, recovery_timeout=60)),
            ("cloud_api", dict(failure_threshold=3, recovery_timeout=120)),
            ("research_web", dict(failure_threshold=3, recovery_timeout=30)),
            ("tts", dict(failure_threshold=3, recovery_timeout=30)),
            ("asr", dict(failure_threshold=3, recovery_timeout=30)),
        ]
        for name, cfg in defaults:
            reg.register(name, _CircuitBreakerConfig(name=name, **cfg))
        _instance = reg
        return _instance
