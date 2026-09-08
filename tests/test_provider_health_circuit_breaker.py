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
    """AUTH disables at the (provider, model) level — a 401 on one model
    must not kill sibling models on the same provider. reset() targets
    the same (provider, model) key that record_failure() added."""
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        await mgr.record_failure("openai", "gpt-4", kind=FailureKind.AUTH, error="401")
        # The auth failure only disabled (openai, gpt-4) — sibling models work
        sibling_ok = await mgr.can_try("openai", "gpt-4o")
        # The failed model is blocked
        failed_blocked = not await mgr.can_try("openai", "gpt-4")
        # Reset the specific model that was disabled
        mgr.reset("openai", "gpt-4")
        after_reset = await mgr.can_try("openai", "gpt-4")
        return sibling_ok, failed_blocked, after_reset

    sibling_ok, failed_blocked, after_reset = asyncio.run(_run())
    assert sibling_ok is True
    assert failed_blocked is True
    assert after_reset is True


def test_auth_failure_does_not_kill_sibling_models():
    """Regression: AUTH failure on one model must NOT disable every model
    on the provider. Previously target_model was forced to '*' which put
    (provider, '*') in _disabled, and can_try() checked that key first —
    one expired key blocked all 50+ models. Fixed 2026-08-12."""
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        # Single expired key on gpt-4
        await mgr.record_failure("openai", "gpt-4", kind=FailureKind.AUTH, error="401 unauthorized")
        # 50+ sibling models must still be tryable
        results = {}
        for model in ("gpt-4o", "gpt-4-turbo", "o3", "o4-mini"):
            results[model] = await mgr.can_try("openai", model)
        # The failed model itself must be blocked
        results["gpt-4"] = await mgr.can_try("openai", "gpt-4")
        return results

    results = asyncio.run(_run())
    for model in ("gpt-4o", "gpt-4-turbo", "o3", "o4-mini"):
        assert results[model] is True, f"{model} should not be blocked by gpt-4's auth failure"
    assert results["gpt-4"] is False, "the model with the auth failure must remain blocked"


def test_bad_request_does_not_trip_circuit():
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        for _ in range(5):  # well past failure_threshold=3
            await mgr.record_failure("openai", "gpt-4", kind=FailureKind.BAD_REQUEST, error="400")
        return await mgr.can_try("openai", "gpt-4")

    assert asyncio.run(_run()) is True


def test_unknown_model_permanently_disables_that_model_only():
    """2026-07-23 (JARVIS-parity latency pass): a provider saying it doesn't
    recognize a specific model (e.g. github_models rejecting openai/gpt-5
    with 'unknown_model' — a real, live, reproduced-every-time case, not
    hypothetical) is a permanent, content-independent mismatch, unlike a
    generic BAD_REQUEST which might just be this one request's fault.
    Confirms: (a) it disables immediately regardless of failure_threshold,
    (b) it survives a cooldown wait (like AUTH), (c) unlike AUTH it's scoped
    to just that model — a sibling model on the same provider is untouched."""
    from core.inference.provider_health import FailureKind

    mgr = _fresh_manager()

    async def _run():
        await mgr.record_failure(
            "github_models", "openai/gpt-5", kind=FailureKind.UNKNOWN_MODEL,
            error='{"error":{"code":"unknown_model","message":"Unknown model: openai/gpt-5"}}',
        )
        immediate = await mgr.can_try("github_models", "openai/gpt-5")
        await asyncio.sleep(0.5)  # well past any cooldown
        later = await mgr.can_try("github_models", "openai/gpt-5")
        sibling = await mgr.can_try("github_models", "Codestral-25.01")
        return immediate, later, sibling

    immediate, later, sibling = asyncio.run(_run())
    assert immediate is False
    assert later is False
    assert sibling is True


def test_classify_error_detects_unknown_model_before_generic_bad_request():
    mgr = _fresh_manager()
    from core.inference.provider_health import FailureKind

    assert mgr.classify_error(
        '{"error":{"code":"unknown_model","message":"Unknown model: openai/gpt-5"}}'
    ) == FailureKind.UNKNOWN_MODEL
    assert mgr.classify_error("Model not found") == FailureKind.UNKNOWN_MODEL
    # A generic 400 with no model-not-found signature still classifies as
    # plain BAD_REQUEST (does NOT permanently disable) — confirms the new
    # check doesn't swallow unrelated 400s.
    assert mgr.classify_error("400 Bad Request: missing required field") == FailureKind.BAD_REQUEST


def test_classify_error_maps_common_strings():
    mgr = _fresh_manager()
    from core.inference.provider_health import FailureKind

    assert mgr.classify_error("401 Unauthorized") == FailureKind.AUTH
    assert mgr.classify_error("429 Too Many Requests") == FailureKind.RATE_LIMIT
    assert mgr.classify_error("503 Service Unavailable") == FailureKind.SERVER_ERROR
    assert mgr.classify_error("Connection timeout") == FailureKind.NETWORK
    assert mgr.classify_error("400 Bad Request") == FailureKind.BAD_REQUEST
    assert mgr.classify_error("something weird") == FailureKind.UNKNOWN


def test_classify_error_status_codes_dont_match_inside_numbers():
    """Regression: substring '400' in classify_error() matched inside model
    names (gpt-oss-1200b → '1**400**b'), token counts ('processed 400
    tokens'), URLs, etc. A 500 error mentioning '400' would be misclassified
    as BAD_REQUEST — which does NOT trip the circuit (sets HEALTHY), so
    genuine server failures got silently retried forever without backoff.
    Fixed with word-boundary regex matching."""
    mgr = _fresh_manager()
    from core.inference.provider_health import FailureKind

    # Model names containing '400' must NOT be classified as BAD_REQUEST
    assert mgr.classify_error("model gpt-oss-1200b not available") != FailureKind.BAD_REQUEST
    assert mgr.classify_error("model-4001 unknown") != FailureKind.BAD_REQUEST

    # Token counts containing '400' must NOT be classified as BAD_REQUEST
    assert mgr.classify_error("processed 400 tokens successfully") != FailureKind.BAD_REQUEST

    # A 500 error that mentions '400 tokens' must be SERVER_ERROR, not BAD_REQUEST
    assert mgr.classify_error("500 Internal Server Error after processing 400 tokens") == FailureKind.SERVER_ERROR

    # Port numbers / request IDs containing '400' must NOT match
    assert mgr.classify_error("connection refused on port 8400") != FailureKind.BAD_REQUEST
    assert mgr.classify_error("request_id abc400def failed") != FailureKind.BAD_REQUEST

    # Legitimate 400 status codes MUST still be classified as BAD_REQUEST
    assert mgr.classify_error("HTTP 400 Bad Request") == FailureKind.BAD_REQUEST
    assert mgr.classify_error("status code: 400") == FailureKind.BAD_REQUEST
    assert mgr.classify_error("returned 400: invalid request") == FailureKind.BAD_REQUEST

    # Same word-boundary fix applies to other status codes
    assert mgr.classify_error("model-4010 auth") != FailureKind.AUTH  # '401' inside '4010'
    assert mgr.classify_error("request-4291") != FailureKind.RATE_LIMIT  # '429' inside '4291'
    assert mgr.classify_error("HTTP 401 Unauthorized") == FailureKind.AUTH
    assert mgr.classify_error("429 rate limit exceeded") == FailureKind.RATE_LIMIT
    assert mgr.classify_error("502 Bad Gateway") == FailureKind.SERVER_ERROR


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
