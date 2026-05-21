"""VECTOR city router - /city/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/city", tags=["city"])


def _run(task_type: str, params: dict) -> dict:
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            gov.dispatch({"type": task_type, "params": params})
        )
    finally:
        loop.close()
    return result


@router.get("/districts")
async def list_districts():
    """List all 47 districts with agent counts."""
    try:
        return _run("list_districts", {})
    except Exception as e:
        logger.error("[VECTOR][city] list_districts failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AgentHistoryReq(BaseModel):
    agent_id: str = ""

@router.post("/agents/history")
async def agent_history(body: AgentHistoryReq):
    """Full generation history for an agent."""
    try:
        return _run("agent_history", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][city] agent_history failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/evolution/generations")
async def generation_map():
    """Map of all agent generations."""
    try:
        return _run("generation_map", {})
    except Exception as e:
        logger.error("[VECTOR][city] generation_map failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class SpawnSuccessorReq(BaseModel):
    dead_agent_id: str = ""
    district: str = ""

@router.post("/evolution/spawn")
async def spawn_successor(body: SpawnSuccessorReq):
    """Spawn a successor agent for a dead agent."""
    try:
        return _run("spawn_successor", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][city] spawn_successor failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class DirectDispatchReq(BaseModel):
    task_type: str = ""
    params: str = ""

@router.post("/dispatch")
async def direct_dispatch(body: DirectDispatchReq):
    """Direct governor dispatch."""
    try:
        return _run("direct_dispatch", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][city] direct_dispatch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
