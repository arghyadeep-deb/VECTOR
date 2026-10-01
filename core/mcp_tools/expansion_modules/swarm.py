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


def add_swarm_tools(mcp) -> None:
    import inspect as _inspect
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ swarm_* (9) — wired to core/swarm/orchestrator.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.swarm.orchestrator import get_orchestrator as _get_orch

        @mcp.tool
        def swarm_init(topology: str = "flat") -> str:
            """Initialise swarm with topology (flat/hierarchical)."""
            orch = _get_orch()
            return _safe_json({"status": "loaded", "swarms": list(orch.get_swarm().keys()) if hasattr(orch, "get_swarm") else []})

        @mcp.tool
        def swarm_submit(task_type: str, params: str = "{}") -> str:
            """Submit a task to the swarm for execution."""
            import json as _j
            orch = _get_orch()
            p = _j.loads(params) if params else {}
            if not hasattr(orch, "dispatch"):
                return _safe_json({"ok": False, "error": "orchestrator has no dispatch(); task NOT submitted"})
            return _safe_json(orch.dispatch(task_type, p))

        @mcp.tool
        def swarm_execute(tasks: str = "[]") -> str:
            """Execute multiple tasks in parallel via swarm."""
            import json as _j
            orch = _get_orch()
            task_list = _j.loads(tasks) if tasks else []
            if not hasattr(orch, "parallel_dispatch"):
                return _safe_json({"ok": False, "error": "orchestrator has no parallel_dispatch(); tasks NOT executed"})
            if not isinstance(task_list, list) or len(task_list) > 20:
                return _safe_json({"ok": False, "error": "tasks must be a JSON list of at most 20 items"})
            result = orch.parallel_dispatch(task_list)
            if _inspect.isawaitable(result):
                # async orchestrator: a sync tool cannot await it; an unawaited coroutine is not a result
                if hasattr(result, "close"):
                    result.close()
                return _safe_json({"ok": False, "error": "parallel_dispatch is async and was not run; tasks NOT executed"})
            return _safe_json(result)

        @mcp.tool
        def swarm_status() -> str:
            """Get current swarm status and agent count."""
            orch = _get_orch()
            swarms = orch.get_swarm() if hasattr(orch, "get_swarm") else {}
            return _safe_json({"swarm_count": len(swarms), "swarms": list(swarms.keys())})

        @mcp.tool
        def swarm_topology() -> str:
            """Get current swarm topology configuration."""
            from core.swarm.orchestrator import DISTRICT_SWARMS, GENERIC_DISTRICTS
            return _safe_json({"district_swarms": list(DISTRICT_SWARMS.keys()) if isinstance(DISTRICT_SWARMS, dict) else [], "generic_districts": GENERIC_DISTRICTS})

        @mcp.tool
        def swarm_agents() -> str:
            """List agents grouped by domain."""
            orch = _get_orch()
            swarms = orch.get_swarm() if hasattr(orch, "get_swarm") else {}
            result = {}
            for name, swarm in swarms.items():
                agents = getattr(swarm, "_agents", [])
                result[name] = [{"id": a.id, "role": getattr(a, "role", "")} for a in agents]
            return _safe_json(result)

        @mcp.tool
        def swarm_report() -> str:
            """Generate a swarm execution summary."""
            orch = _get_orch()
            swarms = orch.get_swarm() if hasattr(orch, "get_swarm") else {}
            return _safe_json({"swarm_count": len(swarms), "status": "active"})

        @mcp.tool
        def swarm_assign(swarm_name: str, task: str) -> str:
            """Assign a subtask to a specific swarm."""
            orch = _get_orch()
            swarms = orch.get_swarm() if hasattr(orch, "get_swarm") else {}
            if swarm_name not in swarms:
                return _safe_json({"error": f"Swarm '{swarm_name}' not found"})
            swarm = swarms[swarm_name]
            if hasattr(swarm, "dispatch"):
                result = swarm.dispatch(task)
            else:
                result = {"status": "assigned", "swarm": swarm_name}
            return _safe_json(result)

        @mcp.tool
        def swarm_shutdown() -> str:
            """Shut down all swarm agents."""
            orch = _get_orch()
            if hasattr(orch, "_swarms"):
                orch._swarms.clear()
            return _safe_json({"ok": True, "message": "All swarms cleared"})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] swarm tools unavailable: {e}")
        for n, d in [("swarm_init", "Init swarm"), ("swarm_submit", "Submit task"), ("swarm_execute", "Execute tasks"), ("swarm_status", "Swarm status"), ("swarm_topology", "Get topology"), ("swarm_agents", "List agents"), ("swarm_report", "Execution report"), ("swarm_assign", "Assign task"), ("swarm_shutdown", "Shutdown swarms")]:
            _reg(mcp, n, d)
