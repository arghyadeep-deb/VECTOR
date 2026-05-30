
import asyncio
import time

import pytest

from core.event_bus.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState
from core.event_bus.rate_limiter import RateLimiter
from core.event_bus.types import Event, EventType
from core.event_bus.bus import AsyncEventBus


# ---------------------------------------------------------------------------
#  Rate Limiter unit tests
# ---------------------------------------------------------------------------

class TestRateLimiter:

    def test_allows_up_to_max_rate(self):
        rl = RateLimiter(name="test", max_rate=5, time_window=1.0)
        allowed = sum(1 for _ in range(10) if rl.allow())
        assert allowed == 5

    def test_denies_beyond_max_rate(self):
        rl = RateLimiter(name="test", max_rate=3, time_window=1.0)
        for _ in range(3):
            assert rl.allow()
        assert not rl.allow()

    def test_refills_tokens_over_time(self):
        rl = RateLimiter(name="test", max_rate=10, time_window=1.0)
        for _ in range(10):
            rl.allow()
        assert not rl.allow()
        time.sleep(0.11)
        assert rl.allow()

    def test_get_stats(self):
        rl = RateLimiter(name="test", max_rate=50, time_window=1.0)
        rl.allow()
        rl.allow()
        stats = rl.get_stats()
        assert stats["max_rate"] == 50
        assert stats["total_allowed"] == 2
        assert stats["total_denied"] == 0


# ---------------------------------------------------------------------------
#  Circuit Breaker unit tests
# ---------------------------------------------------------------------------

class TestCircuitBreaker:

    def test_starts_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.get_stats()["state"] == "closed"

    def test_transitions_to_open_after_failures(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=30.0)
        def fail():
            raise ValueError("boom")
        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(fail)
        assert cb.state == CircuitState.OPEN

    def test_raises_open_error_when_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=30.0)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "ok")

    def test_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN
        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_goes_to_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN
        time.sleep(0.06)
        cb.call(lambda: "ok")
        assert cb.state == CircuitState.CLOSED
        assert cb.get_stats()["total_successes"] >= 1

    def test_half_open_failure_goes_to_open(self):
        call_count = 0
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.05)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN
        time.sleep(0.06)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail again")))
        assert cb.state == CircuitState.OPEN

    def test_async_call(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=30.0)
        results = []

        async def good():
            results.append("ok")
            return "ok"

        async def bad():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerOpenError):
            asyncio.run(cb.async_call(good))
        cb.reset()
        result = asyncio.run(cb.async_call(good))
        assert result == "ok"

    def test_get_stats(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, recovery_timeout=30.0)
        stats = cb.get_stats()
        assert stats["state"] == "closed"
        assert stats["failure_threshold"] == 3
        assert stats["failure_count"] == 0

    def test_reset(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=30.0)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.get_stats()["failure_count"] == 0


# ---------------------------------------------------------------------------
#  Event bus integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def bus():
    b = AsyncEventBus(max_queue_size=100)
    await b.start()
    yield b
    await b.stop()


@pytest.mark.asyncio
class TestEventBusCircuitBreakerIntegration:

    async def test_failing_handler_trips_circuit_breaker(self, bus):
        call_count = 0

        async def failing_handler(event):
            nonlocal call_count
            call_count += 1
            raise ValueError("simulated failure")

        sub = bus.subscribe(EventType.HEALTH_ALERT, failing_handler)
        cb = bus.get_circuit_breaker(sub.id)
        assert cb is not None
        assert cb.state == CircuitState.CLOSED

        for i in range(5):
            await bus.publish(Event(event_type=EventType.HEALTH_ALERT, data={"i": i}))
        await asyncio.sleep(0.3)

        assert cb.state == CircuitState.OPEN

    async def test_circuit_breaker_stops_delivery_when_open(self, bus):
        call_count = 0

        async def failing_handler(event):
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        sub = bus.subscribe(EventType.HEALTH_ALERT, failing_handler)
        cb = bus.get_circuit_breaker(sub.id)

        for i in range(10):
            await bus.publish(Event(event_type=EventType.HEALTH_ALERT, data={"i": i}))
        await asyncio.sleep(0.3)

        assert cb.state == CircuitState.OPEN
        assert call_count == 5


@pytest.mark.asyncio
class TestEventBusRateLimiterIntegration:

    async def test_rate_limiter_skips_events_when_over_limit(self, bus):
        rl = RateLimiter(name="test_integration", max_rate=100, time_window=1.0)
        received = []

        async def handler(event):
            received.append(event)

        sub = bus.subscribe(EventType.CONFIG_CHANGED, handler)
        bus._rate_limiters[sub.id] = rl

        for i in range(200):
            await bus.publish(Event(event_type=EventType.CONFIG_CHANGED, data={"i": i}))
        await asyncio.sleep(0.3)

        assert len(received) <= 100


@pytest.mark.asyncio
class TestEventBusStatsIntegration:

    async def test_stats_include_rate_limiter_and_circuit_breaker(self, bus):
        async def handler(event):
            pass

        bus.subscribe(EventType.TASK_COMPLETED, handler)
        stats = bus.get_stats()
        assert "rate_limiters" in stats
        assert "circuit_breakers" in stats
        assert len(stats["rate_limiters"]) == 1
        assert len(stats["circuit_breakers"]) == 1

    async def test_accessor_methods(self, bus):
        async def handler(event):
            pass

        sub = bus.subscribe(EventType.TASK_COMPLETED, handler)
        cb = bus.get_circuit_breaker(sub.id)
        rl = bus.get_rate_limiter(sub.id)
        assert cb is not None
        assert rl is not None
        assert cb.name == sub.id
        assert rl.name == sub.id

    async def test_circuit_breaker_stats_after_failures(self, bus):
        async def failing_handler(event):
            raise ValueError("fail")

        sub = bus.subscribe(EventType.SYSTEM_ERROR, failing_handler)
        cb = bus.get_circuit_breaker(sub.id)

        for i in range(10):
            await bus.publish(Event(event_type=EventType.SYSTEM_ERROR, data={"i": i}))
        await asyncio.sleep(0.3)

        stats = cb.get_stats()
        assert stats["state"] == "open"
        assert stats["total_failures"] >= 5
        assert stats["failure_count"] >= 5
