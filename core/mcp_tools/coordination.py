"""MCP task-claim, guidance, and kanban tools."""

from loguru import logger

from core.mcp_tools.error_handling import mcp_call_json as _mcp_call_json


def add_claims_tools(mcp) -> None:
    """Wire vectorcode/src/claims.py MCP tools into the server."""
    try:
        from vectorcode.src.claims import (
            mcp_claim_task as _claim,
            mcp_release_task as _release,
            mcp_list_claims as _list,
            mcp_steal_task as _steal,
            mcp_get_stealable as _stealable,
            mcp_rebalance_load as _rebalance,
            mcp_claim_stats as _stats,
        )
        import json as _json
        import asyncio as _asyncio

        @mcp.tool
        async def claim_task(issue_id: str, agent_id: str, agent_name: str, title: str = "", priority: str = "medium") -> str:
            """Claim a task for a VECTOR agent — registers distributed ownership."""
            result = _claim(issue_id, agent_id, agent_name, capabilities=[], title=title, priority=priority)
            return _json.dumps(result)

        @mcp.tool
        async def release_task(issue_id: str, agent_id: str) -> str:
            """Release a task claim — makes it available for other districts."""
            return _json.dumps(_release(issue_id, agent_id))

        @mcp.tool
        async def list_claims(agent_id: str = "") -> str:
            """List active task claims — optionally filter by agent_id."""
            return _json.dumps(_list(agent_id or None))

        @mcp.tool
        async def steal_task(issue_id: str, stealer_id: str, stealer_name: str) -> str:
            """Steal a stale/stealable task from another agent."""
            return _json.dumps(_steal(issue_id, stealer_id, stealer_name))

        @mcp.tool
        async def get_stealable_tasks() -> str:
            """List all tasks currently marked as stealable."""
            return _json.dumps(_stealable())

        @mcp.tool
        async def rebalance_agent_load(agent_ids: str) -> str:
            """Rebalance task load across districts. Pass comma-separated agent IDs."""
            ids = [a.strip() for a in agent_ids.split(",") if a.strip()]
            return _json.dumps(_rebalance(ids))

        @mcp.tool
        async def claim_stats() -> str:
            """Get summary statistics for all task claims."""
            return _json.dumps(_stats())

        logger.info("[VECTOR][mcp] claims tools registered (7 tools)")
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] claims tools unavailable: {e}")

def add_guidance_tools(mcp) -> None:
    """Wire vectorcode/src/guidance.py threat detection into the server."""
    try:
        from vectorcode.src.guidance import create_guidance_system
        import json as _json

        _gsys = None

        def _get_gsys():
            nonlocal _gsys
            if _gsys is None:
                _gsys = create_guidance_system()
            return _gsys

        @mcp.tool
        async def scan_for_threats(text: str, agent_id: str = "user") -> str:
            """Scan text for prompt injection, privilege escalation, or data exfiltration threats."""
            gsys = _get_gsys()
            signals = gsys["threat_detector"].analyze_input(text, agent_id)
            return _json.dumps([{"category": s.category, "severity": s.severity, "description": s.description, "evidence": s.evidence[:2]} for s in signals])

        @mcp.tool
        async def get_agent_coherence(agent_id: str) -> str:
            """Get coherence score and privilege level for a VECTOR agent."""
            gsys = _get_gsys()
            score = gsys["coherence_scheduler"].compute_score(agent_id)
            level = gsys["coherence_scheduler"].get_privilege_level(agent_id)
            return _json.dumps({"agent_id": agent_id, "coherence": round(score.overall * 100, 1), "privilege": level, "components": {"violations": round(score.violation_component, 3), "rework": round(score.rework_component, 3), "drift": round(score.drift_component, 3)}})

        @mcp.tool
        async def check_action_authority(action: str, current_level: str = "agent") -> str:
            """Check if action requires authority escalation (agent→human→institutional)."""
            gsys = _get_gsys()
            irrev = gsys["authority_gate"].classify_action(action)
            needs_esc, req_level = gsys["authority_gate"].requires_escalation(action, current_level)
            return _json.dumps({"action": action, "irreversibility": irrev, "needs_escalation": needs_esc, "required_level": req_level})

        logger.info("[VECTOR][mcp] guidance tools registered (3 tools)")
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] guidance tools unavailable: {e}")

def add_kanban_tools(mcp) -> None:
    """Register kanban task-management tools (4 tools: list, create, update, complete)."""
    try:
        from tools.kanban_tools import (
            list_kanban_tasks,
            create_kanban_task,
            update_kanban_task,
            complete_kanban_task,
        )

        @mcp.tool
        def kanban_list(status: str = "active", limit: int = 20) -> str:
            """List VECTOR kanban tasks. status: active|done|all."""
            return _mcp_call_json(
                "kanban_list",
                list_kanban_tasks,
                status=status,
                limit=limit,
            )

        @mcp.tool
        def kanban_create(title: str, description: str = "", priority: str = "normal") -> str:
            """Create a new kanban task in VECTOR's task board."""
            return _mcp_call_json(
                "kanban_create",
                create_kanban_task,
                title=title,
                description=description,
                priority=priority,
            )

        @mcp.tool
        def kanban_update(task_id: str, status: str = None, description: str = None) -> str:
            """Update a kanban task's status or description."""
            return _mcp_call_json(
                "kanban_update",
                update_kanban_task,
                task_id=task_id,
                status=status,
                description=description,
            )

        @mcp.tool
        def kanban_complete(task_id: str) -> str:
            """Mark a kanban task as complete."""
            return _mcp_call_json("kanban_complete", complete_kanban_task, task_id=task_id)

        logger.info("[VECTOR][mcp] kanban tools registered (4 tools)")
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] kanban tools unavailable: {e}")
