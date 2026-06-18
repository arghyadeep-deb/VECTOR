"""VECTOR health router - /health/* endpoints."""

__all__ = [
    "aggregate_biometrics",
    "check_fatigue",
    "doctor",
    "health_status",
    "log_exercise",
    "LogExerciseReq",
    "readiness",
    "production_readiness",
    "router",
    "track_sleep",
    "TrackSleepReq",
]

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger
from core.api.cache import health_cache

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
    try:
        import datetime

        from core.city.agent_registry import get_registry

        health_agents = get_registry().get_by_district("health")
        return {
            "status": "ok",
            "district": "health",
            "agents": [
                {
                    "id": getattr(agent, "id", ""),
                    "name": getattr(agent, "name", "unknown"),
                    "health_points": getattr(agent, "health_points", 0),
                    "is_alive": bool(getattr(agent, "health_points", 0) > 0),
                }
                for agent in health_agents
            ],
            "capabilities": ["check_fatigue", "track_sleep", "aggregate_biometrics", "log_exercise"],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("[VECTOR][health] health_status failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/readiness")
async def readiness():
    """Core runtime readiness for local production-style operation."""
    from core.runtime.doctor import run_dependency_doctor

    report = run_dependency_doctor(include_optional=False).to_dict()
    if report["required_failed"]:
        raise HTTPException(status_code=503, detail=report)
    return report


@router.get("/production-readiness")
async def production_readiness():
    """Strict production readiness: secrets, approval, encryption, and sidecars."""
    from core.runtime.doctor import run_dependency_doctor

    report = run_dependency_doctor(include_optional=True, production=True).to_dict()
    if report["required_failed"]:
        raise HTTPException(status_code=503, detail=report)
    return report


@router.get("/doctor")
async def doctor():
    """Full offline-safe dependency doctor, including optional warning checks."""
    from core.runtime.doctor import run_dependency_doctor

    report = run_dependency_doctor(include_optional=True).to_dict()
    if report["required_failed"]:
        raise HTTPException(status_code=503, detail=report)
    return report


@router.get("/system")
async def system_health():
    """System-level health: DB, Ollama, memory, loop. Used by monitoring and load balancers."""
    cached = health_cache.get("system")
    if cached:
        return cached
    import datetime
    import psutil
    checks: dict[str, dict] = {}
    all_ok = True

    # 0. Real-time system resources
    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        checks["system"] = {
            "status": "ok",
            "cpu_percent": cpu_pct,
            "mem_used_percent": round(mem.percent, 1),
            "mem_available_mb": round(mem.available / (1024 * 1024), 1),
            "mem_total_mb": round(mem.total / (1024 * 1024), 1),
        }
    except Exception as e:
        checks["system"] = {"status": "error", "error": str(e)}
        all_ok = False

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
        ollama_host = CONFIG["ollama_host"]
        if not ollama_host.startswith(("http://", "https://")):
            ollama_host = f"http://{ollama_host}"
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{ollama_host}/api/tags")
            model_count = len(r.json().get("models", []))
        checks["ollama"] = {"status": "ok", "models": model_count}
    except Exception as e:
        checks["ollama"] = {"status": "error", "error": str(e)}
        all_ok = False

    # 3. Autonomous loop tick count (advancing = loop is running)
    try:
        from core.loop.loop_state import get_runtime as _get_rt
        rt = _get_rt()
        if rt["running"] or rt["tick_count"] > 0:
            checks["loop"] = {"status": "ok", "tick_count": rt["tick_count"], "running": rt["running"]}
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

    result = {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    health_cache.set("system", result)
    return result
