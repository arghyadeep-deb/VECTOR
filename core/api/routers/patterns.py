"""VECTOR patterns router - /patterns/* endpoints."""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/patterns", tags=["patterns"])


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


class DetectPatternsReq(BaseModel):
    days: int = 30
    category: str = "all"

@router.post("/detect")
async def detect_patterns(body: DetectPatternsReq):
    """Detect behavioral patterns from episodic memory."""
    try:
        return _run("detect_patterns", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][patterns] detect_patterns failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/habits")
async def identify_habits():
    """Identify recurring habits (positive and negative)."""
    try:
        return _run("identify_habits", {})
    except Exception as e:
        logger.error("[VECTOR][patterns] identify_habits failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateInsightsReq(BaseModel):
    pattern_type: str = "all"

@router.post("/insights")
async def generate_insights(body: GenerateInsightsReq):
    """Generate actionable insights from patterns."""
    try:
        return _run("generate_insights", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][patterns] generate_insights failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class HabitPlanReq(BaseModel):
    habit: str = ""
    goal: str = "break"

@router.post("/habit-plan")
async def habit_plan(body: HabitPlanReq):
    """Create habit change intervention plan."""
    try:
        return _run("habit_plan", body.model_dump())
    except Exception as e:
        logger.error("[VECTOR][patterns] habit_plan failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
