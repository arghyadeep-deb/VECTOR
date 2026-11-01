"""VECTOR skills router - /skills/* endpoints."""

import json

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


def _json_list(value: str | None) -> list:
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


@router.get("/map")
async def skill_map():
    """Knowledge graph of current skills and proficiency."""
    try:
        from core.memory.episodic import EpisodicMemory

        memory = EpisodicMemory()
        cursor = memory.conn.execute(
            """
            SELECT skill_name, confidence, last_practiced, evidence, related_skills
            FROM skill_memory
            ORDER BY confidence DESC, skill_name ASC
            LIMIT 200
            """
        )
        skills = []
        for row in cursor.fetchall():
            skill_name, confidence, last_practiced, evidence_raw, related_raw = row
            evidence = _json_list(evidence_raw)
            related_skills = _json_list(related_raw)
            skills.append(
                {
                    "skill_name": skill_name,
                    "confidence": confidence,
                    "last_practiced": last_practiced,
                    "evidence": evidence,
                    "related_skills": related_skills,
                }
            )
        return {"status": "ok", "skills": skills, "count": len(skills), "source": "skill_memory"}
    except Exception as e:
        logger.error("[VECTOR][skills] skill_map failed: {}", e)
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
        logger.error("[VECTOR][skills] gap_analysis failed: {}", e)
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
        logger.error("[VECTOR][skills] track_mastery failed: {}", e)
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
        logger.error("[VECTOR][skills] suggest_practice failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
