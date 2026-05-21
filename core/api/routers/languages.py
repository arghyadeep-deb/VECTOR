"""VECTOR languages router - /languages/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/languages", tags=["languages"])


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


class VocabularyPracticeReq(BaseModel):
    word_count: int = 10
    level: str = "beginner"

@router.post("/{lang}/vocabulary")
async def vocabulary_practice(body: VocabularyPracticeReq):
    """Practice vocabulary."""
    try:
        return _run("vocabulary_practice", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][languages] vocabulary_practice failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GrammarPracticeReq(BaseModel):
    topic: str = ""
    level: str = "beginner"

@router.post("/{lang}/grammar")
async def grammar_practice(body: GrammarPracticeReq):
    """Grammar drill."""
    try:
        return _run("grammar_practice", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][languages] grammar_practice failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class DialoguePracticeReq(BaseModel):
    scenario: str = "daily life"
    level: str = "beginner"

@router.post("/{lang}/dialogue")
async def dialogue_practice(body: DialoguePracticeReq):
    """Conversational dialogue practice."""
    try:
        return _run("dialogue_practice", body.model_dump())
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
    try:
        return _run("study_guide", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][languages] study_guide failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
