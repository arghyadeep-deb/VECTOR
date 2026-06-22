"""Coverage tests for core/resilience/ modules."""

import asyncio
import pytest

from core.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    CircuitState,
)
from core.resilience.graceful_degradation import GracefulDegradation, ServiceTier


async def _fail():
    raise ValueError("fail")


async def _ok(*, val: str = "ok") -> str:
    return val


class TestCircuitBreaker:
    async def test_initial_state_closed(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test", failure_threshold=3, recovery_timeout=0.1))
        assert cb.state == CircuitState.CLOSED

    async def test_trip_on_failures(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test", failure_threshold=3, recovery_timeout=0.1))
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.CLOSED
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.CLOSED
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.OPEN

    async def test_half_open_after_timeout(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test", failure_threshold=1, recovery_timeout=0.05))
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.06)
        result = await cb.call(_ok)
        assert result == "ok"
        assert cb.state == CircuitState.HALF_OPEN

    async def test_reset_on_success(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test", failure_threshold=1, recovery_timeout=0.05, success_threshold=1))
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.06)
        result = await cb.call(_ok)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    async def test_open_raises(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test", failure_threshold=1, recovery_timeout=60))
        with pytest.raises(ValueError):
            await cb.call(_fail)
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(_ok)

    async def test_healthy_passes_through(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test", failure_threshold=3, recovery_timeout=0.1))
        result = await cb.call(_ok, val="hello")
        assert result == "hello"


class TestCircuitBreakerRegistry:
    def test_register_and_get(self):
        registry = CircuitBreakerRegistry()
        cb = registry.register("test", CircuitBreakerConfig(name="test", failure_threshold=3, recovery_timeout=0.1))
        assert registry.get("test") is cb

    def test_get_all_snapshots(self):
        registry = CircuitBreakerRegistry()
        registry.register("cb1", CircuitBreakerConfig(name="cb1", failure_threshold=3, recovery_timeout=0.1))
        registry.register("cb2", CircuitBreakerConfig(name="cb2", failure_threshold=5, recovery_timeout=0.2))
        snapshots = registry.get_all_snapshots()
        assert "cb1" in snapshots
        assert "cb2" in snapshots

    async def test_reset_all(self):
        registry = CircuitBreakerRegistry()
        cb = registry.register("test", CircuitBreakerConfig(name="test", failure_threshold=1, recovery_timeout=60))
        with pytest.raises(ValueError):
            await cb.call(_fail)
        assert cb.state == CircuitState.OPEN
        await registry.reset_all()
        assert cb.state == CircuitState.CLOSED


class TestGracefulDegradation:
    def test_initial_state(self):
        mgr = GracefulDegradation()
        assert mgr.current_tier in set(ServiceTier)

    async def test_auto_degrade(self):
        mgr = GracefulDegradation()
        result = await mgr.auto_degrade()
        assert result is None or isinstance(result, ServiceTier)

    def test_get_service_limits_returns_dict(self):
        mgr = GracefulDegradation()
        limits = mgr.get_service_limits("llm")
        assert isinstance(limits, dict)
        assert "batch_size" in limits
        assert "model_size" in limits
        assert "timeout_sec" in limits

    def test_degraded_limits_lower_than_full(self):
        mgr = GracefulDegradation()
        mgr.current_tier = ServiceTier.FULL
        full = mgr.get_service_limits("llm")
        mgr.current_tier = ServiceTier.MINIMAL
        minimal = mgr.get_service_limits("llm")
        assert minimal["batch_size"] <= full["batch_size"]
