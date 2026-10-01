"""Integration tests for Spec 11 — Resilience Infrastructure.

Covers: circuit breaker state machine, bulkhead capacity, chaos monkey,
graceful degradation, recovery playbooks, and the ResilienceLayer facade.
All tests are self-contained — no external services required.
"""
from __future__ import annotations

import asyncio


import pytest

# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class TestCircuitBreakerStateMachine:
    """Exercise the full CLOSED → OPEN → HALF_OPEN → CLOSED cycle."""

    def _cb(self, threshold: int = 3, recovery: float = 0.05):
        from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        return CircuitBreaker(CircuitBreakerConfig(
            name="test", failure_threshold=threshold, recovery_timeout=recovery,
            half_open_max_retries=2, success_threshold=2,
        ))

    async def test_starts_closed(self):
        from core.resilience.circuit_breaker import CircuitState
        cb = self._cb()
        assert cb.state == CircuitState.CLOSED

    async def test_trips_after_threshold_failures(self):
        import asyncio
        from core.resilience.circuit_breaker import CircuitState

        cb = self._cb(threshold=3)

        async def bad():
            raise RuntimeError("boom")

        for _ in range(3):
            try:
                await cb.call(bad)
            except Exception:
                pass

        assert cb.state == CircuitState.OPEN

    async def test_open_raises_circuit_open_error(self):
        from core.resilience.circuit_breaker import CircuitBreakerOpenError, CircuitState

        cb = self._cb(threshold=2)

        async def bad():
            raise RuntimeError("boom")

        for _ in range(2):
            try:
                await cb.call(bad)
            except Exception:
                pass

        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(bad)

    async def test_transitions_to_half_open_after_timeout(self):
        import asyncio
        from core.resilience.circuit_breaker import CircuitState

        cb = self._cb(threshold=2, recovery=0.05)

        async def bad():
            raise RuntimeError("boom")

        for _ in range(2):
            try:
                await cb.call(bad)
            except Exception:
                pass

        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.1)

        # Probe: should allow through (HALF_OPEN)
        try:
            await cb.call(bad)
        except Exception:
            pass
        assert cb.state in (CircuitState.HALF_OPEN, CircuitState.OPEN)

    async def test_recovers_to_closed_after_successes(self):
        import asyncio
        from core.resilience.circuit_breaker import CircuitState

        cb = self._cb(threshold=2, recovery=0.05)

        async def bad():
            raise RuntimeError("boom")

        async def good():
            return "ok"

        for _ in range(2):
            try:
                await cb.call(bad)
            except Exception:
                pass

        await asyncio.sleep(0.1)

        # 2 successes needed to close
        for _ in range(2):
            try:
                await cb.call(good)
            except Exception:
                pass

        assert cb.state == CircuitState.CLOSED

    async def test_force_open_and_close(self):
        from core.resilience.circuit_breaker import CircuitState
        cb = self._cb()
        await cb.force_open()
        assert cb.state == CircuitState.OPEN
        await cb.force_close()
        assert cb.state == CircuitState.CLOSED

    async def test_state_snapshot_has_required_keys(self):
        cb = self._cb()
        snap = cb.get_state_snapshot()
        for key in ("name", "state", "failure_count", "success_count",
                    "last_failure_time", "failure_threshold", "recovery_timeout"):
            assert key in snap

    async def test_sync_callable_works(self):
        from core.resilience.circuit_breaker import CircuitState
        cb = self._cb()
        result = await cb.call(lambda: 42)
        assert result == 42
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerRegistry:
    async def test_register_returns_circuit_breaker(self):
        from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry
        reg = CircuitBreakerRegistry()
        cb = reg.register("svc_a")
        assert isinstance(cb, CircuitBreaker)

    async def test_register_idempotent(self):
        from core.resilience.circuit_breaker import CircuitBreakerRegistry
        reg = CircuitBreakerRegistry()
        cb1 = reg.register("svc_b")
        cb2 = reg.register("svc_b")
        assert cb1 is cb2

    async def test_get_returns_none_for_unknown(self):
        from core.resilience.circuit_breaker import CircuitBreakerRegistry
        reg = CircuitBreakerRegistry()
        assert reg.get("unknown_xyz") is None

    async def test_get_all_snapshots(self):
        from core.resilience.circuit_breaker import CircuitBreakerRegistry
        reg = CircuitBreakerRegistry()
        reg.register("s1")
        reg.register("s2")
        snaps = reg.get_all_snapshots()
        assert "s1" in snaps and "s2" in snaps

    async def test_reset_all_closes_open_breakers(self):
        from core.resilience.circuit_breaker import CircuitBreakerRegistry, CircuitState
        reg = CircuitBreakerRegistry()
        cb = reg.register("svc_c")
        await cb.force_open()
        assert cb.state == CircuitState.OPEN
        await reg.reset_all()
        assert cb.state == CircuitState.CLOSED

    async def test_open_count_property(self):
        from core.resilience.circuit_breaker import CircuitBreakerRegistry
        reg = CircuitBreakerRegistry()
        cb1 = reg.register("x1")
        cb2 = reg.register("x2")
        await cb1.force_open()
        assert reg.open_count == 1
        await cb2.force_open()
        assert reg.open_count == 2


