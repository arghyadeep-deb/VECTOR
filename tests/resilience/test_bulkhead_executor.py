
import asyncio
import pytest
from loguru import logger

from core.resilience.bulkhead_executor import BulkheadConfig, BulkheadExecutor, BulkheadRegistry, BulkheadRejectedError


@pytest.fixture
def bulkhead():
    config = BulkheadConfig(name="test", max_concurrent=2, max_queue=3, queue_timeout=1.0)
    return BulkheadExecutor(config)


@pytest.mark.asyncio
async def test_semaphore_limits(bulkhead):
    started = 0
    completed = 0

    async def slow_task():
        nonlocal started, completed
        started += 1
        await asyncio.sleep(0.2)
        completed += 1

    tasks = []
    for _ in range(4):
        tasks.append(asyncio.create_task(bulkhead.execute(slow_task)))
    await asyncio.sleep(0.05)
    assert started <= 2
    await asyncio.gather(*tasks)
    assert completed == 4


@pytest.mark.asyncio
async def test_queue_overflow_rejection(bulkhead):
    async def slow_task():
        await asyncio.sleep(1.0)

    tasks = []
    for _ in range(6):
        tasks.append(asyncio.create_task(bulkhead.execute(slow_task)))
    await asyncio.sleep(0.1)
    results = []
    for t in tasks:
        try:
            await t
            results.append("ok")
        except BulkheadRejectedError:
            results.append("rejected")
    assert results.count("rejected") >= 1


@pytest.mark.asyncio
async def test_cleanup_on_completion(bulkhead):
    stats = await bulkhead.get_stats()
    assert stats["current_concurrent"] == 0

    async def quick_task():
        pass

    await bulkhead.execute(quick_task)
    stats = await bulkhead.get_stats()
    assert stats["current_concurrent"] == 0
    assert stats["total_processed"] == 1


@pytest.mark.asyncio
async def test_bulkhead_registry():
    registry = BulkheadRegistry()
    bh = registry.register("test_reg", BulkheadConfig(name="test_reg", max_concurrent=3))
    assert bh is not None
    same = registry.get("test_reg")
    assert same is bh
    missing = registry.get("nonexistent")
    assert missing is None
    stats = await registry.get_all_stats()
    assert "test_reg" in stats


@pytest.mark.asyncio
async def test_error_counting(bulkhead):
    async def failing_task():
        raise ValueError("boom")

    for _ in range(3):
        try:
            await bulkhead.execute(failing_task)
        except ValueError:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)

    stats = await bulkhead.get_stats()
    assert stats["total_errors"] == 3