"""
VECTOR Background Task Queue — parallel execution without blocking the main loop.

RULE 2: nothing in here can crash the autonomous loop.
RULE 8: every completed/failed task stored in episodic memory.

Usage:
    from core.loop.task_queue import TaskQueue, Priority

    tq = TaskQueue.get()
    task_id = tq.submit(some_coroutine(), name="Research AI news", priority=Priority.LOW)
    tq.status(task_id)   # → Task dataclass
    tq.cancel(task_id)
"""
import sys

__all__ = [
    "get_task_queue",
    "Priority",
    "Task",
    "TaskQueue",
    "TaskStatus",
]

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


from loguru import logger
from core.config import CONFIG

# â”€â”€ Enums & Dataclasses â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Priority(int, Enum):
    CRITICAL   = 0
    HIGH       = 1
    NORMAL     = 2
    LOW        = 3
    BACKGROUND = 4


class TaskStatus(str, Enum):
    QUEUED      = "queued"
    RUNNING     = "running"
    DONE        = "done"
    FAILED      = "failed"
    CANCELLED   = "cancelled"
    INTERRUPTED = "interrupted"   # was in-flight when the process restarted


@dataclass
class Task:
    id:           str
    name:         str
    priority:     Priority
    district:     str               = "core"
    tags:         list[str]         = field(default_factory=list)
    status:       TaskStatus        = TaskStatus.QUEUED
    progress:     float             = 0.0          # 0.0 → 1.0
    result:       Any               = None
    error:        str | None        = None
    submitted_at: float             = field(default_factory=time.time)
    started_at:   float | None      = None
    finished_at:  float | None      = None

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "name":         self.name,
            "priority":     self.priority.name,
            "district":     self.district,
            "tags":         self.tags,
            "status":       self.status.value,
            "progress":     self.progress,
            "elapsed":      self.elapsed,
            "error":        self.error,
            "submitted_at": self.submitted_at,
        }


