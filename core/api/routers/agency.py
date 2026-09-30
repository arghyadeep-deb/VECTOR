"""VECTOR agency router - /agency/* endpoints."""

__all__ = [
    "analyze_trends",
    "AnalyzeTrendsReq",
    "create_content_plan",
    "CreateContentPlanReq",
    "roi_analysis",
    "RoiAnalysisReq",
    "router",
    "suggest_topics",
    "SuggestTopicsReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/agency", tags=["agency"])


class AnalyzeTrendsReq(BaseModel):
    niche: str = ""
    platform: str = "all"
    days: int = 30

@router.post("/trends")
async def analyze_trends(body: AnalyzeTrendsReq):
    """Analyze content trends for a niche."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "analyze_trends", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][agency] analyze_trends failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class SuggestTopicsReq(BaseModel):
    niche: str = ""
    count: int = 10
    format: str = "blog"

@router.post("/topics")
async def suggest_topics(body: SuggestTopicsReq):
    """Generate content topic ideas."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "suggest_topics", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][agency] suggest_topics failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class CreateContentPlanReq(BaseModel):
    brand: str = ""
    goal: str = ""
    weeks: int = 4

@router.post("/content-plan")
async def create_content_plan(body: CreateContentPlanReq):
    """Create structured content plan."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "create_content_plan", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][agency] create_content_plan failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class RoiAnalysisReq(BaseModel):
    campaign: str = ""
    spend: float = 0.0
    revenue: float = 0.0

@router.post("/roi")
async def roi_analysis(body: RoiAnalysisReq):
    """Performance tracking and ROI analysis."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "roi_analysis", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][agency] roi_analysis failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
