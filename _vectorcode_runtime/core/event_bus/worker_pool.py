from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable

from loguru import logger


class WorkerPool:

    # Completed/failed tasks are retained for this long before pruning (seconds).
    _RETENTION_SECONDS = 3600  # 1 hour

    def __init__(self, max_workers: int = 4, name: str = "generic") -> None:
        self.max_workers = max_workers
        self.name = name
        self._semaphore = asyncio.Semaphore(max_workers)
        self._tasks: dict[str, dict[str, Any]] = {}
        self._task_handles: dict[str, asyncio.Task] = {}  # for cancellation
        self._lock = asyncio.Lock()
        self._active_count = 0
        self._completed_count = 0
        self._failed_count = 0
        logger.info("[WorkerPool][{}] initialized with max_workers={}", name, max_workers)

    async def submit(self, name: str, coro: Callable[[], Any]) -> str:
        task_id = uuid.uuid4().hex[:12]
        async with self._lock:
            self._tasks[task_id] = {
                "name": name,
                "status": "queued",
                "submitted_at": time.time(),
                "started_at": None,
                "completed_at": None,
                "result": None,
                "error": None,
            }
        handle = asyncio.create_task(self._run(task_id, name, coro), name=f"wp_{task_id}")
        async with self._lock:
            self._task_handles[task_id] = handle
        # Opportunistic prune: clean up old completed tasks every 100 submissions
        if len(self._tasks) > 100:
            await self._prune_completed()
        logger.debug("[WorkerPool][{}] submitted task {} ({})", self.name, task_id, name)
        return task_id

    async def map(self, name: str, coros: list[Callable[[], Any]]) -> list[str]:
        task_ids = []
        for i, coro in enumerate(coros):
            task_name = f"{name}_{i}"
            task_id = await self.submit(task_name, coro)
            task_ids.append(task_id)
        return task_ids

    async def _prune_completed(self) -> None:
        """Remove completed/failed/cancelled tasks older than _RETENTION_SECONDS."""
        cutoff = time.time() - self._RETENTION_SECONDS
        to_remove = []
        async with self._lock:
            for tid, entry in self._tasks.items():
                if entry["status"] in ("completed", "failed", "cancelled"):
                    completed_at = entry.get("completed_at") or 0
                    if completed_at < cutoff:
                        to_remove.append(tid)
            for tid in to_remove:
                del self._tasks[tid]
                self._task_handles.pop(tid, None)
        if to_remove:
            logger.debug("[WorkerPool][{}] pruned {} completed tasks", self.name, len(to_remove))

    async def _run(self, task_id: str, name: str, coro: Callable[[], Any]) -> None:
        async with self._semaphore:
            async with self._lock:
                self._active_count += 1
                self._tasks[task_id]["status"] = "running"
                self._tasks[task_id]["started_at"] = time.time()
            try:
                result = await coro()
                async with self._lock:
                    self._completed_count += 1
                    self._tasks[task_id]["status"] = "completed"
                    self._tasks[task_id]["completed_at"] = time.time()
                    self._tasks[task_id]["result"] = result
                logger.debug("[WorkerPool][{}] task {} completed", self.name, task_id)
            except asyncio.CancelledError:
                async with self._lock:
                    self._tasks[task_id]["status"] = "cancelled"
                    self._tasks[task_id]["completed_at"] = time.time()
            except Exception as exc:
                async with self._lock:
                    self._failed_count += 1
                    self._tasks[task_id]["status"] = "failed"
                    self._tasks[task_id]["completed_at"] = time.time()
                    self._tasks[task_id]["error"] = str(exc)
                logger.error("[WorkerPool][{}] task {} failed: {}", self.name, task_id, exc)
            finally:
                async with self._lock:
                    self._active_count -= 1

    async def shutdown(self, wait: bool = True) -> None:
        logger.info("[WorkerPool][{}] shutting down (wait={})", self.name, wait)
        # Cancel all pending/running tasks
        async with self._lock:
            handles = list(self._task_handles.values())
        for handle in handles:
            if not handle.done():
                handle.cancel()
        if wait and handles:
            await asyncio.gather(*handles, return_exceptions=True)
        # Clear all state
        async with self._lock:
            self._tasks.clear()
            self._task_handles.clear()
            self._active_count = 0
        logger.info("[WorkerPool][{}] shutdown complete", self.name)

    def get_stats(self) -> dict[str, Any]:
        queued = sum(1 for t in self._tasks.values() if t["status"] == "queued")
        running = sum(1 for t in self._tasks.values() if t["status"] == "running")
        return {
            "name": self.name,
            "max_workers": self.max_workers,
            "active": self._active_count,
            "running": running,
            "queued": queued,
            "completed": self._completed_count,
            "failed": self._failed_count,
            "total_tasks": len(self._tasks),
        }