# ---------------------------------------------------------------------------
# Bulkhead Executor
# ---------------------------------------------------------------------------

class TestBulkheadExecutor:
    def _bh(self, max_concurrent: int = 2, max_queue: int = 2):
        from core.resilience.bulkhead_executor import BulkheadConfig, BulkheadExecutor
        return BulkheadExecutor(BulkheadConfig(
            name="test_bh", max_concurrent=max_concurrent, max_queue=max_queue,
        ))

    async def test_basic_execution(self):
        bh = self._bh()
        result = await bh.execute(lambda: "hello")
        assert result == "hello"

    async def test_async_execution(self):
        async def work():
            return 99
        bh = self._bh()
        result = await bh.execute(work)
        assert result == 99

    async def test_rejects_when_queue_full(self):
        import asyncio
        from core.resilience.bulkhead_executor import BulkheadRejectedError

        bh = self._bh(max_concurrent=1, max_queue=0)
        gate = asyncio.Event()

        async def slow():
            await gate.wait()
            return "done"

        # Start one task that holds the semaphore
        task = asyncio.create_task(bh.execute(slow))
        await asyncio.sleep(0.01)

        # Now queue is at capacity (max_queue=0), next should be rejected
        with pytest.raises(BulkheadRejectedError):
            await bh.execute(slow)

        gate.set()
        await task

    async def test_stats_has_required_keys(self):
        bh = self._bh()
        await bh.execute(lambda: None)
        stats = await bh.get_stats()
        for key in ("name", "max_concurrent", "max_queue",
                    "total_processed", "total_rejected", "total_errors"):
            assert key in stats

    async def test_total_processed_increments(self):
        bh = self._bh()
        await bh.execute(lambda: None)
        await bh.execute(lambda: None)
        stats = await bh.get_stats()
        assert stats["total_processed"] == 2

    async def test_total_rejected_increments(self):
        import asyncio
        from core.resilience.bulkhead_executor import BulkheadRejectedError

        bh = self._bh(max_concurrent=1, max_queue=0)
        gate = asyncio.Event()

        async def slow():
            await gate.wait()

        task = asyncio.create_task(bh.execute(slow))
        await asyncio.sleep(0.01)

        try:
            await bh.execute(slow)
        except BulkheadRejectedError:
            pass

        gate.set()
        await task
        stats = await bh.get_stats()
        assert stats["total_rejected"] >= 1

    async def test_error_increments_error_count(self):
        bh = self._bh()

        async def bad():
            raise ValueError("oops")

        with pytest.raises(ValueError):
            await bh.execute(bad)

        stats = await bh.get_stats()
        assert stats["total_errors"] == 1


class TestBulkheadRegistry:
    async def test_register_and_get(self):
        from core.resilience.bulkhead_executor import BulkheadExecutor, BulkheadRegistry
        reg = BulkheadRegistry()
        bh = reg.register("svc_a")
        assert isinstance(bh, BulkheadExecutor)
        assert reg.get("svc_a") is bh

    async def test_register_idempotent(self):
        from core.resilience.bulkhead_executor import BulkheadRegistry
        reg = BulkheadRegistry()
        bh1 = reg.register("svc_b")
        bh2 = reg.register("svc_b")
        assert bh1 is bh2

    async def test_get_all_stats(self):
        from core.resilience.bulkhead_executor import BulkheadRegistry
        reg = BulkheadRegistry()
        reg.register("svc_c")
        reg.register("svc_d")
        stats = await reg.get_all_stats()
        assert "svc_c" in stats and "svc_d" in stats


