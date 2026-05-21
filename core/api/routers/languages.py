"""VECTOR languages router - /languages/* endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/languages", tags=["languages"])




class VocabularyPracticeReq(BaseModel):
    word_count: int = 10
    level: str = "beginner"

@router.post("/{lang}/vocabulary")
async def vocabulary_practice(body: VocabularyPracticeReq):
    """Practice vocabulary."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "vocabulary_practice", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][languages] vocabulary_practice failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GrammarPracticeReq(BaseModel):
    topic: str = ""
    level: str = "beginner"

@router.post("/{lang}/grammar")
async def grammar_practice(body: GrammarPracticeReq):
    """Grammar drill."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "grammar_practice", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][languages] grammar_practice failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class DialoguePracticeReq(BaseModel):
    scenario: str = "daily life"
    level: str = "beginner"

@router.post("/{lang}/dialogue")
async def dialogue_practice(body: DialoguePracticeReq):
    """Conversational dialogue practice."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "dialogue_practice", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][languages] dialogue_practice failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class StudyGuideReq(BaseModel):
    current_level: str = "beginner"
    goal: str = "conversational"
    hours_per_week: int = 5

@router.post("/{lang}/study-guide")
async def study_guide(body: StudyGuideReq):
    """Generate personalized study plan."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "study_guide", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][languages] study_guide failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
