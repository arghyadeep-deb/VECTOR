from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


def add_task_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ task_* (8) — wired to core/loop/task_queue.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.loop.task_queue import get_task_queue as _get_tq, Priority as _Priority

        @mcp.tool
        def task_list(status: str = "all", limit: int = 20) -> str:
            """List all tasks with status."""
            tq = _get_tq()
            if status == "running":
                tasks = tq.list_running() if hasattr(tq, "list_running") else []
            elif status == "recent":
                tasks = tq.list_recent(limit) if hasattr(tq, "list_recent") else []
            else:
                tasks = tq.list_recent(limit) if hasattr(tq, "list_recent") else []
            return _safe_json({"tasks": [{"id": t.id, "name": t.name, "status": t.status, "priority": t.priority.name if hasattr(t.priority, "name") else str(t.priority)} for t in tasks]})

        @mcp.tool
        def task_status(task_id: str) -> str:
            """Get detailed status of a specific task."""
            tq = _get_tq()
            status = tq.status(task_id) if hasattr(tq, "status") else None
            if status:
                return _safe_json({"id": task_id, "status": status.status, "progress": status.progress, "elapsed": status.elapsed})
            return _safe_json({"error": f"Task {task_id} not found"})

        @mcp.tool
        def task_update(task_id: str, progress: float = 0.0) -> str:
            """Update task progress (0.0-1.0)."""
            tq = _get_tq()
            if hasattr(tq, "update_progress"):
                tq.update_progress(task_id, progress)
            return _safe_json({"ok": True, "task_id": task_id, "progress": progress})

        @mcp.tool
        def task_delete(task_id: str) -> str:
            """Cancel/delete a task from the queue."""
            tq = _get_tq()
            if not hasattr(tq, "cancel"):
                return _safe_json({"ok": False, "error": "cancel not available"})
            return _safe_json({"ok": bool(tq.cancel(task_id)), "task_id": task_id})

        @mcp.tool
        def task_submit_bg(name: str, work: str = "") -> str:
            """Submit a background low-priority task."""
            tq = _get_tq()
            if hasattr(tq, "submit"):
                tq.submit(lambda: work, name=name, priority=_Priority.BACKGROUND)
            return _safe_json({"ok": True, "name": name, "priority": "background"})

        @mcp.tool
        def task_create(name: str, priority: str = "normal", district: str = "") -> str:
            """Create a new task in the queue."""
            tq = _get_tq()
            pri = getattr(_Priority, priority.upper(), _Priority.NORMAL)
            if hasattr(tq, "submit"):
                tq.submit(lambda: None, name=name, priority=pri, district=district)
            return _safe_json({"ok": True, "name": name, "priority": priority})

        @mcp.tool
        def task_assign(task_id: str, district: str) -> str:
            """Assign a task to a district."""
            return _safe_json({"status": "redirect", "message": "Use task_create with district parameter instead"})

        @mcp.tool
        def task_complete(task_id: str) -> str:
            """Mark a task as complete."""
            return _safe_json({"status": "redirect", "message": "VECTOR tasks complete automatically; use task_delete to remove"})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] task tools unavailable: {e}")
        for n, d in [("task_list", "List tasks"), ("task_status", "Task status"), ("task_update", "Update task"), ("task_delete", "Delete task"), ("task_submit_bg", "Submit BG task"), ("task_create", "Create task"), ("task_assign", "Assign task"), ("task_complete", "Complete task")]:
            _reg(mcp, n, d)
