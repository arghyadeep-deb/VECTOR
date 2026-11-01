"""VECTOR reflection router - /reflection/* endpoints."""

__all__ = [
    "daily_review",
    "DailyReviewReq",
    "growth_analysis",
    "GrowthAnalysisReq",
    "journal_entry",
    "JournalEntryReq",
    "router",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/reflection", tags=["reflection"])


class DailyReviewReq(BaseModel):
    force: bool = False

@router.post("/daily-review")
async def daily_review(body: DailyReviewReq):
    """Run VECTOR daily reflection."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "daily_review", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][reflection] daily_review failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class JournalEntryReq(BaseModel):
    mood: str = "neutral"
    highlights: str = ""
    lessons: str = ""

@router.post("/journal")
async def journal_entry(body: JournalEntryReq):
    """Write structured journal entry."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "journal_entry", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][reflection] journal_entry failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class GrowthAnalysisReq(BaseModel):
    period: str = "7d"

@router.post("/growth-analysis")
async def growth_analysis(body: GrowthAnalysisReq):
    """Analyze progress and growth metrics."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "growth_analysis", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][reflection] growth_analysis failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
