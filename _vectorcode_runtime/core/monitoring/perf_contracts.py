"""
core/monitoring/perf_contracts.py — Timing decorators for critical paths (Gap 7).

Usage:
    from core.monitoring.perf_contracts import timed, CONTRACTS

    @timed("voice_pipeline")
    async def my_voice_fn(): ...

    # Or inline:
    with timed_ctx("ollama_infer"):
        result = ollama.chat(...)

Budgets (seconds):
    voice_pipeline   3.0
    think_tick       15.0
    decision_eval    5.0
    stt_transcribe   2.0
    tts_speak        2.0
    ollama_infer     8.0
    act_on           10.0
    reflect_tick     300.0
"""
import time

__all__ = [
    "all_stats",
    "get_stats",
    "timed",
    "timed_ctx",
]

import asyncio
import functools
from contextlib import contextmanager
from loguru import logger

CONTRACTS: dict[str, float] = {
    "voice_pipeline":  3.0,
    "think_tick":      15.0,
    "decision_eval":   5.0,
    "stt_transcribe":  2.0,
    "tts_speak":       2.0,
    "ollama_infer":    8.0,
    "act_on":          10.0,
    "reflect_tick":    300.0,
}

# Running stats: {name: [elapsed, ...]} (last 100 samples)
_stats: dict[str, list[float]] = {}
_MAX_SAMPLES = 100


def _record(name: str, elapsed: float) -> None:
    bucket = _stats.setdefault(name, [])
    bucket.append(elapsed)
    if len(bucket) > _MAX_SAMPLES:
        bucket.pop(0)
    budget = CONTRACTS.get(name)
    if budget and elapsed > budget:
        logger.warning(
            f"[VECTOR][perf] ⚠ {name} took {elapsed:.2f}s (budget {budget}s, "
            f"over by {elapsed - budget:.2f}s)"
        )
    else:
        logger.debug(f"[VECTOR][perf] {name} {elapsed:.3f}s")


def get_stats(name: str) -> dict:
    """Return p50/p95/max for a named contract."""
    samples = _stats.get(name, [])
    if not samples:
        return {"name": name, "samples": 0}
    s = sorted(samples)
    n = len(s)
    return {
        "name": name,
        "samples": n,
        "p50": s[n // 2],
        "p95": s[int(n * 0.95)],
        "max": s[-1],
        "budget": CONTRACTS.get(name),
        "violations": sum(1 for x in s if CONTRACTS.get(name) and x > CONTRACTS[name]),
    }


def all_stats() -> list[dict]:
    return [get_stats(name) for name in sorted(_stats)]


def timed(name: str):
    """Decorator for sync and async functions."""
    def decorator(fn):
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    _record(name, time.perf_counter() - t0)
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    return fn(*args, **kwargs)
                finally:
                    _record(name, time.perf_counter() - t0)
            return sync_wrapper
    return decorator


@contextmanager
def timed_ctx(name: str):
    """Context manager for inline timing."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _record(name, time.perf_counter() - t0)
