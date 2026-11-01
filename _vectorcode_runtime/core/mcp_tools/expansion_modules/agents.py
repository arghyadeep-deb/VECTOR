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


def add_agent_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

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
