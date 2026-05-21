"""VECTOR agency router - /agency/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/agency", tags=["agency"])


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


class AnalyzeTrendsReq(BaseModel):
    niche: str = ""
    platform: str = "all"
    days: int = 30

@router.post("/trends")
async def analyze_trends(body: AnalyzeTrendsReq):
    """Analyze content trends for a niche."""
    try:
        return _run("analyze_trends", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][agency] analyze_trends failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class SuggestTopicsReq(BaseModel):
    niche: str = ""
    count: int = 10
    format: str = "blog"

@router.post("/topics")
async def suggest_topics(body: SuggestTopicsReq):
    """Generate content topic ideas."""
    try:
        return _run("suggest_topics", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][agency] suggest_topics failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class CreateContentPlanReq(BaseModel):
    brand: str = ""
    goal: str = ""
    weeks: int = 4

@router.post("/content-plan")
async def create_content_plan(body: CreateContentPlanReq):
    """Create structured content plan."""
    try:
        return _run("create_content_plan", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][agency] create_content_plan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class RoiAnalysisReq(BaseModel):
    campaign: str = ""
    spend: float = 0.0
    revenue: float = 0.0

@router.post("/roi")
async def roi_analysis(body: RoiAnalysisReq):
    """Performance tracking and ROI analysis."""
    try:
        return _run("roi_analysis", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][agency] roi_analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
