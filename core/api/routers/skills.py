"""VECTOR skills router - /skills/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/skills", tags=["skills"])


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


@router.get("/map")
async def skill_map():
    """Knowledge graph of current skills and proficiency."""
    try:
        return _run("skill_map", {})
    except Exception as e:
        logger.error("[VECTOR][skills] skill_map failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GapAnalysisReq(BaseModel):
    target_role: str = ""
    timeframe: str = "6m"

@router.post("/gap-analysis")
async def gap_analysis(body: GapAnalysisReq):
    """Identify skill gaps toward a goal."""
    try:
        return _run("gap_analysis", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][skills] gap_analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class TrackMasteryReq(BaseModel):
    skill: str = ""
    level: int = 1
    evidence: str = ""

@router.post("/mastery")
async def track_mastery(body: TrackMasteryReq):
    """Track mastery level for a skill."""
    try:
        return _run("track_mastery", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][skills] track_mastery failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class SuggestPracticeReq(BaseModel):
    skill: str = ""
    current_level: int = 1

@router.post("/practice-suggest")
async def suggest_practice(body: SuggestPracticeReq):
    """Suggest targeted practice exercises."""
    try:
        return _run("suggest_practice", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][skills] suggest_practice failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