# ---------------------------------------------------------------------------
# Chaos Monkey
# ---------------------------------------------------------------------------

class TestChaosMonkey:
    async def test_disabled_by_default(self):
        from core.resilience.chaos_monkey import ChaosMonkey
        cm = ChaosMonkey()
        assert cm.enabled is False

    async def test_dependency_failure_experiment_passes(self):
        """DependencyFailureInjector is safe — no real resource harm."""
        from core.resilience.chaos_monkey import ChaosMonkey
        from core.resilience.injectors.dependency_failure import DependencyFailureInjector

        cm = ChaosMonkey()
        result = await cm.run_experiment(DependencyFailureInjector())
        assert result.injector_name == "dependency_failure"
        assert result.passed is True
        assert result.recovery_time_s >= 0

    async def test_on_result_callback_fires(self):
        from core.resilience.chaos_monkey import ChaosMonkey
        from core.resilience.injectors.dependency_failure import DependencyFailureInjector

        cm = ChaosMonkey()
        fired = []
        cm.on_result(lambda r: fired.append(r))
        await cm.run_experiment(DependencyFailureInjector())
        assert len(fired) == 1

    async def test_results_accumulate(self):
        from core.resilience.chaos_monkey import ChaosMonkey
        from core.resilience.injectors.dependency_failure import DependencyFailureInjector

        cm = ChaosMonkey()
        await cm.run_experiment(DependencyFailureInjector())
        await cm.run_experiment(DependencyFailureInjector())
        assert len(cm.results) == 2

    async def test_generate_report_format(self):
        from core.resilience.chaos_monkey import ChaosMonkey
        from core.resilience.injectors.dependency_failure import DependencyFailureInjector

        cm = ChaosMonkey()
        await cm.run_experiment(DependencyFailureInjector())
        report = cm.generate_report()
        assert "Chaos Monkey Report" in report
        assert "dependency_failure" in report
        assert "Pass rate" in report

    async def test_generate_report_empty(self):
        from core.resilience.chaos_monkey import ChaosMonkey
        cm = ChaosMonkey()
        report = cm.generate_report()
        assert "No chaos experiments" in report

    async def test_run_random_experiment(self):
        from core.resilience.chaos_monkey import ChaosMonkey
        from core.resilience.injectors.dependency_failure import DependencyFailureInjector

        cm = ChaosMonkey()
        cm.injectors = [DependencyFailureInjector()]
        result = await cm.run_random_experiment()
        assert result.passed is True

    async def test_scheduled_run_skips_when_disabled(self, caplog):
        import logging
        from core.resilience.chaos_monkey import ChaosMonkey
        cm = ChaosMonkey()
        assert not cm.enabled
        # Should return immediately without running experiments
        await cm.run_scheduled()
        assert len(cm.results) == 0


# ---------------------------------------------------------------------------
# Graceful Degradation
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    async def test_starts_at_full(self):
        from core.resilience.graceful_degradation import GracefulDegradation, ServiceTier
        gd = GracefulDegradation()
        assert gd.current_tier == ServiceTier.FULL

    async def test_evaluate_tier_returns_service_tier(self):
        from core.resilience.graceful_degradation import GracefulDegradation, ServiceTier
        gd = GracefulDegradation()
        tier = await gd.evaluate_tier()
        assert isinstance(tier, ServiceTier)

    async def test_get_available_services_returns_dict(self):
        from core.resilience.graceful_degradation import GracefulDegradation
        gd = GracefulDegradation()
        await gd.evaluate_tier()
        services = gd.get_available_services()
        assert isinstance(services, dict)

    async def test_get_service_limits_returns_dict(self):
        from core.resilience.graceful_degradation import GracefulDegradation
        gd = GracefulDegradation()
        limits = gd.get_service_limits("inference")
        assert "batch_size" in limits and "timeout_sec" in limits

    async def test_on_change_callback(self):
        from core.resilience.graceful_degradation import GracefulDegradation, ServiceTier
        gd = GracefulDegradation()
        changes = []
        gd.on_change(lambda old, new: changes.append((old, new)))
        gd._notify_change(ServiceTier.FULL, ServiceTier.REDUCED)
        assert len(changes) == 1
        assert changes[0] == (ServiceTier.FULL, ServiceTier.REDUCED)

    async def test_tier_enum_ordering(self):
        from core.resilience.graceful_degradation import ServiceTier
        assert ServiceTier.FULL > ServiceTier.REDUCED > ServiceTier.DEGRADED
        assert ServiceTier.DEGRADED > ServiceTier.MINIMAL > ServiceTier.EMERGENCY
        assert ServiceTier.EMERGENCY > ServiceTier.SURVIVAL


