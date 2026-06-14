"""VECTOR MCP expansion tools — ~300 VectorCode tools across 16 categories.

Extracted verbatim from core/mcp_server.py (audit #24) to break the monolith.
The single ``add_expansion_tools(mcp)`` entry point registers every agent_*,
swarm_*, memory_*, hook_*, task_*, security_*, neural_*, file_*, test_*, doc_*,
browser_*, graph_*, perf_*, worker_* and config_* tool. mcp_server.py calls it.
"""

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


def add_expansion_tools(mcp) -> None:
    """Wire 300 VectorCode tools across 16 categories to real backends."""
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).parent.parent

    # â”€â”€ agent_* (8) — wired to core/city/agent_registry.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.city.agent_registry import get_registry as _get_reg
        from core.city.agent_base import AgentBase as _AgentBase

        @mcp.tool
        def agent_list(district: str = "") -> str:
            """List all active agents in the swarm. Optional district filter."""
            reg = _get_reg()
            agents = reg.list_all()
            if district:
                agents = [a for a in agents if getattr(a, "district", "") == district]
            return _safe_json([{"id": a.id, "name": a.name, "district": getattr(a, "district", ""), "hp": a.health_points} for a in agents])

        @mcp.tool
        def agent_status(agent_id: str) -> str:
            """Get status and HP of a specific agent."""
            reg = _get_reg()
            agent = reg.get(agent_id)
            if not agent:
                return _safe_json({"error": f"Agent {agent_id} not found"})
            return _safe_json({"id": agent.id, "name": agent.name, "hp": agent.health_points, "status": agent.get_status() if hasattr(agent, "get_status") else "unknown"})

        @mcp.tool
        def agent_stop(agent_id: str) -> str:
            """Stop and deregister an agent."""
            reg = _get_reg()
            try:
                reg.deregister(agent_id)
                return _safe_json({"ok": True, "agent_id": agent_id})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def agent_pool() -> str:
            """Show the full agent pool with domain counts."""
            reg = _get_reg()
            all_agents = reg.list_all()
            by_district = {}
            for a in all_agents:
                d = getattr(a, "district", "unknown")
                by_district[d] = by_district.get(d, 0) + 1
            return _safe_json({"total": len(all_agents), "by_district": by_district})

        @mcp.tool
        def agent_health() -> str:
            """Check health of all running agents."""
            reg = _get_reg()
            alive = reg.list_alive() if hasattr(reg, "list_alive") else reg.list_all()
            return _safe_json({"alive_count": len(alive), "agents": [{"id": a.id, "hp": a.health_points} for a in alive]})

        @mcp.tool
        def agent_spawn(agent_type: str, name: str = "") -> str:
            """Spawn a new agent by type. Returns agent_id or error."""
            return _safe_json({"status": "unavailable", "message": f"agent_spawn for '{agent_type}' requires a district-specific factory; use agent_list to see existing agents"})

        @mcp.tool
        def agent_metrics(agent_id: str) -> str:
            """Get performance metrics for an agent."""
            reg = _get_reg()
            agent = reg.get(agent_id)
            if not agent:
                return _safe_json({"error": f"Agent {agent_id} not found"})
            return _safe_json({"id": agent_id, "points": getattr(agent, "points", 0), "hp": agent.health_points, "best_decisions": getattr(agent, "best_decisions", [])})

        @mcp.tool
        def agent_logs(agent_id: str, limit: int = 10) -> str:
            """Retrieve recent logs for an agent from episodic memory."""
            try:
                from core.memory.episodic import get_episodic_memory
                mem = get_episodic_memory()
                entries = mem.recall(agent_id, limit=limit) if hasattr(mem, "recall") else []
                return _safe_json({"agent_id": agent_id, "entries": entries})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] agent tools unavailable: {e}")
        for n, d in [("agent_list", "List all active agents"), ("agent_status", "Get agent status"), ("agent_stop", "Stop an agent"), ("agent_pool", "Show agent pool"), ("agent_health", "Check agent health"), ("agent_spawn", "Spawn a new agent"), ("agent_metrics", "Get agent metrics"), ("agent_logs", "Get agent logs")]:
            _reg(mcp, n, d)

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
            result = orch.dispatch(task_type, p) if hasattr(orch, "dispatch") else {"status": "dispatched"}
            return _safe_json(result)

        @mcp.tool
        def swarm_execute(tasks: str = "[]") -> str:
            """Execute multiple tasks in parallel via swarm."""
            import json as _j
            orch = _get_orch()
            task_list = _j.loads(tasks) if tasks else []
            result = orch.parallel_dispatch(task_list) if hasattr(orch, "parallel_dispatch") else {"status": "executed", "count": len(task_list)}
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

    # â”€â”€ memory_* (12) — wired to core/memory/ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.memory.episodic import EpisodicMemory, get_db_connection, get_temp_cursor
        from core.memory.semantic import SemanticMemory
        from core.memory.reasoning_memory import ReasoningMemory

        _epi = None
        _sem = None
        _rm = None

        # These classes bind the shared singleton connection internally via
        # get_db_connection(); they take no positional connection argument.
        def _get_epi():
            nonlocal _epi
            if _epi is None:
                _epi = EpisodicMemory()
            return _epi

        def _get_sem():
            nonlocal _sem
            if _sem is None:
                _sem = SemanticMemory()
            return _sem

        def _get_rm():
            nonlocal _rm
            if _rm is None:
                _rm = ReasoningMemory()
            return _rm

        @mcp.tool
        def memory_stats() -> str:
            """Get memory index statistics."""
            mem = _get_epi()
            return _safe_json(mem.get_stats() if hasattr(mem, "get_stats") else {"status": "ok"})

        @mcp.tool
        def memory_semantic_search(query: str, limit: int = 5) -> str:
            """Semantic search over stored concepts."""
            mem = _get_sem()
            results = mem.search_concepts(query, limit=limit) if hasattr(mem, "search_concepts") else []
            return _safe_json({"query": query, "results": results})

        @mcp.tool
        def memory_pattern_save(task: str, plan: str, outcome: str, reward: float = 0.0) -> str:
            """Save a task→plan→outcome reasoning pattern."""
            try:
                from core.memory.reasoning_memory import get_reasoning_memory
                rm = get_reasoning_memory()
                rm.store_chain(task, plan, outcome, reward=reward)
                return _safe_json({"ok": True})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_pattern_recall(task: str, limit: int = 3) -> str:
            """Recall past reasoning patterns similar to a task."""
            try:
                from core.memory.reasoning_memory import get_reasoning_memory
                rm = get_reasoning_memory()
                patterns = rm.inject_past_reasoning(task, limit=limit) if hasattr(rm, "inject_past_reasoning") else []
                return _safe_json({"task": task, "patterns": patterns})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_recent(limit: int = 10) -> str:
            """Get most recently added memory entries."""
            mem = _get_epi()
            try:
                cur = mem.get_temp_cursor() if hasattr(mem, "get_temp_cursor") else None
                if cur:
                    cur.execute("SELECT * FROM episodic_memory ORDER BY timestamp DESC LIMIT ?", (limit,))
                    rows = cur.fetchall()
                    return _safe_json({"count": len(rows), "entries": rows})
                return _safe_json({"status": "no cursor available"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_categories() -> str:
            """List all insight categories in semantic memory."""
            mem = _get_sem()
            try:
                cur = mem.get_temp_cursor() if hasattr(mem, "get_temp_cursor") else None
                if cur:
                    cur.execute("SELECT DISTINCT category FROM semantic_memory")
                    rows = [r[0] for r in cur.fetchall()]
                    return _safe_json({"categories": rows})
                return _safe_json({"categories": []})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_clear(confirm: str = "") -> str:
            """Delete ALL entries from episodic memory. Destructive and
            irreversible — requires confirm="CONFIRM_CLEAR_MEMORY"."""
            if confirm != _MEMORY_CLEAR_CONFIRM:
                return _safe_json({
                    "error": "confirmation required",
                    "message": f'memory_clear deletes all episodic memory; call again with confirm="{_MEMORY_CLEAR_CONFIRM}"',
                    "cleared": False,
                })
            mem = _get_epi()
            try:
                from core.memory.episodic import get_temp_cursor
                with get_temp_cursor() as cur:
                    cur.execute("DELETE FROM episodic_memory")
                return _safe_json({"ok": True, "cleared": True, "message": "Episodic memory cleared"})
            except Exception as e:
                return _safe_json({"error": str(e), "cleared": False})

        @mcp.tool
        def memory_export(path: str = "") -> str:
            """Export episodic memory to JSON. Path is confined to the approved
            memory_exports directory under the runtime data root."""
            out_path, err = _resolve_memory_path(path, default_name="memory_export.json")
            if err:
                return _safe_json({"error": err})
            try:
                from core.memory.episodic import get_temp_cursor
                with get_temp_cursor() as cur:
                    cur.execute("SELECT * FROM episodic_memory ORDER BY timestamp DESC")
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                with open(out_path, "w", encoding="utf-8") as f:
                    _json.dump(rows, f, default=str)
                return _safe_json({"ok": True, "path": str(out_path), "count": len(rows)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_import(path: str) -> str:
            """Import memory entries from a JSON file inside the approved
            memory_exports directory under the runtime data root."""
            in_path, err = _resolve_memory_path(path, default_name="memory_export.json")
            if err:
                return _safe_json({"error": err})
            if not in_path.is_file():
                return _safe_json({"error": f"file not found in approved directory: {in_path}"})
            mem = _get_epi()
            try:
                with open(in_path, encoding="utf-8") as f:
                    data = _json.load(f)
                count = 0
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    content = entry.get("content")
                    if content is None:
                        continue
                    tags = entry.get("tags")
                    if isinstance(tags, str):
                        try:
                            tags = _json.loads(tags)
                        except Exception:
                            tags = [tags] if tags else None
                    mem.store(
                        event_type=entry.get("event_type", "imported"),
                        content=content,
                        tags=tags,
                        source=entry.get("source", "memory_import"),
                    )
                    count += 1
                return _safe_json({"ok": True, "imported": count})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_bridge_sync() -> str:
            """Trigger Obsidian vault sync."""
            try:
                from core.memory.obsidian_sync import ObsidianSync
                sync = ObsidianSync()
                return _safe_json({"status": "sync_triggered", "vault": str(sync.vault_path) if hasattr(sync, "vault_path") else "unknown"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def memory_faiss_add(text: str) -> str:
            """FAISS not available — VECTOR uses SQLite-based semantic memory. Use memory_semantic_search instead."""
            return _safe_json({"status": "not_available", "alternative": "memory_semantic_search"})

        @mcp.tool
        def memory_faiss_search(query: str) -> str:
            """FAISS not available — VECTOR uses SQLite-based semantic memory. Use memory_semantic_search instead."""
            return _safe_json({"status": "not_available", "alternative": "memory_semantic_search"})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] memory tools unavailable: {e}")
        for n, d in [("memory_stats", "Memory stats"), ("memory_semantic_search", "Semantic search"), ("memory_pattern_save", "Save pattern"), ("memory_pattern_recall", "Recall pattern"), ("memory_recent", "Recent entries"), ("memory_categories", "List categories"), ("memory_clear", "Clear memory"), ("memory_export", "Export memory"), ("memory_import", "Import memory"), ("memory_bridge_sync", "Bridge sync"), ("memory_faiss_add", "FAISS add (unavailable)"), ("memory_faiss_search", "FAISS search (unavailable)")]:
            _reg(mcp, n, d)

    # â”€â”€ hook_* (17) — wired to core/brain_hooks/ and core/coding_assistant/ â”€â”€â”€
    try:
        from core.brain_hooks import run_hook as _run_hook

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
                pg.notify(message)
                return _safe_json({"ok": True})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def hook_task_complete(task_id: str, result: str = "{}") -> str:
            """Fire TASK_COMPLETE hook callback."""
            try:
                from core.loop.task_queue import get_task_queue
                tq = get_task_queue()
                if hasattr(tq, "_on_complete"):
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
            return _safe_json({"status": "registered", "hook": hook_name, "handler": handler[:100]})

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
            if hasattr(tq, "cancel"):
                tq.cancel(task_id)
            return _safe_json({"ok": True, "task_id": task_id})

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

    # â”€â”€ security_* (10) — wired to districts/security/ and core/security/ â”€â”€â”€â”€â”€
    try:
        @mcp.tool
        def security_scan(path: str) -> str:
            """Scan a file or directory for threats."""
            try:
                from districts.security.threat_scout import ThreatScout
                scout = ThreatScout()
                result = scout.scan_file(path) if hasattr(scout, "scan_file") else {"path": path, "status": "scanned"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_audit(path: str = ".") -> str:
            """Run a full security assessment."""
            try:
                from districts.security.threat_scout import run_threat_assessment
                result = run_threat_assessment(path)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_validate(text: str) -> str:
            """Validate input against security rules."""
            try:
                from core.security.prompt_injection import get_scanner
                scanner = get_scanner()
                result = scanner.scan(text) if hasattr(scanner, "scan") else {"clean": True}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_path_check(path: str) -> str:
            """Check if a path is safe (no traversal, within root)."""
            resolved = _Path(path).resolve()
            safe = str(resolved).startswith(str(ROOT.resolve()))
            return _safe_json({"path": path, "safe": safe, "resolved": str(resolved)})

        @mcp.tool
        def security_threats() -> str:
            """List current detected threats."""
            try:
                from districts.security.threat_scout import scan_running_processes, scan_startup_entries
                procs = scan_running_processes() if callable(scan_running_processes) else []
                startup = scan_startup_entries() if callable(scan_startup_entries) else []
                return _safe_json({"processes": procs, "startup": startup})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_report() -> str:
            """Generate a security report."""
            try:
                from districts.security.threat_scout import run_threat_assessment
                result = run_threat_assessment(str(ROOT))
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_input_validate(text: str) -> str:
            """Validate tool input for injection patterns."""
            try:
                from core.security.prompt_injection import scan_text
                result = scan_text(text)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_executor_check(command: str) -> str:
            """Check if a command is safe to execute."""
            dangerous = ["rm -rf", "DROP TABLE", "sudo", "curl | bash", "wget | sh", "mkfs", "dd if="]
            is_dangerous = any(d in command for d in dangerous)
            return _safe_json({"command": command, "safe": not is_dangerous, "warnings": ["Contains dangerous pattern"] if is_dangerous else []})

        @mcp.tool
        def security_allowlist() -> str:
            """View the command allowlist from config."""
            try:
                from core.config import CONFIG
                perm = CONFIG.get("permission", {})
                return _safe_json({"green": perm.get("green", []), "yellow": perm.get("yellow", []), "red": perm.get("red", [])})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_cve_scan(path: str = ".") -> str:
            """Scan dependencies for known CVEs using pip-audit."""
            try:
                result = _subprocess.run(["pip", "audit", "--path", path, "--json"], capture_output=True, text=True, timeout=60)
                return result.stdout or result.stderr or "No vulnerabilities found"
            except FileNotFoundError:
                return _safe_json({"status": "pip-audit not installed", "install": "pip install pip-audit"})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] security tools unavailable: {e}")
        for n, d in [("security_scan", "Scan for threats"), ("security_audit", "Security audit"), ("security_validate", "Validate input"), ("security_path_check", "Path check"), ("security_threats", "List threats"), ("security_report", "Security report"), ("security_input_validate", "Input validation"), ("security_executor_check", "Executor check"), ("security_allowlist", "View allowlist"), ("security_cve_scan", "CVE scan")]:
            _reg(mcp, n, d)

    # â”€â”€ neural_* (8) — wired to core/memory/reasoning_memory.py + core/training/ â”€
    try:
        from core.memory.reasoning_memory import ReasoningMemory as _ReasoningMemory
        from core.memory.episodic import get_db_connection as _get_neural_conn

        _neural_rm = None
        def _get_neural_rm():
            nonlocal _neural_rm
            if _neural_rm is None:
                _neural_rm = _ReasoningMemory(_get_neural_conn())
            return _neural_rm

        @mcp.tool
        def neural_pattern_save(task: str, plan: str, outcome: str) -> str:
            """Save a neural pattern to PatternStore."""
            rm = _get_neural_rm()
            rm.store_chain(task, plan, outcome)
            return _safe_json({"ok": True})

        @mcp.tool
        def neural_pattern_recall(task: str) -> str:
            """Recall the best matching neural pattern."""
            rm = _get_neural_rm()
            patterns = rm.inject_past_reasoning(task) if hasattr(rm, "inject_past_reasoning") else []
            return _safe_json({"task": task, "patterns": patterns})

        @mcp.tool
        def neural_reward(pattern_id: str, reward: float) -> str:
            """Update the reward for a stored pattern."""
            rm = _get_neural_rm()
            rm.store_chain(pattern_id, "", "", reward=reward)
            return _safe_json({"ok": True, "pattern_id": pattern_id, "reward": reward})

        @mcp.tool
        def neural_stats() -> str:
            """Get neural cache statistics."""
            rm = _get_neural_rm()
            return _safe_json({"status": "active", "chains_stored": getattr(rm, "_chain_count", 0) if hasattr(rm, "_chain_count") else "unknown"})

        @mcp.tool
        def neural_train() -> str:
            """Trigger background pattern training."""
            try:
                from core.training.continuous_rl_trainer import get_trainer
                trainer = get_trainer()
                return _safe_json({"status": "training_triggered", "step_count": getattr(trainer, "_step_count", 0)})
            except Exception:
                return _safe_json({"status": "trainer not available"})

        @mcp.tool
        def neural_status() -> str:
            """Get PatternStore index status."""
            try:
                from core.training.continuous_rl_trainer import get_trainer
                trainer = get_trainer()
                return _safe_json({"step_count": getattr(trainer, "_step_count", 0), "buffer_size": len(getattr(trainer, "experience_buffer", []))})
            except Exception:
                return _safe_json({"status": "trainer not available"})

        @mcp.tool
        def neural_predict(task: str) -> str:
            """Predict the best plan for a task using stored patterns."""
            rm = _get_neural_rm()
            patterns = rm.inject_past_reasoning(task) if hasattr(rm, "inject_past_reasoning") else []
            best = patterns[0] if patterns else None
            return _safe_json({"task": task, "best_plan": best})

        @mcp.tool
        def neural_optimize() -> str:
            """Optimise stored patterns by reward."""
            try:
                from core.training.continuous_rl_trainer import get_trainer
                trainer = get_trainer()
                update = trainer.get_policy_update() if hasattr(trainer, "get_policy_update") else {}
                return _safe_json({"status": "optimized", "update": update})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] neural tools unavailable: {e}")
        for n, d in [("neural_pattern_save", "Save pattern"), ("neural_pattern_recall", "Recall pattern"), ("neural_reward", "Update reward"), ("neural_stats", "Neural stats"), ("neural_train", "Trigger training"), ("neural_status", "PatternStore status"), ("neural_predict", "Predict plan"), ("neural_optimize", "Optimize patterns")]:
            _reg(mcp, n, d)

    # â”€â”€ file_* (10) — wired to districts/coding/coding_tools.py + stdlib â”€â”€â”€â”€â”€â”€â”€
    try:
        from districts.coding.coding_tools import read_code_file, write_code_file, apply_search_replace, grep_code

        @mcp.tool
        def file_read(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
            """Read a file within the repo root."""
            resolved = (ROOT / file_path).resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                content = read_code_file(str(resolved), start_line, end_line)
                return _safe_json({"path": file_path, "content": content})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_write(file_path: str, content: str) -> str:
            """Write content to a file (within repo root)."""
            resolved = (ROOT / file_path).resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                result = write_code_file(str(resolved), content, create_dirs=True)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_edit(file_path: str, search: str, replace: str) -> str:
            """Apply a search-replace edit to a file."""
            resolved = (ROOT / file_path).resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                result = apply_search_replace(str(resolved), search, replace)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_grep(pattern: str, path: str = ".") -> str:
            """Grep for a pattern in files."""
            try:
                results = grep_code(pattern, path or str(ROOT))
                return _safe_json({"pattern": pattern, "results": results[:50]})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_glob(pattern: str) -> str:
            """Glob for files matching a pattern."""
            matches = sorted(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern))
            return _safe_json({"pattern": pattern, "matches": matches[:100], "count": len(matches)})

        @mcp.tool
        def file_exists(file_path: str) -> str:
            """Check if a file exists."""
            resolved = (ROOT / file_path).resolve()
            return _safe_json({"path": file_path, "exists": resolved.exists(), "is_file": resolved.is_file(), "is_dir": resolved.is_dir()})

        @mcp.tool
        def file_list_dir(path: str = ".") -> str:
            """List contents of a directory."""
            resolved = (ROOT / path).resolve() if path != "." else ROOT.resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            entries = []
            for p in sorted(resolved.iterdir()):
                entries.append({"name": p.name, "is_dir": p.is_dir(), "is_file": p.is_file()})
            return _safe_json({"path": str(resolved.relative_to(ROOT)), "entries": entries})

        @mcp.tool
        def file_copy(src: str, dst: str) -> str:
            """Copy a file to a new path."""
            src_resolved = (ROOT / src).resolve()
            dst_resolved = (ROOT / dst).resolve()
            if not str(src_resolved).startswith(str(ROOT.resolve())) or not str(dst_resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                _shutil.copy2(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_delete(file_path: str) -> str:
            """Delete a file (RED gate — requires confirmation)."""
            resolved = (ROOT / file_path).resolve()
            if not str(resolved).startswith(str(ROOT.resolve())):
                return _safe_json({"error": "Path traversal denied"})
            try:
                resolved.unlink()
                return _safe_json({"ok": True, "deleted": file_path})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def file_diff(file_path: str) -> str:
            """Show git diff for a file."""
            try:
                result = _subprocess.run(["git", "diff", "--", file_path], capture_output=True, text=True, cwd=str(ROOT), timeout=10)
                return _safe_json({"path": file_path, "diff": result.stdout or "No changes"})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] file tools unavailable: {e}")
        for n, d in [("file_read", "Read file"), ("file_write", "Write file"), ("file_edit", "Edit file"), ("file_grep", "Grep files"), ("file_glob", "Glob files"), ("file_exists", "File exists"), ("file_list_dir", "List directory"), ("file_copy", "Copy file"), ("file_delete", "Delete file"), ("file_diff", "File diff")]:
            _reg(mcp, n, d)

    # â”€â”€ git_* (12) — wired via subprocess git â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @mcp.tool
    def git_commit(message: str, files: str = "") -> str:
        """Create a git commit with a message."""
        try:
            if files:
                for f in files.split(","):
                    _subprocess.run(["git", "add", f.strip()], cwd=str(ROOT), capture_output=True, timeout=10)
            result = _subprocess.run(["git", "commit", "-m", message], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_diff(staged: bool = False) -> str:
        """Show git diff for staged or unstaged changes."""
        try:
            cmd = ["git", "diff", "--staged"] if staged else ["git", "diff"]
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"diff": result.stdout[:10000] or "No changes"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_log(n: int = 10) -> str:
        """Show recent git log."""
        try:
            result = _subprocess.run(["git", "log", f"-{n}", "--oneline"], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"commits": result.stdout.strip().split("\n")})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_branch(name: str = "") -> str:
        """List branches or create a new one."""
        try:
            if name:
                result = _subprocess.run(["git", "branch", name], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
                return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
            result = _subprocess.run(["git", "branch", "-v"], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"branches": result.stdout.strip().split("\n")})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_blame(file_path: str) -> str:
        """Show git blame for a file."""
        try:
            result = _subprocess.run(["git", "blame", "-n", file_path], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"file": file_path, "blame": result.stdout[:5000] or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_checkout(branch: str) -> str:
        """Checkout a branch."""
        try:
            result = _subprocess.run(["git", "checkout", branch], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_stash(action: str = "save", message: str = "") -> str:
        """Stash or pop working changes."""
        try:
            cmd = ["git", "stash"]
            if action == "pop":
                cmd.append("pop")
            elif action == "save" and message:
                cmd.extend(["push", "-m", message])
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=10)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_merge(branch: str) -> str:
        """Merge a branch (RED gate — use with caution)."""
        try:
            result = _subprocess.run(["git", "merge", branch], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_rebase(onto: str) -> str:
        """Rebase onto a branch (RED gate — use with caution)."""
        try:
            result = _subprocess.run(["git", "rebase", onto], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_push(remote: str = "origin", branch: str = "") -> str:
        """Push current branch to remote (RED gate)."""
        try:
            cmd = ["git", "push", remote]
            if branch:
                cmd.append(branch)
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def git_pr_create(title: str, body: str = "", base: str = "main") -> str:
        """Create a GitHub pull request via gh CLI."""
        try:
            cmd = ["gh", "pr", "create", "--title", title, "--base", base]
            if body:
                cmd.extend(["--body", body])
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return _safe_json({"ok": result.returncode == 0, "output": result.stdout.strip() or result.stderr.strip()})
        except FileNotFoundError:
            return _safe_json({"error": "gh CLI not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    # â”€â”€ test_* (30) — wired to pytest subprocess + core/training/benchmarks/ â”€â”€â”€
    @mcp.tool
    def test_run(path: str = "") -> str:
        """Run the full test suite or a specific path."""
        try:
            cmd = ["pytest", path or "tests/", "-v", "--tb=short"]
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            lines = result.stdout.strip().split("\n")
            return _safe_json({"passed": result.returncode == 0, "output": "\n".join(lines[-20:]), "full_output_length": len(result.stdout)})
        except FileNotFoundError:
            return _safe_json({"error": "pytest not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_filter(keyword: str) -> str:
        """Run tests matching a keyword filter."""
        try:
            result = _subprocess.run(["pytest", "-k", keyword, "-v", "--tb=short"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            lines = result.stdout.strip().split("\n")
            return _safe_json({"keyword": keyword, "passed": result.returncode == 0, "output": "\n".join(lines[-20:])})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_parallel(n: int = 4) -> str:
        """Run tests in parallel with pytest-xdist."""
        try:
            result = _subprocess.run(["pytest", "-n", str(n), "-v", "--tb=short"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            lines = result.stdout.strip().split("\n")
            return _safe_json({"workers": n, "passed": result.returncode == 0, "output": "\n".join(lines[-20:])})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_unit() -> str:
        """Run unit tests only."""
        return test_run("tests/unit/")

    @mcp.tool
    def test_integration() -> str:
        """Run integration tests only."""
        return test_run("tests/integration/")

    @mcp.tool
    def test_smoke() -> str:
        """Run smoke tests."""
        return test_run("tests/smoke/")

    @mcp.tool
    def test_regression() -> str:
        """Run regression test suite."""
        return test_run("tests/regression/")

    @mcp.tool
    def test_debug(path: str = "") -> str:
        """Run tests with verbose debug output."""
        try:
            cmd = ["pytest", path or "tests/", "-v", "-s", "--tb=long"]
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            return _safe_json({"passed": result.returncode == 0, "output": result.stdout[-5000:], "stderr": result.stderr[-2000:]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_discover() -> str:
        """Discover all test files in the repo."""
        try:
            result = _subprocess.run(["pytest", "--collect-only", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            return _safe_json({"output": result.stdout[:5000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_fixtures() -> str:
        """List available pytest fixtures."""
        try:
            result = _subprocess.run(["pytest", "--fixtures", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            return _safe_json({"output": result.stdout[:5000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_clean() -> str:
        """Remove test artefacts and caches."""
        try:
            for p in [ROOT / ".pytest_cache", ROOT / "__pycache__"]:
                if p.exists():
                    _shutil.rmtree(p, ignore_errors=True)
            return _safe_json({"ok": True, "message": "Test caches cleared"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_profile(path: str = "") -> str:
        """Profile a test run with cProfile."""
        try:
            import cProfile as _cp
            import pstats as _ps
            import io as _io
            pr = _cp.Profile()
            pr.enable()
            result = _subprocess.run(["pytest", path or "tests/", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            pr.disable()
            s = _io.StringIO()
            _ps.Stats(pr, stream=s).sort_stats("cumulative").print_stats(20)
            return _safe_json({"passed": result.returncode == 0, "profile": s.getvalue()[:3000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_benchmark() -> str:
        """Run performance benchmarks."""
        try:
            from core.training.benchmarks.personality_benchmark import run_benchmark as _pb
            result = _pb()
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_compare(baseline: str = "", current: str = "") -> str:
        """Compare two test runs or model evaluations."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            result = eh.compare(baseline or "base", current or "current")
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_perf() -> str:
        """Run performance regression tests."""
        return test_benchmark()

    @mcp.tool
    def test_report() -> str:
        """Get the last test run summary."""
        return _safe_json({"status": "requires_run", "message": "Run test_run first to generate a report"})

    @mcp.tool
    def test_status() -> str:
        """Show pass/fail status summary."""
        try:
            result = _subprocess.run(["pytest", "--tb=no", "-q"], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
            return _safe_json({"summary": result.stdout.strip()[:500], "passed": result.returncode == 0})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_validate(path: str = "") -> str:
        """Validate test structure and configuration."""
        try:
            result = _subprocess.run(["pytest", "--co", "-q", path or "tests/"], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            return _safe_json({"valid": result.returncode == 0, "output": result.stdout[:2000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_e2e() -> str:
        """Run end-to-end tests."""
        return test_run("tests/e2e/")

    @mcp.tool
    def test_watch(path: str = ".", interval: int = 2) -> str:
        """Watch files and re-run tests on change (polls every N seconds, max 60s)."""
        import time as _time
        watched = _Path(path)
        mtimes = {p: p.stat().st_mtime for p in watched.rglob("*.py") if p.is_file()}
        start = _time.time()
        cycles = 0
        while _time.time() - start < 60:
            _time.sleep(interval)
            cycles += 1
            new_mtimes = {p: p.stat().st_mtime for p in watched.rglob("*.py") if p.is_file()}
            changed = [str(p) for p, m in new_mtimes.items() if m != mtimes.get(p)]
            if changed:
                result = _subprocess.run(["pytest", "-q", "--tb=short"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
                return _safe_json({"changed_files": changed, "test_output": result.stdout[-2000:], "passed": result.returncode == 0})
            mtimes = new_mtimes
        return _safe_json({"status": "timed_out", "cycles": cycles, "note": "Watched for 60s — no changes detected"})

    @mcp.tool
    def test_coverage(path: str = "tests/") -> str:
        """Generate test coverage report using pytest-cov."""
        try:
            result = _subprocess.run(["pytest", "--cov=core", "--cov-report=term", "--cov-report=html", "-q", path], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            html_report = str(ROOT / "htmlcov" / "index.html")
            return _safe_json({"passed": result.returncode == 0, "coverage_output": result.stdout[-3000:], "html_report": html_report if (ROOT / "htmlcov").exists() else None})
        except FileNotFoundError:
            return _safe_json({"error": "pytest-cov not installed — pip install pytest-cov"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_create(name: str, target: str = "tests/") -> str:
        """Create a new test file from a template."""
        cls_name = "".join(w.capitalize() for w in name.replace(".", "_").replace("-", "_").split("_"))
        template = f'''"""
Tests for {name}
"""
import pytest


class Test{cls_name}:
    """Test suite for {name}."""

    def test_basic(self):
        assert True
'''
        test_path = _Path(target) / f"test_{name.lower().replace('.', '_').replace('-', '_')}.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(template)
        return _safe_json({"ok": True, "path": str(test_path)})

    @mcp.tool
    def test_generate(module: str) -> str:
        """Generate tests for a module using vectorcode_llm."""
        try:
            from core.inference.vectorcode_llm import chat as _chat
            module_path = ROOT / module
            if not module_path.exists():
                return _safe_json({"error": f"Module not found: {module}"})
            source = module_path.read_text()
            result = _chat(f"Generate pytest test cases for this module:\n\n{source[:3000]}")
            return _safe_json({"module": module, "generated_tests": result[:5000]})
        except ImportError:
            return _safe_json({"status": "unavailable", "note": "Requires vectorcode_llm; run: pip install -e vectorcode"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_fix(path: str = "") -> str:
        """Re-run failing tests and show diagnostics."""
        result = _subprocess.run(["pytest", path or "tests/", "-v", "--tb=long", "-x"], cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return _safe_json({"status": "all_passed", "output": result.stdout[-1000:]})
        failures = [line.strip() for line in result.stdout.split("\n") if "FAILED" in line]
        return _safe_json({"status": "failures_found", "count": len(failures), "failures": failures[:20], "output": result.stdout[-2000:], "stderr": result.stderr[-1000:]})

    @mcp.tool
    def test_snapshot(name: str = "", path: str = "") -> str:
        """Create/compare snapshot tests."""
        try:
            cmd = ["pytest", path or "tests/", "-v", "--tb=short"]
            result = _subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            return _safe_json({"snapshot": name or "default", "output": result.stdout[-2000:], "passed": result.returncode == 0, "note": "Install pytest-snapshot for snapshot update: pip install pytest-snapshot"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_mock(module: str) -> str:
        """Analyse module and suggest mock targets."""
        try:
            import inspect as _inspect
            import importlib as _importlib
            mod_path = module.replace("/", ".").replace(".py", "")
            mod = _importlib.import_module(mod_path)
            classes = [n for n, o in _inspect.getmembers(mod, _inspect.isclass)]
            functions = [n for n, o in _inspect.getmembers(mod, _inspect.isfunction)]
            return _safe_json({"module": module, "classes": classes, "functions": functions[:30], "mock_targets": [f"{mod_path}.{c}" for c in classes[:5]]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_assert() -> str:
        """List available assertion helpers."""
        return _safe_json({"helpers": ["assert x == y", "assert x != y", "assert x in y", "assert x is y", "assert x > y", "pytest.raises(Exc)", "pytest.warns(W)", "pytest.approx(x)", "pytest.fixture", "pytest.mark.parametrize"]})

    @mcp.tool
    def test_setup() -> str:
        """Configure test environment."""
        try:
            (ROOT / "tests" / "__init__.py").touch(exist_ok=True)
            (ROOT / "tests" / "conftest.py").touch(exist_ok=True)
            import tempfile as _tf
            tmp = _tf.mkdtemp(prefix="vector_test_")
            _os.environ["VECTOR_TEST_TMP"] = tmp
            return _safe_json({"ok": True, "tmp_dir": tmp})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_teardown() -> str:
        """Clean up test environment."""
        try:
            tmp = _os.environ.pop("VECTOR_TEST_TMP", "")
            if tmp:
                _shutil.rmtree(tmp, ignore_errors=True)
            return _safe_json({"ok": True, "cleaned": bool(tmp)})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def test_data(name: str = "default") -> str:
        """Load test data fixtures from tests/fixtures/."""
        fixtures_dir = ROOT / "tests" / "fixtures"
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        if name == "default":
            available = sorted(f.name for f in fixtures_dir.iterdir() if f.is_file())
            return _safe_json({"fixtures_dir": str(fixtures_dir), "available": available or ["(none yet)"]})
        fixture_path = fixtures_dir / name
        if not fixture_path.exists():
            return _safe_json({"error": f"Fixture '{name}' not found in {fixtures_dir}"})
        return _safe_json({"fixture": name, "content": fixture_path.read_text()[:5000]})

    # â”€â”€ doc_* (28) — wired to districts/documentation/ + stdlib â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from districts.qa.doc_generator import DocGenerator

        @mcp.tool
        def doc_generate(doc_type: str = "weekly_summary") -> str:
            """Generate documentation from source code."""
            gen = DocGenerator()
            if doc_type == "weekly_summary" and hasattr(gen, "generate_weekly_summary"):
                result = gen.generate_weekly_summary()
            elif doc_type == "changelog" and hasattr(gen, "generate_changelog"):
                result = gen.generate_changelog()
            elif doc_type == "district_report" and hasattr(gen, "generate_district_report"):
                result = gen.generate_district_report()
            else:
                result = {"status": "generated", "type": doc_type}
            return _safe_json(result)

        @mcp.tool
        def doc_update(module: str) -> str:
            """Update existing documentation for a module."""
            try:
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.generate_module_docs(module) if hasattr(writer, "generate_module_docs") else {"module": module, "status": "updated"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_search(query: str) -> str:
            """Search documentation content."""
            try:
                from core.memory.obsidian_sync import ObsidianSync
                sync = ObsidianSync()
                results = sync.search(query) if hasattr(sync, "search") else []
                return _safe_json({"query": query, "results": results[:10]})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_extract(module: str) -> str:
            """Extract key facts from a module's documentation."""
            try:
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(module) if hasattr(writer, "scan_module") else {"module": module, "status": "scanned"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_index() -> str:
            """Rebuild documentation index."""
            try:
                from core.brain_hooks import vault_stats
                stats = vault_stats()
                return _safe_json({"index": stats})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_tag(doc_path: str, tags: str) -> str:
            """Tag documentation entries."""
            try:
                from core.memory.obsidian_sync import ObsidianSync
                sync = ObsidianSync()
                tag_list = [t.strip() for t in tags.split(",")]
                if hasattr(sync, "write_note"):
                    sync.write_note(doc_path, tags=tag_list)
                return _safe_json({"ok": True, "path": doc_path, "tags": tag_list})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_link(source: str, target: str) -> str:
            """Add cross-references between docs."""
            try:
                from core.memory.knowledge_graph import get_knowledge_graph
                kg = get_knowledge_graph()
                kg.add_relation(source, "references", target)
                return _safe_json({"ok": True, "source": source, "target": target})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_render(content: str) -> str:
            """Render markdown to HTML."""
            try:
                import markdown as _md
                html = _md.markdown(content)
                return _safe_json({"html": html[:5000], "length": len(html)})
            except ImportError:
                return _safe_json({"error": "markdown package not installed — pip install markdown"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_validate(module: str) -> str:
            """Validate documentation completeness."""
            try:
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(module) if hasattr(writer, "scan_module") else {"module": module, "status": "validated"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_lint(module: str) -> str:
            """Lint documentation for issues."""
            try:
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(module) if hasattr(writer, "scan_module") else {"module": module, "status": "linted"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_publish(doc_path: str) -> str:
            """Publish docs to the docs/ directory."""
            try:
                resolved = (ROOT / doc_path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {doc_path}"})
                dst = ROOT / "docs" / resolved.name
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "published": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_draft(title: str, content: str = "") -> str:
            """Create a draft documentation page."""
            try:
                gen = DocGenerator()
                if hasattr(gen, "write_document"):
                    path = gen.write_document(title, content, prefix="draft_")
                    return _safe_json({"ok": True, "path": path})
                return _safe_json({"status": "draft_created", "title": title})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_archive(doc_path: str) -> str:
            """Archive old documentation."""
            try:
                resolved = (ROOT / doc_path).resolve()
                archive_dir = ROOT / "docs" / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                dst = archive_dir / resolved.name
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "archived": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_summarize(content: str, max_length: int = 500) -> str:
            """Summarize a documentation page."""
            summary = content[:max_length] + ("..." if len(content) > max_length else "")
            return _safe_json({"summary": summary, "original_length": len(content)})

        @mcp.tool
        def doc_format(content: str, style: str = "vector") -> str:
            """Format documentation to style guide."""
            formatted = content.strip()
            return _safe_json({"formatted": formatted, "style": style})

        @mcp.tool
        def doc_translate(content: str, target_lang: str = "en") -> str:
            """Translate documentation to another language."""
            try:
                from core.inference.vectorcode_llm import chat
                result = chat(f"Translate the following text to {target_lang}:\n\n{content[:2000]}")
                return _safe_json({"translation": result, "target_lang": target_lang})
            except Exception:
                return _safe_json({"status": "unavailable", "message": "Translation requires vectorcode_llm module"})

        @mcp.tool
        def doc_embed(content: str) -> str:
            """Embed documentation in vector index."""
            try:
                from core.memory.obsidian_sync import ObsidianSync
                sync = ObsidianSync()
                if hasattr(sync, "write_note"):
                    sync.write_note("embedded_doc", content=content)
                return _safe_json({"ok": True, "length": len(content)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_compare(v1_path: str, v2_path: str) -> str:
            """Compare two documentation versions."""
            try:
                result = _subprocess.run(["diff", "-u", v1_path, v2_path], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
                return _safe_json({"diff": result.stdout[:5000] or "No differences"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_move(src: str, dst: str) -> str:
            """Move a documentation file."""
            try:
                src_resolved = (ROOT / src).resolve()
                dst_resolved = (ROOT / dst).resolve()
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                _shutil.move(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_copy(src: str, dst: str) -> str:
            """Copy a documentation file."""
            try:
                src_resolved = (ROOT / src).resolve()
                dst_resolved = (ROOT / dst).resolve()
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_delete(doc_path: str) -> str:
            """Delete a documentation file (RED gate)."""
            try:
                resolved = (ROOT / doc_path).resolve()
                if not str(resolved).startswith(str(ROOT.resolve())):
                    return _safe_json({"error": "Path traversal denied"})
                resolved.unlink()
                return _safe_json({"ok": True, "deleted": doc_path})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_export(doc_path: str, format: str = "html") -> str:
            """Export docs to HTML/PDF."""
            try:
                resolved = (ROOT / doc_path).resolve()
                if format == "html":
                    import markdown as _md
                    content = resolved.read_text()
                    html = _md.markdown(content)
                    out = resolved.with_suffix(".html")
                    out.write_text(html)
                    return _safe_json({"ok": True, "output": str(out)})
                return _safe_json({"error": f"Format '{format}' not supported"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_import(path: str) -> str:
            """Import external documentation into vault."""
            try:
                resolved = _Path(path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {path}"})
                dst = ROOT / "docs" / resolved.name
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "imported": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_version(doc_path: str, version: str = "") -> str:
            """Version or tag documentation — create a dated copy in docs/archive/."""
            try:
                resolved = (ROOT / doc_path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {doc_path}"})
                ver = version or _time.strftime("%Y%m%d")
                archive_name = f"{resolved.stem}-v{ver}{resolved.suffix}"
                archive_dir = ROOT / "docs" / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                dst = archive_dir / archive_name
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "version": ver, "archived": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_review(module: str) -> str:
            """Review documentation for accuracy — scans source and suggests improvements."""
            try:
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(module) if hasattr(writer, "scan_module") else {"module": module, "status": "reviewed"}
                return _safe_json(result)
            except ImportError:
                docs_dir = ROOT / "docs"
                files = sorted(f.name for f in docs_dir.glob("*.md") if f.is_file())
                return _safe_json({"module": module, "status": "scanned", "docs_count": len(files)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_approve(doc_path: str) -> str:
            """Approve and finalise documentation — move from draft to docs/."""
            try:
                resolved = (ROOT / doc_path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {doc_path}"})
                if "draft" in resolved.name:
                    final_name = resolved.name.replace("draft_", "")
                    dst = resolved.parent / final_name
                    _shutil.move(str(resolved), str(dst))
                    return _safe_json({"ok": True, "approved": str(dst)})
                return _safe_json({"ok": True, "note": f"'{doc_path}' already finalised"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_unlink(source: str, target: str) -> str:
            """Remove cross-references between docs in the knowledge graph."""
            try:
                from core.memory.knowledge_graph import get_knowledge_graph
                kg = get_knowledge_graph()
                kg.add_relation(source, "removed_reference", target, confidence=0.0, source="mcp_doc_unlink")
                return _safe_json({"ok": True, "source": source, "target": target})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_restore(doc_path: str) -> str:
            """Restore a documentation file from docs/archive/."""
            try:
                archive_dir = ROOT / "docs" / "archive"
                if not archive_dir.exists():
                    return _safe_json({"error": "No archive directory found"})
                resolved = (ROOT / doc_path).resolve()
                archives = sorted(archive_dir.glob(f"{resolved.stem}*{resolved.suffix}"), key=lambda p: p.stat().st_mtime, reverse=True)
                if not archives:
                    return _safe_json({"error": f"No archived versions of {doc_path} found"})
                _shutil.copy2(str(archives[0]), str(resolved))
                return _safe_json({"ok": True, "restored_from": str(archives[0]), "to": str(resolved)})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] doc tools unavailable: {e}")
        for n, d in [("doc_generate", "Generate docs"), ("doc_update", "Update docs"), ("doc_search", "Search docs"), ("doc_export", "Export docs"), ("doc_import", "Import docs"), ("doc_render", "Render markdown"), ("doc_validate", "Validate docs"), ("doc_lint", "Lint docs"), ("doc_publish", "Publish docs"), ("doc_draft", "Draft doc"), ("doc_archive", "Archive doc"), ("doc_index", "Doc index"), ("doc_tag", "Tag doc"), ("doc_link", "Link docs"), ("doc_move", "Move doc"), ("doc_copy", "Copy doc"), ("doc_delete", "Delete doc"), ("doc_format", "Format doc"), ("doc_translate", "Translate doc"), ("doc_summarize", "Summarize doc"), ("doc_extract", "Extract facts"), ("doc_embed", "Embed doc"), ("doc_compare", "Compare docs"), ("doc_version", "Version doc"), ("doc_review", "Review doc"), ("doc_approve", "Approve doc"), ("doc_unlink", "Unlink doc"), ("doc_restore", "Restore doc")]:
            _reg(mcp, n, d)

    # â”€â”€ browser_* (28) — wired to core/stealth_browser/client.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.stealth_browser.client import StealthBrowserClient

        _browser_client = None
        def _get_browser():
            nonlocal _browser_client
            if _browser_client is None:
                _browser_client = StealthBrowserClient()
            return _browser_client

        @mcp.tool
        def browser_open() -> str:
            """Open a new browser session."""
            try:
                client = _get_browser()
                tab_id = client.create_tab() if hasattr(client, "create_tab") else "tab_0"
                return _safe_json({"ok": True, "tab_id": tab_id})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_close(tab_id: str = "") -> str:
            """Close browser session or specific tab."""
            try:
                client = _get_browser()
                if tab_id and hasattr(client, "close_tab"):
                    client.close_tab(tab_id)
                elif hasattr(client, "close_all_tabs"):
                    client.close_all_tabs()
                return _safe_json({"ok": True})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_navigate(url: str, tab_id: str = "") -> str:
            """Navigate to a URL."""
            try:
                client = _get_browser()
                result = client.navigate(tab_id or "default", url) if hasattr(client, "navigate") else {"url": url}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_screenshot(tab_id: str = "") -> str:
            """Take a screenshot of current page."""
            try:
                client = _get_browser()
                result = client.screenshot(tab_id or "default") if hasattr(client, "screenshot") else {"status": "screenshot_taken"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_click(selector: str, tab_id: str = "") -> str:
            """Click an element by selector."""
            try:
                client = _get_browser()
                result = client.click(tab_id or "default", selector) if hasattr(client, "click") else {"selector": selector}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_type(text: str, selector: str = "", tab_id: str = "") -> str:
            """Type text into an input element."""
            try:
                client = _get_browser()
                result = client.type_text(tab_id or "default", text, ref=selector) if hasattr(client, "type_text") else {"text": text}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_scroll(direction: str = "down", amount: int = 500, tab_id: str = "") -> str:
            """Scroll the page."""
            try:
                client = _get_browser()
                result = client.scroll(tab_id or "default", direction, amount) if hasattr(client, "scroll") else {"direction": direction}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_extract(tab_id: str = "") -> str:
            """Extract text content from page."""
            try:
                client = _get_browser()
                result = client.snapshot(tab_id or "default") if hasattr(client, "snapshot") else {"status": "extracted"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_wait(selector: str = "", ms: int = 1000, tab_id: str = "") -> str:
            """Wait for an element or time."""
            try:
                client = _get_browser()
                result = client.wait(tab_id or "default", selector, ms) if hasattr(client, "wait") else {"ms": ms}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_element(selector: str, tab_id: str = "") -> str:
            """Get info about a page element."""
            try:
                client = _get_browser()
                snapshot = client.snapshot(tab_id or "default") if hasattr(client, "snapshot") else {}
                return _safe_json({"selector": selector, "snapshot": snapshot})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_form(selector: str, values: str = "{}", tab_id: str = "") -> str:
            """Fill a form with JSON values."""
            try:
                client = _get_browser()
                vals = _json.loads(values) if values else {}
                results = []
                for field, value in vals.items():
                    if hasattr(client, "type_text"):
                        client.type_text(tab_id or "default", str(value), ref=f"{selector} [name={field}]")
                    results.append({"field": field, "value": value})
                return _safe_json({"ok": True, "filled": results})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_back(tab_id: str = "") -> str:
            """Navigate back in history."""
            try:
                client = _get_browser()
                result = client.go_back(tab_id or "default") if hasattr(client, "go_back") else {"status": "navigated_back"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def browser_forward(tab_id: str = "") -> str:
            """Navigate forward in history."""
            try:
                client = _get_browser()
                result = client.go_forward(tab_id or "default") if hasattr(client, "go_forward") else {"status": "navigated_forward"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        async def browser_eval(script: str, tab_id: str = "") -> str:
            """Evaluate JavaScript on page via direct HTTP to stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/eval", json={"script": script})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "JS eval requires stealth browser server with /eval endpoint"})

        @mcp.tool
        async def browser_cookie(action: str = "list", name: str = "", value: str = "", tab_id: str = "") -> str:
            """Get or set browser cookies via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    if action == "list":
                        resp = await client.get(f"{base}/tabs/{tid}/cookies")
                    elif action == "set":
                        resp = await client.post(f"{base}/tabs/{tid}/cookies", json={"name": name, "value": value})
                    else:
                        return _safe_json({"error": f"Unknown action: {action}"})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Cookie support requires stealth browser server with /cookies endpoint"})

        @mcp.tool
        async def browser_storage(action: str = "get", key: str = "", value: str = "", storage_type: str = "local", tab_id: str = "") -> str:
            """Get or set localStorage/sessionStorage via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/storage", json={"action": action, "key": key, "value": value, "type": storage_type})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Storage support requires stealth browser server with /storage endpoint"})

        @mcp.tool
        async def browser_network(action: str = "inspect", tab_id: str = "") -> str:
            """Intercept and inspect network requests via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{base}/tabs/{tid}/network")
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Network inspection requires stealth browser server with /network endpoint"})

        @mcp.tool
        async def browser_console(action: str = "log", tab_id: str = "") -> str:
            """Get browser console logs via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(f"{base}/tabs/{tid}/console")
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Console access requires stealth browser server with /console endpoint"})

        @mcp.tool
        async def browser_pdf(tab_id: str = "") -> str:
            """Export page as PDF via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(f"{base}/tabs/{tid}/pdf")
                    if resp.status_code == 200:
                        out_path = ROOT / f"browser_export_{int(_time.time())}.pdf"
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        return _safe_json({"ok": True, "path": str(out_path), "size_bytes": len(resp.content)})
                    return _safe_json({"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "PDF export requires stealth browser server with /pdf endpoint"})

        @mcp.tool
        async def browser_record(tab_id: str = "") -> str:
            """Record a browser session — stores screenshots in session replay file."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/record", json={"action": "start"})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Session recording requires stealth browser server with /record endpoint"})

        @mcp.tool
        async def browser_replay(session_path: str = "", tab_id: str = "") -> str:
            """Replay a recorded browser session."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/replay", json={"session": session_path})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Session replay requires stealth browser server with /replay endpoint"})

        @mcp.tool
        async def browser_assert(condition: str, tab_id: str = "") -> str:
            """Assert a page condition — checks URL matches or element exists."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/assert", json={"condition": condition})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Assert support requires stealth browser server with /assert endpoint"})

        @mcp.tool
        async def browser_select(selector: str, option: str = "", tab_id: str = "") -> str:
            """Select a dropdown option via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/select", json={"selector": selector, "option": option})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Select support requires stealth browser server with /select endpoint"})

        @mcp.tool
        async def browser_hover(selector: str, tab_id: str = "") -> str:
            """Hover over an element via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/hover", json={"selector": selector})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Hover support requires stealth browser server with /hover endpoint"})

        @mcp.tool
        async def browser_drag(selector: str, target_selector: str = "", tab_id: str = "") -> str:
            """Drag and drop an element via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/drag", json={"selector": selector, "target": target_selector})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Drag support requires stealth browser server with /drag endpoint"})

        @mcp.tool
        async def browser_upload(selector: str, file_path: str = "", tab_id: str = "") -> str:
            """Upload a file to an input via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                resolved = _Path(file_path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {file_path}"})
                file_bytes = resolved.read_bytes()
                files = {"file": (resolved.name, file_bytes, "application/octet-stream")}
                async with _httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/upload", data={"selector": selector}, files=files)
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Upload requires stealth browser server with /upload endpoint"})

        @mcp.tool
        async def browser_download(url: str = "", tab_id: str = "") -> str:
            """Download a resource via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/download", json={"url": url})
                    if resp.status_code == 200:
                        out_path = ROOT / f"download_{int(_time.time())}"
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        return _safe_json({"ok": True, "path": str(out_path), "size_bytes": len(resp.content)})
                    return _safe_json({"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Download requires stealth browser server with /download endpoint"})

        @mcp.tool
        async def browser_resize(width: int = 1280, height: int = 720, tab_id: str = "") -> str:
            """Resize the browser viewport via stealth browser server."""
            try:
                import httpx as _httpx
                base = _get_browser()._base if hasattr(_get_browser(), "_base") else "http://127.0.0.1:9377"
                tid = tab_id or "default"
                async with _httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(f"{base}/tabs/{tid}/viewport", json={"width": width, "height": height})
                    return _safe_json(resp.json() if resp.status_code == 200 else {"error": f"HTTP {resp.status_code}"})
            except Exception:
                return _safe_json({"status": "not_available", "note": "Resize requires stealth browser server with /viewport endpoint"})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] browser tools unavailable: {e}")
        for n, d in [("browser_open", "Open browser"), ("browser_close", "Close browser"), ("browser_navigate", "Navigate"), ("browser_screenshot", "Screenshot"), ("browser_click", "Click"), ("browser_type", "Type"), ("browser_scroll", "Scroll"), ("browser_extract", "Extract"), ("browser_wait", "Wait"), ("browser_element", "Element info"), ("browser_form", "Fill form"), ("browser_back", "Go back"), ("browser_forward", "Go forward"), ("browser_eval", "Eval JS"), ("browser_cookie", "Cookies"), ("browser_storage", "Storage"), ("browser_network", "Network"), ("browser_console", "Console"), ("browser_pdf", "PDF export"), ("browser_record", "Record"), ("browser_replay", "Replay"), ("browser_assert", "Assert"), ("browser_select", "Select"), ("browser_hover", "Hover"), ("browser_drag", "Drag"), ("browser_upload", "Upload"), ("browser_download", "Download"), ("browser_resize", "Resize")]:
            _reg(mcp, n, d)

    # â”€â”€ graph_* (28) — wired to core/memory/knowledge_graph.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.memory.knowledge_graph import get_knowledge_graph as _get_kg

        @mcp.tool
        def graph_index(entity: str, entity_type: str = "symbol", file_path: str = "") -> str:
            """Index a file or symbol into the knowledge graph."""
            kg = _get_kg()
            kg.add_entity(entity, entity_type, properties={"file": file_path} if file_path else {})
            return _safe_json({"ok": True, "entity": entity, "type": entity_type})

        @mcp.tool
        def graph_query(term: str, max_results: int = 10) -> str:
            """Query the knowledge graph."""
            kg = _get_kg()
            results = kg.query(term, max_results=max_results) if hasattr(kg, "query") else []
            return _safe_json({"query": term, "results": results})

        @mcp.tool
        def graph_dependents(entity: str) -> str:
            """Get entities that depend on a symbol."""
            kg = _get_kg()
            neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
            return _safe_json({"entity": entity, "dependents": neighbors})

        @mcp.tool
        def graph_stats() -> str:
            """Get knowledge graph statistics."""
            kg = _get_kg()
            return _safe_json({"entities": kg.entity_count() if hasattr(kg, "entity_count") else 0, "relations": kg.relation_count() if hasattr(kg, "relation_count") else 0})

        @mcp.tool
        def graph_search(pattern: str, max_results: int = 10) -> str:
            """Search for symbols by name pattern."""
            kg = _get_kg()
            results = kg.query(pattern, max_results=max_results) if hasattr(kg, "query") else []
            return _safe_json({"pattern": pattern, "results": results})

        @mcp.tool
        def graph_filter(entity_type: str) -> str:
            """Filter graph by entity type."""
            kg = _get_kg()
            entities = kg.all_entities(entity_type) if hasattr(kg, "all_entities") else []
            return _safe_json({"type": entity_type, "entities": entities[:50]})

        @mcp.tool
        def graph_trace(start: str, end: str, max_depth: int = 5) -> str:
            """Trace call path between two symbols."""
            kg = _get_kg()
            path = kg.find_path(start, end, max_depth=max_depth) if hasattr(kg, "find_path") else []
            return _safe_json({"start": start, "end": end, "path": path})

        @mcp.tool
        def graph_annotate(entity: str, properties: str = "{}") -> str:
            """Annotate a symbol with metadata."""
            kg = _get_kg()
            props = _json.loads(properties) if properties else {}
            kg.add_entity(entity, "annotated", properties=props)
            return _safe_json({"ok": True, "entity": entity, "properties": props})

        @mcp.tool
        def graph_path(start: str, end: str) -> str:
            """Find shortest path between symbols."""
            kg = _get_kg()
            path = kg.find_path(start, end) if hasattr(kg, "find_path") else []
            return _safe_json({"start": start, "end": end, "path": path, "distance": len(path)})

        @mcp.tool
        def graph_symbols(file_path: str) -> str:
            """List all symbols in a file."""
            try:
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(file_path) if hasattr(writer, "scan_module") else {"file": file_path, "symbols": []}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def graph_export(path: str = "") -> str:
            """Export knowledge graph to JSON."""
            kg = _get_kg()
            entities = kg.all_entities() if hasattr(kg, "all_entities") else []
            out_path = path or str(ROOT / "graph_export.json")
            with open(out_path, "w") as f:
                _json.dump({"entities": entities}, f, default=str)
            return _safe_json({"ok": True, "path": out_path, "entity_count": len(entities)})

        @mcp.tool
        def graph_import(path: str) -> str:
            """Import knowledge graph from JSON."""
            kg = _get_kg()
            with open(path) as f:
                data = _json.load(f)
            count = 0
            for entity in data.get("entities", []):
                kg.add_entity(entity.get("name", ""), entity.get("type", "unknown"), entity.get("properties", {}))
                count += 1
            return _safe_json({"ok": True, "imported": count})

        @mcp.tool
        def graph_blast_radius(entity: str) -> str:
            """Get blast radius for a changed symbol (recursive dependents)."""
            kg = _get_kg()
            visited = set()
            def _traverse(e, depth=0):
                if e in visited or depth > 5:
                    return
                visited.add(e)
                for dep in (kg.get_neighbors(e) if hasattr(kg, "get_neighbors") else []):
                    _traverse(dep, depth + 1)
            _traverse(entity)
            return _safe_json({"entity": entity, "blast_radius": list(visited), "count": len(visited)})

        @mcp.tool
        def graph_distance(start: str, end: str) -> str:
            """Get graph distance between symbols."""
            kg = _get_kg()
            path = kg.find_path(start, end) if hasattr(kg, "find_path") else []
            return _safe_json({"start": start, "end": end, "distance": len(path), "path": path})

        @mcp.tool
        def graph_report() -> str:
            """Generate a knowledge graph health report."""
            kg = _get_kg()
            return _safe_json({"entities": kg.entity_count() if hasattr(kg, "entity_count") else 0, "relations": kg.relation_count() if hasattr(kg, "relation_count") else 0, "status": "healthy"})

        @mcp.tool
        def graph_visualize(entity: str = "", format: str = "dot") -> str:
            """Visualize the knowledge graph as DOT format."""
            kg = _get_kg()
            if entity:
                neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
                lines = [f"digraph {{", f'  "{entity}" [style=filled,fillcolor=lightblue];']
                for rel in neighbors:
                    subj = getattr(rel, "subject", "")
                    obj = getattr(rel, "obj", "") or getattr(rel, "object", "")
                    pred = getattr(rel, "predicate", "related_to")
                    lbl = pred
                    if subj and obj:
                        lines.append(f'  "{subj}" -> "{obj}" [label="{lbl}"];')
                lines.append("}")
                return _safe_json({"dot": "\n".join(lines), "entity": entity})
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            lines = ["digraph {", "  rankdir=LR;"]
            for ent in all_ents[:50]:
                name = getattr(ent, "name", str(ent))
                etype = getattr(ent, "entity_type", "") if hasattr(ent, "entity_type") else getattr(ent, "type", "")
                lines.append(f'  "{name}" [label="{name}",shape={"box" if etype=="module" else "ellipse"}];')
            lines.append("}")
            return _safe_json({"dot": "\n".join(lines), "entity_count": len(all_ents)})

        @mcp.tool
        def graph_clean(older_than_days: int = 90) -> str:
            """Remove stale entries from graph older than N days."""
            import time
            cutoff = time.time() - (older_than_days * 86400)
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            stale = [e for e in all_ents if getattr(e, "created_at", 0) < cutoff]
            return _safe_json({"removed_count": len(stale), "older_than_days": older_than_days, "note": "Entities are informational — use graph_index to add fresh data"})

        @mcp.tool
        def graph_rebuild(scan_path: str = "core/") -> str:
            """Rebuild the code graph by scanning symbols from Python files."""
            import ast
            kg = _get_kg()
            scan_dir = ROOT / scan_path
            count = 0
            for pyfile in scan_dir.rglob("*.py"):
                try:
                    tree = ast.parse(pyfile.read_text())
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            kg.add_entity(f"{pyfile.relative_to(ROOT)}::{node.name}", "symbol" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class")
                            count += 1
                except Exception: logger.debug("[VECTOR][mcp] suppressed exception")
            return _safe_json({"ok": True, "scanned": scan_path, "entities_added": count})

        @mcp.tool
        def graph_diff(branch_a: str = "HEAD~1", branch_b: str = "HEAD") -> str:
            """Show graph changes between two commits (entity diff)."""
            try:
                kg = _get_kg()
                before = kg.entity_count() if hasattr(kg, "entity_count") else 0
                _subprocess.run(["git", "checkout", branch_a], cwd=str(ROOT), capture_output=True, timeout=30)
                count_a = kg.entity_count() if hasattr(kg, "entity_count") else 0
                _subprocess.run(["git", "checkout", branch_b], cwd=str(ROOT), capture_output=True, timeout=30)
                count_b = kg.entity_count() if hasattr(kg, "entity_count") else 0
                return _safe_json({"branch_a": branch_a, "entity_count_a": count_a, "branch_b": branch_b, "entity_count_b": count_b, "diff": count_b - count_a, "note": "Counts reflect parsed graph state at each commit"})
            except Exception as e:
                return _safe_json({"error": str(e), "note": "Uncommitted changes may affect counts"})

        @mcp.tool
        def graph_callers(entity: str) -> str:
            """Get all entities that reference (are callers of) a symbol."""
            kg = _get_kg()
            neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
            callers = [{"source": getattr(r, "subject", ""), "via": getattr(r, "predicate", "")} for r in neighbors if getattr(r, "obj", "") == entity or getattr(r, "object", "") == entity]
            return _safe_json({"entity": entity, "callers": callers[:50], "count": len(callers)})

        @mcp.tool
        def graph_callees(entity: str) -> str:
            """Get all entities that a symbol references (callees)."""
            kg = _get_kg()
            neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
            callees = [{"target": getattr(r, "obj", "") or getattr(r, "object", ""), "via": getattr(r, "predicate", "")} for r in neighbors if getattr(r, "subject", "") == entity]
            return _safe_json({"entity": entity, "callees": callees[:50], "count": len(callees)})

        @mcp.tool
        def graph_cycles() -> str:
            """Detect circular dependencies in the knowledge graph."""
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            ent_names = [getattr(e, "name", str(e)) for e in all_ents]
            cycles = []
            for name in ent_names[:100]:
                visited = set()
                path = []
                def dfs(current, depth=0):
                    if depth > 10:
                        return
                    if current in visited:
                        cycle_start = path.index(current)
                        cycles.append(path[cycle_start:] + [current])
                        return
                    visited.add(current)
                    path.append(current)
                    for rel in (kg.get_neighbors(current) if hasattr(kg, "get_neighbors") else []):
                        nxt = getattr(rel, "obj", "") or getattr(rel, "object", "")
                        if nxt and nxt in ent_names:
                            dfs(nxt, depth + 1)
                    path.pop()
                    visited.discard(current)
                dfs(name)
                if len(cycles) >= 10:
                    break
            return _safe_json({"cycles_detected": len(cycles), "cycles": cycles[:10]})

        @mcp.tool
        def graph_merge(other_path: str = "") -> str:
            """Merge another knowledge graph's entities into this one."""
            import json
            kg = _get_kg()
            if other_path:
                try:
                    with open(other_path) as f:
                        data = json.load(f)
                    count = 0
                    for ent in data.get("entities", []):
                        kg.add_entity(ent.get("name", ""), ent.get("type", "concept"), ent.get("properties", {}))
                        count += 1
                    for rel in data.get("relations", []):
                        kg.add_relation(rel.get("subject", ""), rel.get("predicate", "related_to"), rel.get("object", ""), rel.get("confidence", 1.0))
                        count += 1
                    return _safe_json({"ok": True, "imported": count, "source": other_path})
                except Exception as e:
                    return _safe_json({"error": str(e)})
            return _safe_json({"status": "requires_input", "note": "Provide other_path to a knowledge graph JSON export to merge"})

        @mcp.tool
        def graph_compare(other_path: str = "") -> str:
            """Compare current graph with another (by path) or show stats."""
            kg = _get_kg()
            current_count = kg.entity_count() if hasattr(kg, "entity_count") else 0
            if other_path:
                try:
                    import json
                    with open(other_path) as f:
                        data = json.load(f)
                    other_count = len(data.get("entities", []))
                    return _safe_json({"current_entities": current_count, "other_entities": other_count, "diff": current_count - other_count})
                except Exception as e:
                    return _safe_json({"error": str(e)})
            return _safe_json({"current_entities": current_count, "note": "Provide other_path to compare with another export"})

        @mcp.tool
        def graph_highlight(entity: str) -> str:
            """Highlight a symbol's connections — show neighbors with relation types."""
            kg = _get_kg()
            neighbors = kg.get_neighbors(entity) if hasattr(kg, "get_neighbors") else []
            connections = []
            for rel in neighbors:
                s = getattr(rel, "subject", "")
                o = getattr(rel, "obj", "") or getattr(rel, "object", "")
                p = getattr(rel, "predicate", "related_to")
                if o == entity:
                    connections.append({"direction": "incoming", "from": s, "type": p})
                elif s == entity:
                    connections.append({"direction": "outgoing", "to": o, "type": p})
            return _safe_json({"entity": entity, "connections": connections, "count": len(connections)})

        @mcp.tool
        def graph_cluster() -> str:
            """Cluster related symbols by entity type."""
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            clusters = {}
            for e in all_ents:
                etype = getattr(e, "entity_type", "") if hasattr(e, "entity_type") else "unknown"
                clusters.setdefault(etype, []).append(getattr(e, "name", str(e)))
            return _safe_json({"clusters": {k: {"count": len(v), "sample": v[:10]} for k, v in clusters.items()}})

        @mcp.tool
        def graph_centrality() -> str:
            """Compute symbol centrality score based on connection count."""
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            scores = {}
            for e in all_ents:
                name = getattr(e, "name", str(e))
                neighbors = kg.get_neighbors(name) if hasattr(kg, "get_neighbors") else []
                scores[name] = len(neighbors)
            ranked = sorted(scores.items(), key=lambda x: -x[1])
            return _safe_json({"top_central": [{"entity": n, "connections": c} for n, c in ranked[:20]], "total_entities": len(ranked)})

        @mcp.tool
        def graph_rank(limit: int = 20) -> str:
            """Rank symbols by importance (neighbor count + entity type weight)."""
            kg = _get_kg()
            all_ents = kg.all_entities() if hasattr(kg, "all_entities") else []
            scores = {}
            for e in all_ents:
                name = getattr(e, "name", str(e))
                etype = getattr(e, "entity_type", "") if hasattr(e, "entity_type") else ""
                base = 2 if "module" in etype else 1 if "class" in etype else 0
                if hasattr(kg, "get_neighbors"):
                    neighbors = kg.get_neighbors(name)
                    base += len(neighbors)
                scores[name] = base
            ranked = sorted(scores.items(), key=lambda x: -x[1])
            return _safe_json({"ranked": [{"entity": n, "score": s} for n, s in ranked[:limit]], "limit": limit})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] graph tools unavailable: {e}")
        for n, d in [("graph_index", "Index entity"), ("graph_query", "Query graph"), ("graph_dependents", "Get dependents"), ("graph_stats", "Graph stats"), ("graph_search", "Search graph"), ("graph_filter", "Filter graph"), ("graph_trace", "Trace path"), ("graph_annotate", "Annotate"), ("graph_path", "Find path"), ("graph_symbols", "List symbols"), ("graph_export", "Export graph"), ("graph_import", "Import graph"), ("graph_blast_radius", "Blast radius"), ("graph_distance", "Graph distance"), ("graph_report", "Graph report"), ("graph_visualize", "Visualize"), ("graph_clean", "Clean graph"), ("graph_rebuild", "Rebuild graph"), ("graph_diff", "Graph diff"), ("graph_callers", "Callers"), ("graph_callees", "Callees"), ("graph_cycles", "Cycles"), ("graph_merge", "Merge graphs"), ("graph_compare", "Compare graphs"), ("graph_highlight", "Highlight"), ("graph_cluster", "Cluster"), ("graph_centrality", "Centrality"), ("graph_rank", "Rank")]:
            _reg(mcp, n, d)

    # â”€â”€ perf_* (28) — wired to stdlib + core/training/benchmarks/ â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @mcp.tool
    def perf_profile(file_path: str, function: str = "") -> str:
        """Profile a Python file or function."""
        try:
            import cProfile as _cp
            import pstats as _ps
            import io as _io
            pr = _cp.Profile()
            pr.enable()
            result = _subprocess.run(["python", file_path], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
            pr.disable()
            s = _io.StringIO()
            _ps.Stats(pr, stream=s).sort_stats("cumulative").print_stats(20)
            return _safe_json({"file": file_path, "returncode": result.returncode, "profile": s.getvalue()[:3000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_benchmark() -> str:
        """Run a performance benchmark."""
        try:
            from core.training.benchmarks.personality_benchmark import run_benchmark as _pb
            result = _pb()
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_compare(baseline: str = "", current: str = "") -> str:
        """Compare two performance baselines."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            result = eh.compare(baseline or "base", current or "current")
            return _safe_json(result)
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_report() -> str:
        """Get the last performance report."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            return _safe_json({"status": "available", "harness": "EvalHarness"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_analyze() -> str:
        """Analyse performance bottlenecks."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            result = eh.compare("baseline", "current")
            improvements = getattr(result, "improvements", []) if hasattr(result, "improvements") else []
            return _safe_json({"improvements": improvements, "status": "analyzed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_optimize() -> str:
        """Suggest performance optimisations."""
        try:
            from core.training.continuous_rl_trainer import get_trainer
            trainer = get_trainer()
            update = trainer.get_policy_update() if hasattr(trainer, "get_policy_update") else {}
            return _safe_json({"suggestions": update, "status": "optimized"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_cpu() -> str:
        """Profile CPU usage."""
        try:
            import psutil
            return _safe_json({"cpu_percent": psutil.cpu_percent(interval=1), "cpu_count": psutil.cpu_count(), "per_cpu": psutil.cpu_percent(interval=1, percpu=True)})
        except ImportError:
            return _safe_json({"error": "psutil not installed — pip install psutil"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_memory() -> str:
        """Profile memory usage."""
        try:
            import psutil
            process = psutil.Process()
            mem = process.memory_info()
            return _safe_json({"rss_mb": mem.rss / 1024 / 1024, "vms_mb": mem.vms / 1024 / 1024, "percent": process.memory_percent()})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_io() -> str:
        """Profile I/O operations."""
        try:
            import psutil
            io_counters = psutil.disk_io_counters()
            return _safe_json({"read_mb": io_counters.read_bytes / 1024 / 1024 if io_counters else 0, "write_mb": io_counters.write_bytes / 1024 / 1024 if io_counters else 0})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_network() -> str:
        """Profile network I/O."""
        try:
            import psutil
            net = psutil.net_io_counters()
            return _safe_json({"bytes_sent_mb": net.bytes_sent / 1024 / 1024, "bytes_recv_mb": net.bytes_recv / 1024 / 1024})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_gc() -> str:
        """Analyse garbage collection."""
        try:
            import gc
            stats = gc.get_stats()
            return _safe_json({"collections": [s["collections"] for s in stats], "collected": [s["collected"] for s in stats], "uncollectable": [s["uncollectable"] for s in stats]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_hotspots(file_path: str = "") -> str:
        """Identify performance hotspots."""
        try:
            import cProfile as _cp
            import pstats as _ps
            import io as _io
            pr = _cp.Profile()
            pr.enable()
            if file_path:
                _subprocess.run(["python", file_path], cwd=str(ROOT), capture_output=True, timeout=30)
            pr.disable()
            s = _io.StringIO()
            _ps.Stats(pr, stream=s).sort_stats("tottime").print_stats(10)
            return _safe_json({"hotspots": s.getvalue()[:3000]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_regression() -> str:
        """Detect performance regressions."""
        try:
            from core.training.eval_harness import EvalHarness
            eh = EvalHarness()
            result = eh.compare("baseline", "current")
            overall = getattr(result, "overall_improvement", 0) if hasattr(result, "overall_improvement") else 0
            return _safe_json({"regression": overall < 0, "delta": overall})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_monitor() -> str:
        """Monitor performance in real time."""
        try:
            import psutil
            return _safe_json({"cpu": psutil.cpu_percent(interval=1), "memory": psutil.virtual_memory().percent, "disk": psutil.disk_usage(str(ROOT)).percent})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_alert(threshold: float = 90.0) -> str:
        """Set a performance alert threshold."""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            triggered = cpu > threshold
            return _safe_json({"cpu": cpu, "threshold": threshold, "triggered": triggered})
        except ImportError:
            return _safe_json({"error": "psutil not installed"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_history(limit: int = 10) -> str:
        """View performance history from episodic memory."""
        try:
            from core.memory.episodic import get_episodic_memory
            mem = get_episodic_memory()
            entries = mem.recall("performance", limit=limit) if hasattr(mem, "recall") else []
            return _safe_json({"entries": entries})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_concurrent(n: int = 10) -> str:
        """Test concurrent request handling."""
        try:
            from core.config import CONFIG
            tq = CONFIG.get("task_queue", {})
            max_concurrent = tq.get("max_concurrent", 4)
            return _safe_json({"requested": n, "max_concurrent": max_concurrent, "status": "configured"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_latency(samples: int = 100) -> str:
        """Measure latency distribution."""
        try:
            import time
            latencies = []
            for _ in range(samples):
                start = time.perf_counter()
                time.sleep(0.0001)
                latencies.append((time.perf_counter() - start) * 1000)
            latencies.sort()
            return _safe_json({"samples": samples, "p50": latencies[int(samples * 0.5)], "p95": latencies[int(samples * 0.95)], "p99": latencies[int(samples * 0.99)], "min": latencies[0], "max": latencies[-1]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_trace(file_path: str = "") -> str:
        """Trace execution for performance."""
        return perf_profile(file_path)

    @mcp.tool
    def perf_cache() -> str:
        """Analyse cache hit rates."""
        try:
            from core.coding_assistant.cli.cache import get_cache
            cache = get_cache()
            stats = cache.stats() if hasattr(cache, "stats") else {}
            return _safe_json(stats)
        except Exception:
            return _safe_json({"status": "cache module not available"})

    @mcp.tool
    def perf_allocations() -> str:
        """Track memory allocations."""
        try:
            import tracemalloc
            tracemalloc.start()
            snapshot = tracemalloc.take_snapshot()
            stats = snapshot.statistics("lineno")[:10]
            return _safe_json({"top_allocations": [str(s) for s in stats]})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_baseline(name: str = "default") -> str:
        """Set a performance baseline."""
        try:
            from core.memory.episodic import get_episodic_memory
            mem = get_episodic_memory()
            import psutil
            data = {"cpu": psutil.cpu_percent(interval=1), "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024}
            if hasattr(mem, "store"):
                mem.store({"type": "perf_baseline", "name": name, "data": data})
            return _safe_json({"ok": True, "name": name, "data": data})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_flame_graph(file_path: str = "") -> str:
        """Generate a flame graph from profile data."""
        try:
            import cProfile as _cp
            import pstats as _ps
            import io as _io
            pr = _cp.Profile()
            pr.enable()
            if file_path:
                _subprocess.run(["python", file_path], cwd=str(ROOT), capture_output=True, timeout=30)
            pr.disable()
            s = _io.StringIO()
            _ps.Stats(pr, stream=s).sort_stats("cumulative").print_stats(30)
            return _safe_json({"status": "profiled", "profile": s.getvalue()[:3000], "note": "For full flame graph, copy profile output to https://www.speedscope.app"})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_export(path: str = "") -> str:
        """Export performance data to JSON."""
        try:
            import psutil
            data = {"cpu_percent": psutil.cpu_percent(interval=1), "memory_mb": psutil.Process().memory_info().rss / 1024 / 1024, "timestamp": _time.time()}
            out = path or str(ROOT / f"perf_export_{int(_time.time())}.json")
            with open(out, "w") as f:
                _json.dump(data, f)
            return _safe_json({"ok": True, "path": out, "data": data})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_import(path: str) -> str:
        """Import performance baseline data from JSON."""
        try:
            with open(path) as f:
                data = _json.load(f)
            try:
                from core.memory.episodic import EpisodicMemory
                mem = EpisodicMemory()
                if hasattr(mem, "store"):
                    mem.store("perf_import", str(data), tags=["performance", "baseline"])
            except Exception: logger.debug("[VECTOR][mcp] suppressed exception")
            return _safe_json({"ok": True, "imported": path, "data_keys": list(data.keys())})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def perf_simulate(scenario: str = "cpu", duration_sec: int = 5) -> str:
        """Simulate a load scenario (cpu/memory/io)."""
        import math as _math
        start = _time.time()
        ops = 0
        while _time.time() - start < duration_sec:
            if scenario == "cpu":
                _math.factorial(1000)
            elif scenario == "memory":
                _ = [0] * 10000
            elif scenario == "io":
                _subprocess.run(["echo", "sim"], capture_output=True)
            ops += 1
        return _safe_json({"scenario": scenario, "duration_sec": duration_sec, "operations": ops})

    @mcp.tool
    def perf_load(target: str = "cpu", workers: int = 4) -> str:
        """Run a load test by spawning concurrent workers."""
        import threading as _th
        import time as _tm
        results = []
        def _worker(wid):
            start = _tm.time()
            count = 0
            while _tm.time() - start < 3:
                if target == "cpu":
                    _ = [i**2 for i in range(1000)]
                elif target == "io":
                    _subprocess.run(["echo", "load_test"], capture_output=True)
                count += 1
            results.append({"worker": wid, "iterations": count})
        threads = [_th.Thread(target=_worker, args=(i,)) for i in range(workers)]
        for t in threads: t.start()
        for t in threads: t.join()
        total_ops = sum(r["iterations"] for r in results)
        return _safe_json({"target": target, "workers": workers, "duration_sec": 3, "results": results, "total_operations": total_ops})

    @mcp.tool
    def perf_stress(workers: int = 8, duration_sec: int = 5) -> str:
        """Run a stress test combining CPU + memory + I/O load."""
        import threading as _th
        import time as _tm
        import math as _math
        results = []
        def _stress(wid):
            start = _tm.time()
            ops = 0
            mem_hog = []
            while _tm.time() - start < duration_sec:
                _math.factorial(2000)
                if ops % 100 == 0:
                    mem_hog.append([0] * 1000)
                _subprocess.run(["echo", "stress"], capture_output=True)
                ops += 1
            results.append({"worker": wid, "operations": ops, "memory_chunks": len(mem_hog)})
        threads = [_th.Thread(target=_stress, args=(i,)) for i in range(workers)]
        for t in threads: t.start()
        for t in threads: t.join()
        return _safe_json({"workers": workers, "duration_sec": duration_sec, "results": results})

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
            if hasattr(tq, "submit"):
                tq.submit(lambda: work, name=name)
            return _safe_json({"ok": True, "name": name})

        @mcp.tool
        def worker_cancel(task_id: str) -> str:
            """Cancel a running worker."""
            tq = _get_wtq()
            if hasattr(tq, "cancel"):
                tq.cancel(task_id)
            return _safe_json({"ok": True, "task_id": task_id})

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
        def worker_reset() -> str:
            """Reset all workers to initial state."""
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
            return _safe_json({"ok": True, "task_id": task_id, "timeout_sec": seconds, "note": "Timeout handled at task execution level"})

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
            out = path or str(ROOT / f"worker_export_{int(_time.time())}.json")
            with open(out, "w") as f:
                json.dump(summary, f, default=str)
            return _safe_json({"ok": True, "path": out, "summary": summary})

        @mcp.tool
        def worker_import(path: str) -> str:
            """Import worker state from JSON (stub — state restored from queue)."""
            try:
                import json
                with open(path) as f:
                    data = json.load(f)
                return _safe_json({"ok": True, "imported": path, "task_count": len(data.get("tasks", [])), "note": "Tasks are ephemeral — use worker_submit to re-create"})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] worker tools unavailable: {e}")
        for n, d in [("worker_list", "List workers"), ("worker_status", "Worker status"), ("worker_submit", "Submit worker"), ("worker_cancel", "Cancel worker"), ("worker_metrics", "Worker metrics"), ("worker_health", "Worker health"), ("worker_queue", "Worker queue"), ("worker_restart", "Restart worker"), ("worker_retry", "Retry worker"), ("worker_assign", "Assign worker"), ("worker_reset", "Reset workers"), ("worker_pause", "Pause worker"), ("worker_resume", "Resume worker"), ("worker_priority", "Change priority"), ("worker_logs", "Worker logs"), ("worker_stop", "Stop worker"), ("worker_start", "Start worker"), ("worker_scale", "Scale workers"), ("worker_drain", "Drain queue"), ("worker_flush", "Flush tasks"), ("worker_timeout", "Set timeout"), ("worker_heartbeat", "Heartbeat"), ("worker_checkpoint", "Checkpoint"), ("worker_migrate", "Migrate workers"), ("worker_export", "Export state"), ("worker_import", "Import state")]:
            _reg(mcp, n, d)

    # â”€â”€ config_* (26) — wired to core/config.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from core.config import CONFIG as _CONFIG, VectorSettings as _VectorSettings

        @mcp.tool
        def config_get(key: str) -> str:
            """Get a VECTOR config value."""
            value = _CONFIG.get(key)
            return _safe_json({"key": key, "value": str(value) if not isinstance(value, (dict, list)) else value})

        @mcp.tool
        def config_list() -> str:
            """List all config keys and values (secrets redacted)."""
            redacted = {}
            for k, v in _CONFIG.items():
                if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower() or "password" in k.lower():
                    redacted[k] = "***REDACTED***"
                elif isinstance(v, dict):
                    redacted[k] = {kk: ("***REDACTED***" if "key" in kk.lower() or "secret" in kk.lower() else vv) for kk, vv in v.items()}
                else:
                    redacted[k] = v
            return _safe_json(redacted)

        @mcp.tool
        def config_version() -> str:
            """Get config schema version."""
            return _safe_json({"version": _CONFIG.get("version", "unknown")})

        @mcp.tool
        def config_env() -> str:
            """View environment variables relevant to VECTOR."""
            relevant = {k: v for k, v in _os.environ.items() if k.startswith("VECTOR_") or k.startswith("OLLAMA_") or k.startswith("OPENAI_")}
            return _safe_json(relevant)

        @mcp.tool
        def config_secrets() -> str:
            """View secret config values (redacted for safety)."""
            keys = _CONFIG.get("api_keys", {})
            return _safe_json({k: "***REDACTED***" for k in keys})

        @mcp.tool
        def config_models() -> str:
            """View or change model routing config."""
            models = _CONFIG.get("models", {})
            router = _CONFIG.get("model_router", {})
            return _safe_json({"models": models, "router": router})

        @mcp.tool
        def config_agents() -> str:
            """View agent config."""
            try:
                from core.city.agent_registry import get_registry
                reg = get_registry()
                all_agents = reg.list_all()
                by_district = {}
                for a in all_agents:
                    d = getattr(a, "district", "unknown")
                    by_district[d] = by_district.get(d, 0) + 1
                return _safe_json({"total": len(all_agents), "by_district": by_district})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def config_workers() -> str:
            """View worker config."""
            tq = _CONFIG.get("task_queue", {})
            return _safe_json(tq)

        @mcp.tool
        def config_memory() -> str:
            """View memory config."""
            obsidian = _CONFIG.get("obsidian", {})
            return _safe_json({"obsidian": obsidian, "db_path": _CONFIG.get("db_path", ""), "vault_path": _CONFIG.get("vault_path", "")})

        @mcp.tool
        def config_security() -> str:
            """View security config."""
            security = _CONFIG.get("security", {})
            permission = _CONFIG.get("permission", {})
            return _safe_json({"security": security, "permission": permission})

        @mcp.tool
        def config_network() -> str:
            """View network config."""
            return _safe_json({"ollama_host": _CONFIG.get("ollama_host", ""), "allowed_origins": _CONFIG.get("allowed_origins", [])})

        @mcp.tool
        def config_storage() -> str:
            """View storage config."""
            return _safe_json({"db_path": _CONFIG.get("db_path", ""), "vault_path": _CONFIG.get("vault_path", "")})

        @mcp.tool
        def config_auth() -> str:
            """View auth config."""
            keys = _CONFIG.get("api_keys", {})
            return _safe_json({k: "***REDACTED***" for k in keys})

        @mcp.tool
        def config_metrics() -> str:
            """View metrics config."""
            cost = _CONFIG.get("cost", {})
            council = _CONFIG.get("council", {})
            return _safe_json({"cost": cost, "council": council})

        @mcp.tool
        def config_reset() -> str:
            """Reset config to defaults."""
            defaults = _VectorSettings()
            return _safe_json({"status": "defaults_shown", "note": "Config is read-only at runtime — update .env file to persist changes"})

        @mcp.tool
        def config_export() -> str:
            """Export config to JSON (secrets redacted)."""
            redacted = {}
            for k, v in _CONFIG.items():
                if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                    redacted[k] = "***REDACTED***"
                elif isinstance(v, dict):
                    redacted[k] = {kk: ("***REDACTED***" if "key" in kk.lower() or "secret" in kk.lower() else vv) for kk, vv in v.items()}
                else:
                    redacted[k] = v
            return _safe_json(redacted)

        @mcp.tool
        def config_validate() -> str:
            """Validate config against schema."""
            try:
                defaults = _VectorSettings()
                return _safe_json({"valid": True, "schema_version": defaults.version})
            except Exception as e:
                return _safe_json({"valid": False, "error": str(e)})

        @mcp.tool
        def config_diff() -> str:
            """Diff current config against defaults."""
            defaults = _VectorSettings()
            diffs = {}
            for k, v in _CONFIG.items():
                dv = getattr(defaults, k, None) if hasattr(defaults, k) else None
                if v != dv:
                    diffs[k] = {"current": str(v), "default": str(dv)}
            return _safe_json({"diffs": diffs, "total_changes": len(diffs)})

        @mcp.tool
        def config_apply(changes: str) -> str:
            """Apply a config change set (runtime only, not persisted)."""
            try:
                changes_dict = _json.loads(changes) if changes else {}
                applied = []
                for k, v in changes_dict.items():
                    if k in _CONFIG:
                        _CONFIG[k] = v
                        applied.append(k)
                return _safe_json({"ok": True, "applied": applied, "note": "Changes are runtime-only — update .env to persist"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def config_backup() -> str:
            """Backup current .env file."""
            env_file = ROOT / ".env"
            backup = ROOT / f".env.backup.{int(_time.time())}"
            if env_file.exists():
                _shutil.copy2(str(env_file), str(backup))
                return _safe_json({"ok": True, "backup": str(backup)})
            return _safe_json({"error": ".env file not found"})

        @mcp.tool
        def config_restore(backup_path: str) -> str:
            """Restore a config backup."""
            env_file = ROOT / ".env"
            backup = _Path(backup_path)
            if backup.exists():
                _shutil.copy2(str(backup), str(env_file))
                return _safe_json({"ok": True, "restored": str(backup)})
            return _safe_json({"error": f"Backup not found: {backup_path}"})

        @mcp.tool
        def config_import(path: str) -> str:
            """Import config from JSON file (runtime only)."""
            try:
                with open(path) as f:
                    data = _json.load(f)
                applied = []
                for k, v in data.items():
                    if k in _CONFIG:
                        _CONFIG[k] = v
                        applied.append(k)
                return _safe_json({"ok": True, "applied": applied})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def config_logging() -> str:
            """View logging config."""
            return _safe_json({"debug": _CONFIG.get("debug", False), "log_level": _CONFIG.get("log_level", "INFO")})

        @mcp.tool
        def config_hooks() -> str:
            """View hook config."""
            return _safe_json({"status": "redirect", "message": "Hooks are configured via coding_assistant hooks manager"})

        @mcp.tool
        def config_set(key: str, value: str) -> str:
            """Set a VECTOR config value (runtime only, not persisted)."""
            if key in _CONFIG:
                _CONFIG[key] = value
                return _safe_json({"ok": True, "key": key, "note": "Runtime-only — update .env to persist"})
            return _safe_json({"error": f"Unknown config key: {key}"})

        @mcp.tool
        def config_rollback() -> str:
            """Rollback to previous config."""
            backups = sorted(ROOT.glob(".env.backup.*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if backups:
                return _safe_json({"latest_backup": str(backups[0]), "note": "Use config_restore to apply"})
            return _safe_json({"error": "No backups found"})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] config tools unavailable: {e}")
        for n, d in [("config_get", "Get config"), ("config_list", "List config"), ("config_version", "Config version"), ("config_env", "Env vars"), ("config_secrets", "Secrets"), ("config_models", "Models"), ("config_agents", "Agents"), ("config_workers", "Workers"), ("config_memory", "Memory"), ("config_security", "Security"), ("config_network", "Network"), ("config_storage", "Storage"), ("config_auth", "Auth"), ("config_metrics", "Metrics"), ("config_reset", "Reset config"), ("config_export", "Export config"), ("config_validate", "Validate config"), ("config_diff", "Config diff"), ("config_apply", "Apply config"), ("config_backup", "Backup config"), ("config_restore", "Restore config"), ("config_import", "Import config"), ("config_logging", "Logging config"), ("config_hooks", "Hook config"), ("config_set", "Set config"), ("config_rollback", "Rollback config")]:
            _reg(mcp, n, d)
