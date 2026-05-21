"""VECTOR governance router - /governance/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/governance", tags=["governance"])


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


class ProductRoadmapReq(BaseModel):
    features: str = ""
    timeline: str = "quarter"
    constraints: str = ""

@router.post("/roadmap")
async def product_roadmap(body: ProductRoadmapReq):
    """Generate product roadmap with RICE scoring."""
    try:
        return _run("product_roadmap", body.model_dump())
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
    try:
        return _run("delegate_task", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][governance] delegate_task failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/autopilot/status")
async def autopilot_status():
    """Autonomous task execution status."""
    try:
        return _run("autopilot_status", {})
    except Exception as e:
        logger.error("[VECTOR][governance] autopilot_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class AutopilotTriggerReq(BaseModel):
    workflow: str = ""
    params: str = ""

@router.post("/autopilot/trigger")
async def autopilot_trigger(body: AutopilotTriggerReq):
    """Trigger autonomous workflow."""
    try:
        return _run("autopilot_trigger", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][governance] autopilot_trigger failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
