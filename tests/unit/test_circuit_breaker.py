import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
from unittest.mock import patch

import pytest
from loguru import logger

from core.resilience.circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpenError, CircuitBreakerRegistry,
)


@pytest.fixture
def cb():
    config = CircuitBreakerConfig(
        name="test_cb",
        failure_threshold=3,
        recovery_timeout=60.0,
        half_open_max_retries=2,
        success_threshold=2,
    )
    return CircuitBreaker(config)


@pytest.fixture
def registry():
    return CircuitBreakerRegistry()


@pytest.mark.unit
class TestStateTransitions:

    async def test_initial_state_closed(self, cb):
        assert cb.state.value == "closed"

    async def test_closed_to_open_on_failure_threshold(self, cb):
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(3):
            try:
                await cb.call(fail_fn)
            except (ValueError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        assert cb.state.value == "open"
        assert cb.failure_count >= 3

    async def test_does_not_trip_below_threshold(self, cb):
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(2):
            try:
                await cb.call(fail_fn)
            except ValueError:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        assert cb.state.value == "closed"
        assert cb.failure_count == 2

    async def test_open_blocks_calls_before_timeout(self, cb):
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(3):
            try:
                await cb.call(fail_fn)
            except (ValueError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(lambda: "ok")

    async def test_open_to_half_open_after_recovery_timeout(self, cb):
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(3):
            try:
                await cb.call(fail_fn)
            except (ValueError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        assert cb.state.value == "open"
        last_failure = cb.last_failure_time
        with patch("core.resilience.circuit_breaker.time") as mock_time:
            mock_time.time.return_value = last_failure + 120.0
            allowed = await cb._can_proceed()
        assert allowed is True
        assert cb.state.value == "half_open"

    async def test_half_open_to_closed_on_success(self, cb):
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(3):
            try:
                await cb.call(fail_fn)
            except (ValueError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        last_failure = cb.last_failure_time
        with patch("core.resilience.circuit_breaker.time") as mock_time:
            mock_time.time.return_value = last_failure + 120.0
            assert await cb._can_proceed() is True
        assert cb.state.value == "half_open"
        async def success_fn():
            return "ok"
        await cb.call(success_fn)
        await cb.call(success_fn)
        assert cb.state.value == "closed"
        assert cb.failure_count == 0

    async def test_half_open_to_open_on_retry_fail(self, cb):
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(3):
            try:
                await cb.call(fail_fn)
            except (ValueError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        last_failure = cb.last_failure_time
        with patch("core.resilience.circuit_breaker.time") as mock_time:
            mock_time.time.return_value = last_failure + 120.0
            assert await cb._can_proceed() is True
        assert cb.state.value == "half_open"
        for _ in range(3):
            try:
                await cb.call(fail_fn)
            except (ValueError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        assert cb.state.value == "open"

    async def test_success_in_closed_resets_failure_count(self, cb):
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(2):
            try:
                await cb.call(fail_fn)
            except ValueError:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        assert cb.failure_count == 2
        async def success_fn():
            return "ok"
        await cb.call(success_fn)
        assert cb.failure_count == 0


@pytest.mark.unit
class TestForceCommands:

    async def test_force_open(self, cb):
        await cb.force_open()
        assert cb.state.value == "open"

    async def test_force_open_blocks_calls(self, cb):
        async def fail_fn():
            raise ValueError("set last_failure_time")
        try:
            await cb.call(fail_fn)
        except ValueError:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)
        await cb.force_open()
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(lambda: "should not run")

    async def test_force_close(self, cb):
        await cb.force_open()
        await cb.force_close()
        assert cb.state.value == "closed"
        assert cb.failure_count == 0
        assert cb.success_count == 0

    async def test_force_close_resets_counts(self, cb):
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(2):
            try:
                await cb.call(fail_fn)
            except ValueError:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        await cb.force_close()
        assert cb.failure_count == 0
        assert cb.success_count == 0

    async def test_force_close_allows_calls(self, cb):
        await cb.force_open()
        await cb.force_close()
        async def success_fn():
            return "ok"
        result = await cb.call(success_fn)
        assert result == "ok"


@pytest.mark.unit
class TestRegistry:

    async def test_register_creates_new_breaker(self, registry):
        cb = registry.register("my_service")
        assert isinstance(cb, CircuitBreaker)
        assert cb.config.name == "my_service"

    async def test_register_returns_existing(self, registry):
        cb1 = registry.register("svc")
        cb2 = registry.register("svc")
        assert cb1 is cb2

    async def test_get_returns_none_for_missing(self, registry):
        assert registry.get("nonexistent") is None

    async def test_get_returns_breaker(self, registry):
        registry.register("svc")
        assert registry.get("svc") is not None

    async def test_get_all_snapshots(self, registry):
        registry.register("svc_a")
        registry.register("svc_b")
        snaps = registry.get_all_snapshots()
        assert "svc_a" in snaps
        assert "svc_b" in snaps
        for snap in snaps.values():
            assert "state" in snap
            assert "failure_count" in snap
            assert "success_count" in snap

    async def test_open_count(self, registry):
        cb = registry.register("svc")
        await cb.force_open()
        assert registry.open_count == 1

    async def test_open_count_with_service_breaker(self, registry):
        config = CircuitBreakerConfig(name="svc", failure_threshold=3, recovery_timeout=60.0)
        cb = registry.register("svc", config=config)
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(3):
            try:
                await cb.call(fail_fn)
            except (ValueError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        assert cb.state.value == "open"
        assert registry.open_count == 1

    async def test_half_open_count(self, registry):
        config = CircuitBreakerConfig(name="svc", failure_threshold=3, recovery_timeout=60.0)
        cb = registry.register("svc", config=config)
        async def fail_fn():
            raise ValueError("fail")
        for _ in range(3):
            try:
                await cb.call(fail_fn)
            except (ValueError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        last_failure = cb.last_failure_time
        with patch("core.resilience.circuit_breaker.time") as mock_time:
            mock_time.time.return_value = last_failure + 120.0
            assert await cb._can_proceed() is True
        assert registry.half_open_count == 1

    async def test_reset_all(self, registry):
        cb_a = registry.register("svc_a")
        cb_b = registry.register("svc_b")
        await cb_a.force_open()
        await cb_b.force_open()
        await registry.reset_all()
        assert registry.open_count == 0


@pytest.mark.unit
class TestStateSnapshots:

    async def test_snapshot_has_all_keys(self, cb):
        snap = cb.get_state_snapshot()
        for key in ("name", "state", "failure_count", "success_count",
                     "last_failure_time", "last_state_change", "failure_threshold",
                     "recovery_timeout"):
            assert key in snap

    async def test_snapshot_reflects_state(self, cb):
        await cb.force_open()
        snap = cb.get_state_snapshot()
        assert snap["state"] == "open"

    async def test_snapshot_updated_after_success(self, cb):
        async def success_fn():
            return "ok"
        await cb.call(success_fn)
        snap = cb.get_state_snapshot()
        assert snap["failure_count"] == 0
        assert snap["success_count"] == 0


@pytest.mark.unit
class TestSyncFunctions:

    async def test_sync_function_wrapped_in_call(self, cb):
        def sync_fn():
            return 42
        result = await cb.call(sync_fn)
        assert result == 42

    async def test_sync_function_failure_increments_counter(self, cb):
        def sync_fail():
            raise RuntimeError("sync fail")
        for _ in range(3):
            try:
                await cb.call(sync_fail)
            except (RuntimeError, CircuitBreakerOpenError):
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        assert cb.state.value == "open"