# â”€â”€ TaskQueue â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TaskQueue:
    """
    Singleton parallel execution engine.

    submit()  → returns task_id immediately, work runs in background
    status()  → Task dataclass with live progress/status
    cancel()  → cancels if still running
    list_*()  → introspection helpers

    On complete/fail fires three notifications:
      1. Terminal line  — printed directly via loguru (chat picks it up)
      2. Episodic store — RULE 8
      3. Pushover       — via permission_gateway.notify (best-effort)
    """

    _instance: "TaskQueue | None" = None

    @classmethod
    def get(cls) -> "TaskQueue":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        max_workers: int = CONFIG.get("task_queue", {}).get("max_concurrent", 8)
        self._tasks:      dict[str, Task]         = {}
        self._aio_tasks:  dict[str, asyncio.Task] = {}
        self._running:    set[str]                = set()
        self._thread_pool = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="vector-bg"
        )
        self._max_concurrent = max_workers
        # Terminal notification callback — set by chat.py when it starts
        self._terminal_notify: Callable[[str], None] | None = None
        self._shutdown_flag = False

        # Durable ledger for cross-restart continuation (roadmap #7).
        self._ledger = None
        self._interrupted: list[dict] = []
        try:
            from core.loop.task_ledger import TaskLedger
            from core.runtime_paths import data_path
            self._ledger = TaskLedger(data_path("tasks.db"))
            self._interrupted = self._ledger.recover_interrupted()
        except Exception as e:
            logger.warning(f"[VECTOR][task_queue] ledger unavailable (in-memory only): {e}")

        logger.info(f"[VECTOR][task_queue] ready max_concurrent={max_workers}")

    def _persist(self, task: "Task") -> None:
        """Best-effort write-through of a task's current state to the ledger."""
        if self._ledger is None:
            return
        try:
            self._ledger.upsert({
                "id":           task.id,
                "name":         task.name,
                "priority":     task.priority.name,
                "district":     task.district,
                "tags":         json.dumps(task.tags),
                "status":       task.status.value,
                "progress":     task.progress,
                "error":        task.error,
                "submitted_at": task.submitted_at,
                "started_at":   task.started_at,
                "finished_at":  task.finished_at,
            })
        except Exception as e:
            logger.debug(f"[VECTOR][task_queue] persist skipped for {task.id}: {e}")

    def list_interrupted(self) -> list[dict]:
        """Tasks that were in-flight when a previous process exited — re-submittable."""
        if self._ledger is not None:
            return self._ledger.list_interrupted()
        return list(self._interrupted)

    # â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def submit(
        self,
        work:     "Coroutine | Callable | asyncio.coroutine",
        name:     str,
        priority: Priority   = Priority.NORMAL,
        district: str        = "core",
        tags:     list[str]  | None = None,
    ) -> str:
        """
        Submit work for background execution.
        Returns task_id (8-char hex) immediately.
        work can be a coroutine, coroutine function, or blocking callable.
        """
        task_id = uuid.uuid4().hex[:8]
        task = Task(
            id=task_id,
            name=name,
            priority=priority,
            district=district,
            tags=tags or [],
        )
        self._tasks[task_id] = task
        self._persist(task)

        try:
            loop = asyncio.get_event_loop()
            if asyncio.iscoroutine(work):
                aio = loop.create_task(self._run_coro(task_id, work))
            elif asyncio.iscoroutinefunction(work):
                aio = loop.create_task(self._run_coro(task_id, work()))
            else:
                # blocking callable → offload to thread pool
                aio = loop.create_task(self._run_in_thread(task_id, work))
            self._aio_tasks[task_id] = aio
        except RuntimeError:
            # Called from outside a running event loop — mark QUEUED, loop picks up
            logger.warning(f"[VECTOR][task_queue] no running loop — task {task_id} queued")

        logger.info(
            f"[VECTOR][task_queue] submitted id={task_id} name={name!r} "
            f"priority={priority.name} district={district}"
        )
        return task_id

    def cancel(self, task_id: str) -> bool:
        aio = self._aio_tasks.get(task_id)
        if aio and not aio.done():
            aio.cancel()
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.CANCELLED
                self._persist(task)
            logger.info(f"[VECTOR][task_queue] cancelled id={task_id}")
            return True
        return False

    def status(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def update_progress(self, task_id: str, progress: float) -> None:
        task = self._tasks.get(task_id)
        if task:
            task.progress = max(0.0, min(1.0, progress))

    def list_queued(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]

    def list_running(self) -> list[Task]:
        return [self._tasks[tid] for tid in self._running if tid in self._tasks]

    def list_recent(self, n: int = 20) -> list[Task]:
        terminal = (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED)
        done = [t for t in self._tasks.values() if t.status in terminal]
        return sorted(done, key=lambda t: t.finished_at or 0, reverse=True)[:n]

    def summary(self) -> dict:
        running = self.list_running()
        recent  = self.list_recent(10)
        queued  = [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]
        return {
            "running":        len(running),
            "queued":         len(queued),
            "completed_today": sum(1 for t in self._tasks.values() if t.status == TaskStatus.DONE),
            "failed_today":    sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED),
            "tasks":  [t.to_dict() for t in running],
            "recent": [t.to_dict() for t in recent],
        }

    def set_terminal_notify(self, fn: Callable[[str], None]) -> None:
        """Register a callback for in-terminal task completion lines."""
        self._terminal_notify = fn

    def cancel_all(self) -> None:
        """Cancel all running tasks."""
        for tid in list(self._aio_tasks.keys()):
            self.cancel(tid)
        logger.info("[VECTOR][task_queue] all tasks cancelled")

    def shutdown(self, wait: bool = True) -> None:
        """Release thread pool resources. Call during graceful shutdown."""
        self.cancel_all()
        self._thread_pool.shutdown(wait=wait)
        logger.info("[VECTOR][task_queue] thread pool shut down")

    # â”€â”€ Internal runners â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _run_coro(self, task_id: str, coro: Coroutine) -> None:
        task = self._tasks[task_id]
        task.status     = TaskStatus.RUNNING
        task.started_at = time.time()
        self._running.add(task_id)
        self._persist(task)
        try:
            result      = await coro
            task.result = result
            task.status = TaskStatus.DONE
            task.progress = 1.0
            await self._on_complete(task)
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error  = str(e)
            logger.error(f"[VECTOR][task_queue] FAILED id={task_id} name={task.name!r} err={e}")
            await self._on_failed(task)
        finally:
            task.finished_at = time.time()
            self._running.discard(task_id)
            self._persist(task)

    async def _run_in_thread(self, task_id: str, fn: Callable) -> None:
        task = self._tasks[task_id]
        task.status     = TaskStatus.RUNNING
        task.started_at = time.time()
        self._running.add(task_id)
        self._persist(task)
        try:
            loop   = asyncio.get_event_loop()
            result = await loop.run_in_executor(self._thread_pool, fn)
            task.result   = result
            task.status   = TaskStatus.DONE
            task.progress = 1.0
            await self._on_complete(task)
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error  = str(e)
            logger.error(f"[VECTOR][task_queue] thread FAILED id={task_id} name={task.name!r} err={e}")
            await self._on_failed(task)
        finally:
            task.finished_at = time.time()
            self._running.discard(task_id)
            self._persist(task)

    # â”€â”€ Notification â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _on_complete(self, task: Task) -> None:
        msg = f"[✓ BG] {task.name} ({task.elapsed}s)"

        # 1. Terminal line
        self._notify_terminal(msg)

        # 2. Episodic memory — RULE 8
        await self._store_episodic(task, success=True)

        # 3. Pushover
        await self._pushover(msg)

    async def _on_failed(self, task: Task) -> None:
        msg = f"[✗ BG] {task.name} FAILED: {task.error or '?'} ({task.elapsed}s)"

        self._notify_terminal(msg)
        await self._store_episodic(task, success=False)
        await self._pushover(msg)

    def _notify_terminal(self, msg: str) -> None:
        if self._terminal_notify:
            try:
                self._terminal_notify(msg)
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        # Always log — visible in the terminal regardless
        logger.info(f"[VECTOR][task_queue] {msg}")

    async def _store_episodic(self, task: Task, success: bool) -> None:
        try:
            from core.memory.episodic import EpisodicMemory
            result_preview = str(task.result)[:400] if task.result else (task.error or "")
            EpisodicMemory().store(
                event_type="background_task_complete" if success else "background_task_failed",
                content=f"Task '{task.name}' {'completed' if success else 'failed'}. "
                        f"District: {task.district}. Elapsed: {task.elapsed}s. "
                        f"{'Result: ' + result_preview if success else 'Error: ' + (task.error or '')}",
                tags=["background", "task_complete" if success else "task_failed"] + task.tags,
                source=f"task_queue:{task.district}",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][task_queue] episodic store failed: {e}")

    async def _pushover(self, msg: str) -> None:
        try:
            from core.loop.permission_gateway import PermissionGateway
            await PermissionGateway().notify(msg)
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)


