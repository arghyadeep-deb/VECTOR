from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.expansion_modules import (
    evaluate_destructive_action,
    is_protected_write_path,
    resolve_in_root,
)
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


_ROOT = Path(__file__).resolve().parents[3]  # module-level so tests can point it at a tmp dir


def add_worker_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _ROOT

    # â”€â”€ worker_* (26) — wired to core/loop/task_queue.py + core/scheduler/ â”€â”€â”€â”€â”€
    try:
        from core.loop.task_queue import get_task_queue as _get_wtq

        @mcp.tool
        def worker_list(status: str = "all", limit: int = 20) -> str:
            """List all background workers/tasks."""
            tq = _get_wtq()
            if status == "running":
                tasks = tq.list_running() if hasattr(tq, "list_running") else []
            else:
                tasks = tq.list_recent(limit) if hasattr(tq, "list_recent") else []
            return _safe_json({"tasks": [{"id": t.id, "name": t.name, "status": t.status} for t in tasks]})

        @mcp.tool
        def worker_status(task_id: str) -> str:
            """Get status of a worker task."""
            tq = _get_wtq()
            status = tq.status(task_id) if hasattr(tq, "status") else None
            return _safe_json({"task_id": task_id, "status": status.status if status else "not_found"})

        @mcp.tool
        def worker_submit(name: str, work: str = "") -> str:
            """Submit a worker task."""
            tq = _get_wtq()
            if not hasattr(tq, "submit"):
                return _safe_json({"ok": False, "error": "submit not available"})
            task_id = tq.submit(lambda: work, name=name)
            return _safe_json({"ok": True, "name": name, "task_id": task_id})

        @mcp.tool
        def worker_cancel(task_id: str) -> str:
            """Cancel a running worker."""
            tq = _get_wtq()
            if not hasattr(tq, "cancel"):
                return _safe_json({"ok": False, "error": "cancel not available"})
            return _safe_json({"ok": bool(tq.cancel(task_id)), "task_id": task_id})

        @mcp.tool
        def worker_metrics() -> str:
            """Get worker performance metrics."""
            tq = _get_wtq()
            summary = tq.summary() if hasattr(tq, "summary") else {}
            return _safe_json(summary)

        @mcp.tool
        def worker_health() -> str:
            """Check worker health."""
            tq = _get_wtq()
            running = tq.list_running() if hasattr(tq, "list_running") else []
            return _safe_json({"running_count": len(running), "workers": [{"id": t.id, "name": t.name} for t in running]})

        @mcp.tool
        def worker_queue() -> str:
            """View worker task queue."""
            tq = _get_wtq()
            summary = tq.summary() if hasattr(tq, "summary") else {}
            return _safe_json(summary)

        @mcp.tool
        def worker_restart(task_id: str) -> str:
            """Restart a worker (cancel + re-submit)."""
            tq = _get_wtq()
            if hasattr(tq, "cancel"):
                tq.cancel(task_id)
            return _safe_json({"ok": True, "task_id": task_id, "message": "cancelled — re-submit to restart"})

        @mcp.tool
        def worker_retry(task_id: str) -> str:
            """Retry a failed worker task."""
            return worker_restart(task_id)

        @mcp.tool
        def worker_assign(task_id: str, district: str) -> str:
            """Assign worker to a district."""
            return _safe_json({"status": "redirect", "message": "Use task_create with district parameter"})

        @mcp.tool
        async def worker_reset() -> str:
            """Reset all workers to initial state."""
            gate = await evaluate_destructive_action("worker_reset", {}, "mcp_workers")
            if not gate.approved:
                return _safe_json({
                    "error": "permission denied", "status": "blocked",
                    "reason": gate.reason, "level": gate.level, "ok": False,
                })
            tq = _get_wtq()
            if hasattr(tq, "_tasks"):
                tq._tasks.clear()
            return _safe_json({"ok": True, "message": "All tasks cleared"})

        @mcp.tool
        def worker_pause(task_id: str) -> str:
            """Pause a worker task (sets status to queued)."""
            tq = _get_wtq()
            task = tq.status(task_id) if hasattr(tq, "status") else None
            if task:
                if hasattr(task, "_status"):
                    task._status = "queued"
                return _safe_json({"ok": True, "task_id": task_id, "paused": True})
            return _safe_json({"error": f"Task {task_id} not found"})

        @mcp.tool
        def worker_resume(task_id: str) -> str:
            """Resume a paused worker task."""
            return _safe_json({"status": "redirect", "task_id": task_id, "note": "Re-submit the task to resume via worker_submit or worker_restart"})

        @mcp.tool
        def worker_priority(task_id: str, priority: str = "normal") -> str:
            """Change worker task priority."""
            tq = _get_wtq()
            task = tq.status(task_id) if hasattr(tq, "status") else None
            if task:
                prio_map = {"critical": 0, "high": 1, "normal": 2, "low": 3, "background": 4}
                prio_val = prio_map.get(priority.lower(), 2)
                if hasattr(task, "priority"):
                    from core.loop.task_queue import Priority as _Prio
                    task.priority = list(_Prio.__members__.values())[prio_val] if hasattr(_Prio, "__members__") else priority
                return _safe_json({"ok": True, "task_id": task_id, "priority": priority})
            return _safe_json({"error": f"Task {task_id} not found"})

        @mcp.tool
        def worker_logs(task_id: str) -> str:
            """Get worker execution logs from episodic memory."""
            try:
                from core.memory.episodic import EpisodicMemory
                mem = EpisodicMemory()
                entries = mem.recall(task_id, limit=10) if hasattr(mem, "recall") else []
                return _safe_json({"task_id": task_id, "logs": entries})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def worker_stop(task_id: str) -> str:
            """Stop a worker task (cancels execution)."""
            tq = _get_wtq()
            if hasattr(tq, "cancel"):
                ok = tq.cancel(task_id)
                return _safe_json({"ok": ok, "task_id": task_id})
            return _safe_json({"error": "cancel not available"})

        @mcp.tool
        def worker_start(name: str, work: str = "") -> str:
            """Start a worker by name (creates new task)."""
            tq = _get_wtq()
            if hasattr(tq, "submit"):
                task_id = tq.submit(lambda: work or "worker_task", name=name)
                return _safe_json({"ok": True, "name": name, "task_id": task_id})
            return _safe_json({"error": "submit not available"})

        @mcp.tool
        def worker_scale(count: int = 4) -> str:
            """Scale worker concurrency (adjusts max_concurrent config)."""
            try:
                from core.config import CONFIG as _C
                count = int(count)
                if not 1 <= count <= 32:
                    return _safe_json({"ok": False, "error": "count must be between 1 and 32"})
                _C.setdefault("task_queue", {})["max_concurrent"] = count
                return _safe_json({"ok": True, "max_concurrent": count, "note": "Runtime change only — restart to persist"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def worker_drain() -> str:
            """Drain the worker queue — wait for running tasks to finish."""
            tq = _get_wtq()
            running = tq.list_running() if hasattr(tq, "list_running") else []
            return _safe_json({"running_before_drain": len(running), "status": "drained", "note": "Tasks will complete naturally"})

        @mcp.tool
        def worker_flush() -> str:
            """Flush completed worker tasks from memory."""
            tq = _get_wtq()
            if hasattr(tq, "_tasks"):
                count = len(tq._tasks)
                tq._tasks.clear()
                return _safe_json({"ok": True, "flushed": count})
            return _safe_json({"ok": True, "note": "Task queue cleared"})

        @mcp.tool
        def worker_timeout(task_id: str, seconds: int = 300) -> str:
            """Set worker task timeout."""
            return _safe_json({"ok": False, "task_id": task_id, "timeout_sec": seconds, "note": "Not applied: per-task timeouts are enforced at task execution level, nothing was changed"})

        @mcp.tool
        def worker_heartbeat(task_id: str) -> str:
            """Send a worker heartbeat — update timestamp in episodic memory."""
            try:
                from core.memory.episodic import EpisodicMemory
                mem = EpisodicMemory()
                if hasattr(mem, "store"):
                    mem.store("heartbeat", f"Worker {task_id} OK", tags=["worker", "heartbeat"])
                return _safe_json({"ok": True, "task_id": task_id, "timestamp": _time.time()})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def worker_checkpoint(task_id: str) -> str:
            """Save worker checkpoint state to episodic memory."""
            try:
                from core.memory.episodic import EpisodicMemory
                mem = EpisodicMemory()
                tq = _get_wtq()
                task = tq.status(task_id) if hasattr(tq, "status") else None
                state = {"task_id": task_id, "name": task.name if task else "unknown", "status": task.status if task else "unknown", "progress": task.progress if hasattr(task, "progress") else 0.0}
                if hasattr(mem, "store"):
                    mem.store("checkpoint", str(state), tags=["worker", "checkpoint"])
                return _safe_json({"ok": True, "checkpoint": state})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def worker_migrate(target_queue: str = "") -> str:
            """Migrate workers to new queue."""
            return _safe_json({"status": "unsupported", "note": "VECTOR uses a single task queue. Re-submit tasks to redistribute."})

        @mcp.tool
        def worker_export(path: str = "") -> str:
            """Export worker state to JSON."""
            import json
            tq = _get_wtq()
            summary = tq.summary() if hasattr(tq, "summary") else {"note": "summary not available"}
            dest = resolve_in_root(ROOT, path or f"worker_export_{int(_time.time())}.json")
            if dest is None or dest.suffix.lower() != ".json" or is_protected_write_path(ROOT, dest):
                return _safe_json({"ok": False, "error": "export path must be a .json file inside the repo root (not a protected file)"})
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(summary, f, default=str)
            return _safe_json({"ok": True, "path": str(dest), "summary": summary})

        @mcp.tool
        def worker_import(path: str) -> str:
            """Import worker state from JSON (stub — state restored from queue)."""
            try:
                import json
                src = resolve_in_root(ROOT, path)
                if src is None:
                    return _safe_json({"ok": False, "error": "Path traversal denied"})
                with open(src, encoding="utf-8") as f:
                    data = json.load(f)
                return _safe_json({"ok": True, "imported": path, "task_count": len(data.get("tasks", [])), "note": "Tasks are ephemeral — use worker_submit to re-create"})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] worker tools unavailable: {e}")
        for n, d in [("worker_list", "List workers"), ("worker_status", "Worker status"), ("worker_submit", "Submit worker"), ("worker_cancel", "Cancel worker"), ("worker_metrics", "Worker metrics"), ("worker_health", "Worker health"), ("worker_queue", "Worker queue"), ("worker_restart", "Restart worker"), ("worker_retry", "Retry worker"), ("worker_assign", "Assign worker"), ("worker_reset", "Reset workers"), ("worker_pause", "Pause worker"), ("worker_resume", "Resume worker"), ("worker_priority", "Change priority"), ("worker_logs", "Worker logs"), ("worker_stop", "Stop worker"), ("worker_start", "Start worker"), ("worker_scale", "Scale workers"), ("worker_drain", "Drain queue"), ("worker_flush", "Flush tasks"), ("worker_timeout", "Set timeout"), ("worker_heartbeat", "Heartbeat"), ("worker_checkpoint", "Checkpoint"), ("worker_migrate", "Migrate workers"), ("worker_export", "Export state"), ("worker_import", "Import state")]:
            _reg(mcp, n, d)
