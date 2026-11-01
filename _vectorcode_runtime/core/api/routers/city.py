"""VECTOR city router - /city/* endpoints."""

__all__ = [
    "agent_history",
    "AgentHistoryReq",
    "direct_dispatch",
    "DirectDispatchReq",
    "generation_map",
    "list_districts",
    "router",
    "spawn_successor",
    "SpawnSuccessorReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/city", tags=["city"])


@router.get("/districts")
async def list_districts():
    """List all configured districts with real agent counts.

    2026-10-21 (HUD acceptance check): this used to route through
    Governor.dispatch({"type": "list_districts"}) -- a GREEN/UNKNOWN-tier
    task_type with no handler anywhere (not in Governor, not in any
    district agent), so it always landed on whichever district's generic
    "unknown task type" fallback the LLM-based router happened to pick
    (observed: "documentation"), returning HTTP 200 with an internal error
    body. Since frontend/js/widgets.js's health-check only inspects the
    HTTP status (never the payload), the HUD showed this panel as
    permanently "online" despite every real call failing. This is a plain
    read of already-live data -- the same source /status's "agents" block
    already uses -- so it needs no LLM/task dispatch at all.
    """
    try:
        from core.city.agent_registry import get_registry
        agents = get_registry().list_all()
        by_district: dict[str, dict] = {}
        for a in agents:
            d = a.get("district") or "unknown"
            entry = by_district.setdefault(d, {"district": d, "agent_count": 0, "alive": 0})
            entry["agent_count"] += 1
            if a.get("is_alive"):
                entry["alive"] += 1
        districts = sorted(by_district.values(), key=lambda e: e["district"])
        return {"count": len(districts), "total_agents": len(agents), "districts": districts}
    except Exception as e:
        logger.error("[VECTOR][city] list_districts failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class AgentHistoryReq(BaseModel):
    agent_id: str = ""

@router.post("/agents/history")
async def agent_history(body: AgentHistoryReq):
    """Full generation history for an agent."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "agent_history", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][city] agent_history failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/evolution/generations")
async def generation_map():
    """Map of all agent generations."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "generation_map", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][city] generation_map failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class SpawnSuccessorReq(BaseModel):
    dead_agent_id: str = ""
    district: str = ""

@router.post("/evolution/spawn")
async def spawn_successor(body: SpawnSuccessorReq):
    """Spawn a successor agent for a dead agent."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "spawn_successor", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][city] spawn_successor failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class DirectDispatchReq(BaseModel):
    task_type: str = ""
    params: str = ""

@router.post("/dispatch")
async def direct_dispatch(body: DirectDispatchReq):
    """Direct governor dispatch."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "direct_dispatch", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][city] direct_dispatch failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
