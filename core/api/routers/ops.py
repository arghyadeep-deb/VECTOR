"""VECTOR ops router - /ops/* endpoints."""

__all__ = [
    "error_classify",
    "ErrorClassifyReq",
    "incident_command",
    "IncidentCommandReq",
    "post_mortem",
    "PostMortemReq",
    "router",
    "slo_check",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/ops", tags=["ops"])


class IncidentCommandReq(BaseModel):
    title: str = ""
    severity: str = "medium"
    description: str = ""

@router.post("/incident")
async def incident_command(body: IncidentCommandReq):
    """Trigger incident response."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "incident_command", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][ops] incident_command failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/slo-check")
async def slo_check():
    """Check current SLO status and error budgets."""
    try:
        import datetime

        from core.api.routers.status import get_uptime_seconds

        uptime = get_uptime_seconds()
        return {
            "status": "ok",
            "service": "vector-api",
            "uptime_seconds": uptime,
            "slo": {
                "availability_target": 0.99,
                "latency_p95_ms_target": 1000,
                "error_budget_status": "not_configured",
            },
            "checks": {
                "api_process": "ok",
                "external_monitoring": "not_configured",
                "ops_agents": "not_registered",
            },
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("[VECTOR][ops] slo_check failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class PostMortemReq(BaseModel):
    incident_id: str = ""
    timeline: str = ""
    root_cause: str = ""

@router.post("/post-mortem")
async def post_mortem(body: PostMortemReq):
    """Generate post-mortem analysis."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "post_mortem", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][ops] post_mortem failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class ErrorClassifyReq(BaseModel):
    error_message: str = ""
    stack_trace: str = ""

@router.post("/error-classify")
async def error_classify(body: ErrorClassifyReq):
    """Classify error by category and severity."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "error_classify", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][ops] error_classify failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
