"""VCSEC-5 regressions for asyncio-safe security rate limiting."""
from __future__ import annotations

import asyncio
import inspect

import pytest

from vectorcode.src.vc_security.rate_limiter import RateLimitConfig, RateLimiter


def test_rate_limiter_public_mutations_are_async_and_no_threading_import() -> None:
    import vectorcode.src.vc_security.rate_limiter as module

    assert inspect.iscoroutinefunction(RateLimiter.check)
    assert inspect.iscoroutinefunction(RateLimiter.reset)
    assert "threading" not in inspect.getsource(module)


@pytest.mark.asyncio
async def test_concurrent_checks_cannot_exceed_bucket_capacity(monkeypatch) -> None:
    monkeypatch.setattr("vectorcode.src._rust_bridge.get_rust_module", lambda: None)
    limiter = RateLimiter(RateLimitConfig(requests_per_minute=1, burst_size=3))
    results = await asyncio.gather(*(limiter.check("same-key") for _ in range(20)))
    assert sum(allowed for allowed, _ in results) == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
