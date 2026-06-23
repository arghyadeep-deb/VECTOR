"""
Closes a real duplication found on user-prompted re-audit: core/inference/
provider_health.py reimplemented a 3-state circuit-breaker state machine
from scratch (HEALTHY/COOLDOWN/HALF_OPEN/DISABLED, consecutive-failure
counting, cooldown timers) — introduced by this session's OmniRoute
absorption with exactly 1 real caller (provider_client.py) — duplicating
core/resilience/circuit_breaker.py, which already existed a month prior
with 8 production callers and (unlike the original provider_health.py)
proper async locking.

Fixed: ProviderHealthManager is now a thin layer on top of the real,
shared CircuitBreaker/CircuitBreakerRegistry (core.breaker_registry) for
the actual state machine, keeping only the genuinely-new capabilities on
top: failure-kind classification, differentiated cooldowns per kind,
permanent auth-disable, and latency tracking.

can_try/record_success/record_failure are now async (delegating to the
CircuitBreaker's async, lock-protected methods) -- a real correctness
improvement, since the original had no locking at all despite being
called from concurrent async chat() calls.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _fresh_manager():
    """A manager with its own private registry so tests don't share
    breaker state with the real process-wide singleton."""
    from core.inference.provider_health import ProviderHealthManager
    from core.resilience.circuit_breaker import CircuitBreakerRegistry

    mgr = ProviderHealthManager(failure_threshold=3, base_cooldown_seconds=0.1, rate_limit_cooldown_seconds=0.3)
    mgr._registry = CircuitBreakerRegistry()
    return mgr


def test_can_try_true_initially():
    mgr = _fresh_manager()
    assert asyncio.run(mgr.can_try("openai", "gpt-4")) is True


def test_record_failure_below_threshold_keeps_can_try_true():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        await mgr.record_failure("openai", "gpt-4", kind=FailureKind.SERVER_ERROR, error="500")
        await mgr.record_failure("openai", "gpt-4", kind=FailureKind.SERVER_ERROR, error="500")
        return await mgr.can_try("openai", "gpt-4")

    assert asyncio.run(_run()) is True


def test_record_failure_at_threshold_trips_circuit():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        for _ in range(3):
            await mgr.record_failure("openai", "gpt-4", kind=FailureKind.SERVER_ERROR, error="500")
        return await mgr.can_try("openai", "gpt-4")

    assert asyncio.run(_run()) is False


def test_circuit_recovers_to_half_open_after_cooldown():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        for _ in range(3):
            await mgr.record_failure("openai", "gpt-4", kind=FailureKind.SERVER_ERROR, error="500")
        assert await mgr.can_try("openai", "gpt-4") is False
        await asyncio.sleep(0.15)  # base_cooldown_seconds=0.1
        return await mgr.can_try("openai", "gpt-4")

    assert asyncio.run(_run()) is True


def test_record_success_closes_circuit():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        for _ in range(3):
            await mgr.record_failure("openai", "gpt-4", kind=FailureKind.SERVER_ERROR, error="500")
        await asyncio.sleep(0.15)
        await mgr.can_try("openai", "gpt-4")  # transitions OPEN -> HALF_OPEN
        await mgr.record_success("openai", "gpt-4", latency_ms=120)
        meta = mgr.state("openai", "gpt-4")
        return meta

    meta = asyncio.run(_run())
    assert meta.consecutive_failures == 0
    assert meta.rolling_latency_ms == 120


def test_rate_limit_uses_longer_cooldown_than_base():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        for _ in range(3):
            await mgr.record_failure("openai", "gpt-4", kind=FailureKind.RATE_LIMIT, error="429")
        assert await mgr.can_try("openai", "gpt-4") is False
        await asyncio.sleep(0.15)  # past base_cooldown (0.1) but not rate_limit_cooldown (0.3)
        return await mgr.can_try("openai", "gpt-4")

    assert asyncio.run(_run()) is False


def test_auth_failure_permanently_disables_regardless_of_wait():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        await mgr.record_failure("openai", "gpt-4", kind=FailureKind.AUTH, error="401 unauthorized")
        immediate = await mgr.can_try("openai", "gpt-4")
        await asyncio.sleep(0.5)  # well past any cooldown
        later = await mgr.can_try("openai", "gpt-4")
        return immediate, later

    immediate, later = asyncio.run(_run())
    assert immediate is False
    assert later is False


def test_auth_disable_can_be_manually_reset():
    """AUTH disables at the provider level ("*"), matching the original
    semantics: target_model becomes "*" for AUTH failures regardless of
    which model triggered it (an invalid API key blocks the whole
    provider, not just one model) -- so reset() must target that same
    provider-level key."""
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        await mgr.record_failure("openai", "gpt-4", kind=FailureKind.AUTH, error="401")
        mgr.reset("openai", "*")
        return await mgr.can_try("openai", "gpt-4")

    assert asyncio.run(_run()) is True


def test_bad_request_does_not_trip_circuit():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        for _ in range(5):  # well past failure_threshold=3
            await mgr.record_failure("openai", "gpt-4", kind=FailureKind.BAD_REQUEST, error="400")
        return await mgr.can_try("openai", "gpt-4")

    assert asyncio.run(_run()) is True


def test_classify_error_maps_common_strings():
    mgr = _fresh_manager()
    from core.inference.provider_health import FailureKind

    assert mgr.classify_error("401 Unauthorized") == FailureKind.AUTH
    assert mgr.classify_error("429 Too Many Requests") == FailureKind.RATE_LIMIT
    assert mgr.classify_error("503 Service Unavailable") == FailureKind.SERVER_ERROR
    assert mgr.classify_error("Connection timeout") == FailureKind.NETWORK
    assert mgr.classify_error("400 Bad Request") == FailureKind.BAD_REQUEST
    assert mgr.classify_error("something weird") == FailureKind.UNKNOWN


def test_snapshot_returns_expected_shape():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        await mgr.record_success("anthropic", "claude-3", latency_ms=80)
        await mgr.record_failure("anthropic", "claude-3", kind=FailureKind.NETWORK, error="dns failure")

    asyncio.run(_run())
    snap = mgr.snapshot()
    assert len(snap) == 1
    row = snap[0]
    assert row["provider"] == "anthropic"
    assert row["model"] == "claude-3"
    assert row["successes"] == 1
    assert row["failures"] == 1
    assert row["last_failure_kind"] == "network"


def test_uses_real_circuit_breaker_registry_under_the_hood():
    """Confirms the de-duplication: the breaker for a provider:model pair
    is a genuine core.resilience.circuit_breaker.CircuitBreaker instance,
    not a parallel reimplementation."""
    from core.inference.provider_health import ProviderHealthManager
    from core.resilience.circuit_breaker import CircuitBreaker

    mgr = _fresh_manager()
    cb = mgr._breaker("openai", "gpt-4")
    assert isinstance(cb, CircuitBreaker)


def test_provider_client_call_sites_await_async_api():
    """provider_client.py's 3 real call sites must use await -- a static
    check that the integration was updated, not just the manager itself."""
    import inspect
    from core.inference import provider_client

    src = inspect.getsource(provider_client)
    assert "await _health.can_try(" in src
    assert "await _health.record_success(" in src
    assert "await _health.record_failure(" in src


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
