"""VECTOR reflection router - /reflection/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/reflection", tags=["reflection"])


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


class DailyReviewReq(BaseModel):
    force: bool = False

@router.post("/daily-review")
async def daily_review(body: DailyReviewReq):
    """Run VECTOR daily reflection."""
    try:
        return _run("daily_review", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][reflection] daily_review failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class JournalEntryReq(BaseModel):
    mood: str = "neutral"
    highlights: str = ""
    lessons: str = ""

@router.post("/journal")
async def journal_entry(body: JournalEntryReq):
    """Write structured journal entry."""
    try:
        return _run("journal_entry", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][reflection] journal_entry failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GrowthAnalysisReq(BaseModel):
    period: str = "7d"

@router.post("/growth-analysis")
async def growth_analysis(body: GrowthAnalysisReq):
    """Analyze progress and growth metrics."""
    try:
        return _run("growth_analysis", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][reflection] growth_analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
