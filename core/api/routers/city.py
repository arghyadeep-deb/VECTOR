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
    """List all 47 districts with agent counts."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "list_districts", "params": {}})
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
