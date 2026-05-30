"""VECTOR governance router - /governance/* endpoints."""

__all__ = [
    "autopilot_status",
    "autopilot_trigger",
    "AutopilotTriggerReq",
    "delegate_task",
    "DelegateTaskReq",
    "product_roadmap",
    "ProductRoadmapReq",
    "router",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/governance", tags=["governance"])


class ProductRoadmapReq(BaseModel):
    features: str = ""
    timeline: str = "quarter"
    constraints: str = ""

@router.post("/roadmap")
async def product_roadmap(body: ProductRoadmapReq):
    """Generate product roadmap with RICE scoring."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "product_roadmap", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][governance] product_roadmap failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class DelegateTaskReq(BaseModel):
    task: str = ""
    target_agent: str = ""
    priority: str = "medium"

@router.post("/federation")
async def delegate_task(body: DelegateTaskReq):
    """Delegate task to another agent."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "delegate_task", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][governance] delegate_task failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/autopilot/status")
async def autopilot_status():
    """Autonomous task execution status."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "autopilot_status", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][governance] autopilot_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AutopilotTriggerReq(BaseModel):
    workflow: str = ""
    params: str = ""

@router.post("/autopilot/trigger")
async def autopilot_trigger(body: AutopilotTriggerReq):
    """Trigger autonomous workflow."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "autopilot_trigger", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][governance] autopilot_trigger failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
