"""VECTOR patterns router - /patterns/* endpoints."""

__all__ = [
    "detect_patterns",
    "DetectPatternsReq",
    "generate_insights",
    "GenerateInsightsReq",
    "habit_plan",
    "HabitPlanReq",
    "identify_habits",
    "router",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/patterns", tags=["patterns"])


class DetectPatternsReq(BaseModel):
    days: int = 30
    category: str = "all"

@router.post("/detect")
async def detect_patterns(body: DetectPatternsReq):
    """Detect behavioral patterns from episodic memory."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "detect_patterns", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][patterns] detect_patterns failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/habits")
async def identify_habits():
    """Identify recurring habits (positive and negative)."""
    try:
        from core.api.crud import recall_episodes

        events = recall_episodes("habits", limit=10, event_type="habits_found")
        habits = []
        for event in events:
            habits.append({
                "timestamp": event.get("timestamp"),
                "content": event.get("content", ""),
                "source": event.get("source", "memory"),
                "tags": event.get("tags", []),
            })
        return {
            "status": "ok",
            "habits": habits,
            "count": len(habits),
            "note": "Use POST /patterns/detect to run fresh pattern analysis.",
        }
    except Exception as e:
        logger.error("[VECTOR][patterns] identify_habits failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class GenerateInsightsReq(BaseModel):
    pattern_type: str = "all"

@router.post("/insights")
async def generate_insights(body: GenerateInsightsReq):
    """Generate actionable insights from patterns."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "generate_insights", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][patterns] generate_insights failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))

class HabitPlanReq(BaseModel):
    habit: str = ""
    goal: str = "break"

@router.post("/habit-plan")
async def habit_plan(body: HabitPlanReq):
    """Create habit change intervention plan."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "habit_plan", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][patterns] habit_plan failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