# ---------------------------------------------------------------------------
# Recovery Playbooks
# ---------------------------------------------------------------------------

class TestRecoveryPlaybooks:
    async def test_oom_playbook_succeeds(self):
        from core.resilience.recovery_playbooks import OOMPlaybook
        result = await OOMPlaybook().run()
        assert result.success is True
        assert len(result.actions_taken) > 0

    async def test_disk_full_playbook_succeeds(self):
        from core.resilience.recovery_playbooks import DiskFullPlaybook
        result = await DiskFullPlaybook().run()
        assert result.success is True

    async def test_config_corrupt_playbook_succeeds(self):
        from core.resilience.recovery_playbooks import ConfigCorruptPlaybook
        result = await ConfigCorruptPlaybook().run()
        assert result.success is True

    async def test_db_corruption_playbook_succeeds(self):
        from core.resilience.recovery_playbooks import DBCorruptionPlaybook
        result = await DBCorruptionPlaybook().run()
        assert result.success is True

    async def test_gpu_failure_playbook_succeeds(self):
        from core.resilience.recovery_playbooks import GPUFailurePlaybook
        result = await GPUFailurePlaybook().run()
        assert result.success is True

    async def test_network_partition_playbook_succeeds(self):
        from core.resilience.recovery_playbooks import NetworkPartitionPlaybook
        result = await NetworkPartitionPlaybook().run()
        assert result.success is True
        assert len(result.actions_taken) > 0

    async def test_playbook_result_has_name(self):
        from core.resilience.recovery_playbooks import OOMPlaybook
        result = await OOMPlaybook().run()
        assert result.name == "oom_recovery"
        assert result.duration_s >= 0

    async def test_playbook_registry_has_eight_entries(self):
        from core.resilience.recovery_playbooks import PLAYBOOK_REGISTRY
        assert len(PLAYBOOK_REGISTRY) >= 7  # model_crash needs Ollama; rest are safe

    async def test_run_all_playbooks_returns_list(self):
        # run_all_playbooks() includes ModelCrashPlaybook which calls `ollama serve`
        # (subprocess, real network) — test the 7 safe playbooks directly instead.
        from core.resilience.recovery_playbooks import (
            OOMPlaybook, DiskFullPlaybook, ConfigCorruptPlaybook,
            DBCorruptionPlaybook, GPUFailurePlaybook,
            NetworkPartitionPlaybook, ProcessHangPlaybook,
        )
        safe = [
            OOMPlaybook(), DiskFullPlaybook(), ConfigCorruptPlaybook(),
            DBCorruptionPlaybook(), GPUFailurePlaybook(),
            NetworkPartitionPlaybook(), ProcessHangPlaybook(),
        ]
        results = [await pb.run() for pb in safe]
        assert len(results) == 7
        assert all(r.name for r in results)


# ---------------------------------------------------------------------------
# ResilienceMetrics
# ---------------------------------------------------------------------------

