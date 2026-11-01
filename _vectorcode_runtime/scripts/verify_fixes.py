"""Verify provider_health fix: base_cooldown_seconds=0 should NOT be overridden by CONFIG."""
import sys
sys.path.insert(0, ".")

# Test 1: Explicit 0 should stay 0
from core.inference.provider_health import ProviderHealthManager
h = ProviderHealthManager(failure_threshold=2, base_cooldown_seconds=0)
assert h.failure_threshold == 2, f"Expected 2, got {h.failure_threshold}"
assert h.base_cooldown_seconds == 0, f"Expected 0, got {h.base_cooldown_seconds}"
print(f"  OK  failure_threshold={h.failure_threshold}, base_cooldown_seconds={h.base_cooldown_seconds}")

# Test 2: None should use CONFIG defaults
h2 = ProviderHealthManager()
assert h2.failure_threshold >= 1, f"Expected >=1, got {h2.failure_threshold}"
assert h2.base_cooldown_seconds >= 1, f"Expected >=1, got {h2.base_cooldown_seconds}"
print(f"  OK  defaults: failure_threshold={h2.failure_threshold}, base_cooldown_seconds={h2.base_cooldown_seconds}")

# Test 3: WorkerPool pruning
import asyncio
from core.event_bus.worker_pool import WorkerPool

async def _test_pool():
    pool = WorkerPool(max_workers=2, name="test")
    async def noop():
        return 42
    tid = await pool.submit("test_task", noop)
    await asyncio.sleep(0.2)
    stats = pool.get_stats()
    assert stats["completed"] >= 1 or stats["total_tasks"] >= 1, f"Unexpected stats: {stats}"
    await pool.shutdown(wait=False)
    print(f"  OK  WorkerPool: {stats}")

asyncio.run(_test_pool())

# Test 4: model_pool cooldown lock
from core.inference.model_pool import mark_cooldown, _is_cooling_down, cooldown_status
mark_cooldown("test_provider", seconds=5)
assert _is_cooling_down("test_provider"), "Should be cooling down"
status = cooldown_status()
assert "test_provider" in status, f"Expected test_provider in status: {status}"
print(f"  OK  model_pool cooldown lock works")

print("\nAll manual verification checks passed")
