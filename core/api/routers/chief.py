"""VECTOR chief router - /chief/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/chief", tags=["chief"])


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


@router.get("/morning-brief")
async def morning_brief():
    """Get the 08:00 executive morning brief."""
    try:
        return _run("morning_brief", {})
    except Exception as e:
        logger.error("[VECTOR][chief] morning_brief failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/evening-brief")
async def evening_brief():
    """Get the 22:00 accomplishment summary."""
    try:
        return _run("evening_brief", {})
    except Exception as e:
        logger.error("[VECTOR][chief] evening_brief failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ExecutiveBriefReq(BaseModel):
    topics: str = "all"
    format: str = "bullets"

@router.post("/executive-brief")
async def executive_brief(body: ExecutiveBriefReq):
    """Generate executive brief."""
    try:
        return _run("executive_brief", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][chief] executive_brief failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RouteEscalationReq(BaseModel):
    task: str = ""
    urgency: str = "medium"

@router.post("/route-escalation")
async def route_escalation(body: RouteEscalationReq):
    """Intelligently route a task."""
    try:
        return _run("route_escalation", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][chief] route_escalation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class FilterNoiseReq(BaseModel):
    events: str = ""

@router.post("/filter-noise")
async def filter_noise(body: FilterNoiseReq):
    """Classify events as SIGNAL/ROUTINE/NOISE."""
    try:
        return _run("filter_noise", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][chief] filter_noise failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
