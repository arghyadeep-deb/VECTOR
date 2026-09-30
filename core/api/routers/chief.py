"""VECTOR chief router - /chief/* endpoints."""

__all__ = [
    "evening_brief",
    "executive_brief",
    "ExecutiveBriefReq",
    "filter_noise",
    "FilterNoiseReq",
    "morning_brief",
    "route_escalation",
    "RouteEscalationReq",
    "router",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/chief", tags=["chief"])


@router.get("/morning-brief")
async def morning_brief():
    """Get the 08:00 executive morning brief."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "morning_brief", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][chief] morning_brief failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/evening-brief")
async def evening_brief():
    """Get the 22:00 accomplishment summary."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "evening_brief", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][chief] evening_brief failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class ExecutiveBriefReq(BaseModel):
    topics: str = "all"
    format: str = "bullets"

@router.post("/executive-brief")
async def executive_brief(body: ExecutiveBriefReq):
    """Generate executive brief."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "executive_brief", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][chief] executive_brief failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class RouteEscalationReq(BaseModel):
    task: str = ""
    urgency: str = "medium"

@router.post("/route-escalation")
async def route_escalation(body: RouteEscalationReq):
    """Intelligently route a task."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "route_escalation", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][chief] route_escalation failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class FilterNoiseReq(BaseModel):
    events: str = ""

@router.post("/filter-noise")
async def filter_noise(body: FilterNoiseReq):
    """Classify events as SIGNAL/ROUTINE/NOISE."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "filter_noise", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][chief] filter_noise failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
