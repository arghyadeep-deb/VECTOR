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


_ROOT = Path(__file__).resolve().parents[3]  # module-level so tests can point it at a tmp dir


def add_hook_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _ROOT

    # â”€â”€ hook_* (17) — wired to core/brain_hooks/ and core/coding_assistant/ â”€â”€â”€
    try:
        from core.brain_hooks import run_hook as _run_hook_raw
        import re as _re

        _HOOK_NAME_RE = _re.compile(r"^[a-z][a-z0-9_-]*$")

        def _run_hook(hook_name: str, data: str = ""):
            """run_hook builds `<hooks_dir>/<name>.ts` and runs it under node: an unvalidated
            name such as '../../x' would execute an arbitrary .ts file. Returns a dict that
            reports the exit code instead of hiding it in a tuple."""
            if not _HOOK_NAME_RE.match(hook_name or ""):
                return {"ok": False, "error": f"invalid hook name: {hook_name!r}"}
            out, code = _run_hook_raw(hook_name, data)
            return {"ok": code == 0, "exit_code": code, "output": out}

        @mcp.tool
        def hook_fire(hook_name: str, payload: str = "{}") -> str:
            """Fire a hook with a JSON payload."""
            result = _run_hook(hook_name, payload)
            return _safe_json({"hook": hook_name, "result": result})

        @mcp.tool
        def hook_session_start(data: str = "{}") -> str:
            """Fire SESSION_START hook."""
            return _safe_json({"hook": "session-start", "result": _run_hook("session-start", data)})

        @mcp.tool
        def hook_session_end(data: str = "{}") -> str:
            """Fire SESSION_END hook."""
            return _safe_json({"hook": "stop-checklist", "result": _run_hook("stop-checklist", data)})

        @mcp.tool
        def hook_intelligence(data: str = "{}") -> str:
            """Fire INTELLIGENCE hook."""
            return _safe_json({"hook": "intelligence", "result": _run_hook("intelligence", data)})

        @mcp.tool
        def hook_session_restore(data: str = "{}") -> str:
            """Fire SESSION_RESTORE hook."""
            return _safe_json({"hook": "session-restore", "result": _run_hook("session-restore", data)})

        @mcp.tool
        def hook_notify(message: str) -> str:
            """Fire NOTIFY hook via permission gateway."""
            try:
                from core.loop.permission_gateway import PermissionGateway
                pg = PermissionGateway()
                import asyncio as _asyncio
                coro = pg.notify(message)  # async: calling it alone never sends anything
                try:
                    _asyncio.get_running_loop().create_task(coro)
                except RuntimeError:
                    _asyncio.run(coro)
                return _safe_json({"ok": True})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def hook_task_complete(task_id: str, result: str = "{}") -> str:
            """Fire TASK_COMPLETE hook callback."""
            try:
                from core.loop.task_queue import get_task_queue
                tq = get_task_queue()
                if not hasattr(tq, "_on_complete"):
                    return _safe_json({"ok": False, "error": "task queue has no completion callback; nothing fired"})
                tq._on_complete(task_id, result)
                return _safe_json({"ok": True})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def hook_list() -> str:
            """List available hook types."""
            hooks = ["session-start", "stop-checklist", "intelligence", "session-restore", "pre_edit", "post_edit", "pre_task", "post_task", "route", "notify", "task_complete", "post_command", "transfer"]
            return _safe_json({"hooks": hooks})

        @mcp.tool
        def hook_register(hook_name: str, handler: str) -> str:
            """Register a handler for a hook (stub — requires hooks manager config)."""
            return _safe_json({"ok": False, "status": "unsupported", "hook": hook_name, "note": "hook registration is not implemented; nothing was registered"})

        @mcp.tool
        def hook_pre_edit(file_path: str) -> str:
            """Fire PRE_EDIT hook before file modification."""
            return _safe_json({"hook": "pre_edit", "file": file_path})

        @mcp.tool
        def hook_post_edit(file_path: str) -> str:
            """Fire POST_EDIT hook after file modification."""
            return _safe_json({"hook": "post_edit", "file": file_path})

        @mcp.tool
        def hook_pre_task(task: str) -> str:
            """Fire PRE_TASK hook."""
            return _safe_json({"hook": "pre_task", "task": task})

        @mcp.tool
        def hook_post_task(task: str) -> str:
            """Fire POST_TASK hook."""
            return _safe_json({"hook": "post_task", "task": task})

        @mcp.tool
        def hook_route(task_type: str) -> str:
            """Fire ROUTE hook for task routing."""
            return _safe_json({"hook": "route", "task_type": task_type})

        @mcp.tool
        def hook_explain(context: str) -> str:
            """Fire EXPLAIN hook for code explanation."""
            return _safe_json({"hook": "explain", "context": context[:200]})

        @mcp.tool
        def hook_post_command(command: str) -> str:
            """Fire POST_COMMAND hook."""
            return _safe_json({"hook": "post_command", "command": command})

        @mcp.tool
        def hook_transfer(from_agent: str, to_agent: str) -> str:
            """Fire TRANSFER hook for agent handoff."""
            return _safe_json({"hook": "transfer", "from": from_agent, "to": to_agent})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] hook tools unavailable: {e}")
        for n, d in [("hook_fire", "Fire hook"), ("hook_session_start", "Session start"), ("hook_session_end", "Session end"), ("hook_intelligence", "Intelligence hook"), ("hook_session_restore", "Session restore"), ("hook_notify", "Notify hook"), ("hook_task_complete", "Task complete"), ("hook_list", "List hooks"), ("hook_register", "Register hook"), ("hook_pre_edit", "Pre-edit hook"), ("hook_post_edit", "Post-edit hook"), ("hook_pre_task", "Pre-task hook"), ("hook_post_task", "Post-task hook"), ("hook_route", "Route hook"), ("hook_explain", "Explain hook"), ("hook_post_command", "Post-command hook"), ("hook_transfer", "Transfer hook")]:
            _reg(mcp, n, d)