# â”€â”€ Convenience helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_task_queue() -> TaskQueue:
    return TaskQueue.get()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        tq = TaskQueue.get()
        assert tq is TaskQueue.get(), "singleton broken"

        # Fast coroutine task
        async def quick_work():
            await asyncio.sleep(0.1)
            return {"items": 3}

        tid = tq.submit(quick_work(), name="smoke-test", priority=Priority.HIGH, district="test")
        assert len(tid) == 8
        print(f"  submitted task_id={tid}")

        await asyncio.sleep(0.5)
        t = tq.status(tid)
        assert t is not None
        assert t.status == TaskStatus.DONE, f"expected DONE got {t.status}"
        assert t.result == {"items": 3}
        print(f"  task done elapsed={t.elapsed}s result={t.result}")

        # Blocking callable task
        def blocking():
            import time as _t; _t.sleep(0.05)
            return "blocking-ok"

        tid2 = tq.submit(blocking, name="blocking-smoke", priority=Priority.LOW)
        await asyncio.sleep(0.5)
        t2 = tq.status(tid2)
        assert t2.status == TaskStatus.DONE, f"expected DONE got {t2.status}"
        print(f"  blocking task done result={t2.result}")

        # Summary
        s = tq.summary()
        assert s["completed_today"] >= 2
        print(f"  summary: {s['completed_today']} completed, {s['running']} running")

        print(f"✅ task_queue.py OK")

    asyncio.run(_smoke())
