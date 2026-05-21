"""VECTOR ops router - /ops/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/ops", tags=["ops"])


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


class IncidentCommandReq(BaseModel):
    title: str = ""
    severity: str = "medium"
    description: str = ""

@router.post("/incident")
async def incident_command(body: IncidentCommandReq):
    """Trigger incident response."""
    try:
        return _run("incident_command", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][ops] incident_command failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/slo-check")
async def slo_check():
    """Check current SLO status and error budgets."""
    try:
        return _run("slo_check", {})
    except Exception as e:
        logger.error("[VECTOR][ops] slo_check failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class PostMortemReq(BaseModel):
    incident_id: str = ""
    timeline: str = ""
    root_cause: str = ""

@router.post("/post-mortem")
async def post_mortem(body: PostMortemReq):
    """Generate post-mortem analysis."""
    try:
        return _run("post_mortem", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][ops] post_mortem failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class ErrorClassifyReq(BaseModel):
    error_message: str = ""
    stack_trace: str = ""

@router.post("/error-classify")
async def error_classify(body: ErrorClassifyReq):
    """Classify error by category and severity."""
    try:
        return _run("error_classify", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][ops] error_classify failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
