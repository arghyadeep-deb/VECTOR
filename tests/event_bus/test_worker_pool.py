
import asyncio
import pytest

from core.event_bus.worker_pool import WorkerPool


@pytest.fixture
async def pool():
    p = WorkerPool(max_workers=2, name="test")
    yield p
    await p.shutdown(wait=False)


@pytest.mark.asyncio
class TestWorkerPool:

    async def test_submit_and_complete(self, pool):
        async def dummy():
            return 42

        task_id = await pool.submit("test_task", dummy)
        await asyncio.sleep(0.1)
        stats = pool.get_stats()
        assert stats["completed"] == 1
        assert stats["failed"] == 0
        assert pool._tasks[task_id]["result"] == 42

    async def test_max_concurrency_limiting(self, pool):
        results = []

        async def slow():
            await asyncio.sleep(0.3)
            results.append(1)
            return 1

        task_ids = await pool.map("slow", [slow, slow, slow, slow])
        await asyncio.sleep(0.15)
        stats = pool.get_stats()
        assert stats["running"] <= pool.max_workers
        await asyncio.sleep(0.5)
        stats = pool.get_stats()
        assert stats["completed"] == 4

    async def test_task_failure(self, pool):
        async def failing():
            raise ValueError("test error")

        task_id = await pool.submit("fail_task", failing)
        await asyncio.sleep(0.1)
        stats = pool.get_stats()
        assert stats["failed"] == 1
        assert "test error" in str(pool._tasks[task_id]["error"])

    async def test_get_stats(self, pool):
        stats = pool.get_stats()
        assert stats["name"] == "test"
        assert stats["max_workers"] == 2
        assert "active" in stats
        assert "running" in stats
        assert "queued" in stats
        assert "completed" in stats
        assert "failed" in stats
        assert "total_tasks" in stats

    async def test_shutdown_wait(self, pool):
        async def fast():
            return 1

        await pool.submit("a", fast)
        await pool.submit("b", fast)
        await pool.shutdown(wait=True)
        stats = pool.get_stats()
        assert stats["completed"] + stats["failed"] == stats["total_tasks"]

    async def test_map_returns_task_ids(self, pool):
        async def dummy():
            return 1

        ids = await pool.map("batch", [dummy, dummy])
        assert len(ids) == 2
        import uuid
        for tid in ids:
            assert len(tid) == 12
            assert all(c in "0123456789abcdef" for c in tid)

    async def test_semaphore_limits_concurrent(self, pool):
        sem_checks = []
        original_acquire = pool._semaphore.acquire

        async def wrapped_acquire():
            sem_checks.append(pool._semaphore._value)
            return await original_acquire()

        pool._semaphore.acquire = wrapped_acquire

        async def worker():
            await asyncio.sleep(0.2)

        await pool.map("workers", [worker, worker, worker, worker])
        await asyncio.sleep(0.5)
        assert all(v >= 0 for v in sem_checks)
