"""VECTOR health router - /health/* endpoints."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/health", tags=["health"])




@router.get("/check-fatigue")
async def check_fatigue():
    """Real-time fatigue detection via EAR scoring."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "check_fatigue", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][health] check_fatigue failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class TrackSleepReq(BaseModel):
    duration_hours: float = 0.0
    quality: int = 0
    notes: str = ""

@router.post("/sleep")
async def track_sleep(body: TrackSleepReq):
    """Log and analyze sleep quality."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "track_sleep", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][health] track_sleep failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/biometrics")
async def aggregate_biometrics():
    """Aggregate biometric data."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "aggregate_biometrics", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][health] aggregate_biometrics failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class LogExerciseReq(BaseModel):
    exercise_type: str = "cardio"
    duration_min: int = 30
    intensity: str = "medium"

@router.post("/exercise")
async def log_exercise(body: LogExerciseReq):
    """Log a workout session."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "log_exercise", "params": body.model_dump()})
    except Exception as e:
        logger.error("[VECTOR][health] log_exercise failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def health_status():
    """Overall health district status."""
    from core.city.governor import GovernorCouncil
    gov = GovernorCouncil()
    try:
        return await gov.dispatch({"type": "health_status", "params": {}})
    except Exception as e:
        logger.error("[VECTOR][health] health_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
