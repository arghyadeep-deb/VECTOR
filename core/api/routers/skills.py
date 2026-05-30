"""VECTOR skills router - /skills/* endpoints."""

__all__ = [
    "gap_analysis",
    "GapAnalysisReq",
    "router",
    "skill_map",
    "suggest_practice",
    "SuggestPracticeReq",
    "track_mastery",
    "TrackMasteryReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/map")
async def skill_map():
    """Knowledge graph of current skills and proficiency."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "skill_map", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][skills] skill_map failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GapAnalysisReq(BaseModel):
    target_role: str = ""
    timeframe: str = "6m"

@router.post("/gap-analysis")
async def gap_analysis(body: GapAnalysisReq):
    """Identify skill gaps toward a goal."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "gap_analysis", "params": body.model_dump()})
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
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "track_mastery", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][skills] track_mastery failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class SuggestPracticeReq(BaseModel):
    skill: str = ""
    current_level: int = 1

@router.post("/practice-suggest")
async def suggest_practice(body: SuggestPracticeReq):
    """Suggest targeted practice exercises."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "suggest_practice", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][skills] suggest_practice failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