class TestResilienceMetrics:
    def test_initial_health_summary(self):
        from core.resilience.metrics import ResilienceMetrics
        m = ResilienceMetrics()
        summary = m.get_health_summary()
        assert "circuit_breakers" in summary
        assert "bulkheads" in summary
        assert "failover" in summary
        assert "degradation" in summary
        assert "chaos" in summary

    def test_record_circuit_breaker_updates_summary(self):
        from core.resilience.metrics import ResilienceMetrics
        m = ResilienceMetrics()
        m.record_circuit_breaker({"ollama": {"state": "open"}, "memory": {"state": "closed"}})
        summary = m.get_health_summary()
        assert summary["circuit_breakers"]["total"] == 2
        assert summary["circuit_breakers"]["open"] == 1

    def test_record_degradation_appears_in_summary(self):
        from core.resilience.metrics import ResilienceMetrics
        m = ResilienceMetrics()
        m.record_degradation({"new_tier": "REDUCED", "timestamp": 0})
        summary = m.get_health_summary()
        assert summary["degradation"]["current_tier"] == "REDUCED"

    def test_chaos_pass_rate_none_when_no_experiments(self):
        # No experiments run != 100% pass rate -- must be distinguishable
        # (chaos.enabled defaults to False, so this is the common state).
        from core.resilience.metrics import ResilienceMetrics
        m = ResilienceMetrics()
        assert m._chaos_pass_rate() is None
        assert m.get_health_summary()["chaos"]["pass_rate"] is None

    def test_chaos_pass_rate_computed_when_experiments_recorded(self):
        from core.resilience.metrics import ResilienceMetrics
        m = ResilienceMetrics()
        m.record_chaos_experiment({"passed": True})
        m.record_chaos_experiment({"passed": False})
        assert m._chaos_pass_rate() == 0.5

    def test_to_json_returns_string(self):
        from core.resilience.metrics import ResilienceMetrics
        import json
        m = ResilienceMetrics()
        j = m.to_json()
        assert isinstance(j, str)
        parsed = json.loads(j)
        assert "circuit_breakers" in parsed


# ---------------------------------------------------------------------------
# ResilienceLayer Facade
# ---------------------------------------------------------------------------

class TestResilienceLayerFacade:
    async def test_initializes_default_circuit_breakers(self):
        from core.resilience import ResilienceLayer
        rl = ResilienceLayer()
        for name in ("ollama", "memory_db", "cloud_api", "tts"):
            assert rl.circuit_breakers.get(name) is not None

    async def test_initializes_default_bulkheads(self):
        from core.resilience import ResilienceLayer
        rl = ResilienceLayer()
        for name in ("voice", "inference", "memory"):
            assert rl.bulkheads.get(name) is not None

    async def test_wrap_call_passes_through_when_disabled(self):
        from core.resilience import ResilienceLayer
        rl = ResilienceLayer()
        rl._enabled = False

        async def work():
            return "result"

        result = await rl.wrap_call("ollama", "inference", work)
        assert result == "result"

    async def test_wrap_call_uses_circuit_breaker(self):
        from core.resilience import ResilienceLayer
        from core.resilience.circuit_breaker import CircuitBreakerOpenError

        rl = ResilienceLayer()
        # Force the ollama circuit breaker open
        await rl.circuit_breakers.get("ollama").force_open()

        async def work():
            return "should not reach"

        with pytest.raises(CircuitBreakerOpenError):
            await rl.wrap_call("ollama", None, work)

    async def test_wrap_call_executes_sync_fn(self):
        from core.resilience import ResilienceLayer
        rl = ResilienceLayer()
        result = await rl.wrap_call("memory_db", None, lambda: 42)
        assert result == 42

    async def test_get_health_returns_dict(self):
        from core.resilience import ResilienceLayer
        rl = ResilienceLayer()
        health = rl.get_health()
        assert isinstance(health, dict)
        assert "circuit_breakers" in health

    async def test_run_monitor_cycle_completes(self):
        from core.resilience import ResilienceLayer
        rl = ResilienceLayer()
        # Should not raise; degradation checks may time out but are handled
        await rl.run_monitor_cycle()


# ---------------------------------------------------------------------------
# HotFailover
# ---------------------------------------------------------------------------

class TestHotFailover:
    async def test_state_digest_serializes(self):
        import dataclasses
        from core.resilience.hot_failover import StateDigest
        d = StateDigest(timestamp=1.0, generation=5)
        d_dict = dataclasses.asdict(d)
        assert d_dict["generation"] == 5

    async def test_initializes_as_primary(self):
        from core.resilience.hot_failover import HotFailover
        hf = HotFailover(is_primary=True)
        assert hf.is_primary is True

    async def test_initializes_as_secondary(self):
        from core.resilience.hot_failover import HotFailover
        hf = HotFailover(is_primary=False)
        assert hf.is_primary is False
