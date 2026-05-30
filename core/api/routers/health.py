"""VECTOR health router - /health/* endpoints."""

__all__ = [
    "aggregate_biometrics",
    "check_fatigue",
    "health_status",
    "log_exercise",
    "LogExerciseReq",
    "router",
    "track_sleep",
    "TrackSleepReq",
]

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


@router.get("/system")
async def system_health():
    """System-level health: DB, Ollama, memory, loop. Used by monitoring and load balancers."""
    import datetime
    checks: dict[str, dict] = {}
    all_ok = True

    # 1. Episodic DB
    try:
        from core.memory.episodic import EpisodicMemory
        stats = EpisodicMemory().get_stats()
        checks["db"] = {"status": "ok", "episodic_rows": stats.get("episodic_memory", 0)}
    except Exception as e:
        checks["db"] = {"status": "error", "error": str(e)}
        all_ok = False

    # 2. Ollama reachability
    try:
        import httpx
        from core.config import CONFIG
        ollama_host = CONFIG["ollama_host"]  # e.g. "http://127.0.0.1:11434"
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{ollama_host}/api/tags")
            model_count = len(r.json().get("models", []))
        checks["ollama"] = {"status": "ok", "models": model_count}
    except Exception as e:
        checks["ollama"] = {"status": "error", "error": str(e)}
        all_ok = False

    # 3. Autonomous loop tick count (advancing = loop is running)
    try:
        from core.loop import autonomous_loop as _al_mod
        _loop_instance = getattr(_al_mod, "_loop", None)
        ticks = getattr(_loop_instance, "_tick_count", None)
        if ticks is not None:
            checks["loop"] = {"status": "ok", "tick_count": ticks, "running": getattr(_loop_instance, "_running", False)}
        else:
            checks["loop"] = {"status": "not_started", "note": "loop not yet initialised"}
    except Exception as e:
        checks["loop"] = {"status": "unknown", "note": str(e)}

    # 4. Memory stats
    try:
        from core.memory.episodic import EpisodicMemory
        stats = EpisodicMemory().get_stats()
        checks["memory"] = {
            "status": "ok",
            "episodic": stats.get("episodic_memory", 0),
            "reasoning_chains": stats.get("reasoning_chains", 0),
            "policy_entries": stats.get("policy_memory", 0),
        }
    except Exception as e:
        checks["memory"] = {"status": "error", "error": str(e)}
        all_ok = False

    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
