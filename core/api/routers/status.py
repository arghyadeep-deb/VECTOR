"""Status router — /status, /health."""

import sys
import time
import datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import httpx

from core.api.schemas import StatusResponse, HealthResponse
from core.api.crud import get_memory_stats
from core.config import CONFIG

router = APIRouter(tags=["status"])

_OLLAMA_HOST = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
if not _OLLAMA_HOST.startswith("http"):
    _OLLAMA_HOST = "http://" + _OLLAMA_HOST

START_TIME = dt.datetime.now(dt.timezone.utc)


def get_uptime_seconds() -> int:
    return int((dt.datetime.now(dt.timezone.utc) - START_TIME).total_seconds())

@router.get("/status", response_model=StatusResponse)
async def status_endpoint():
    """Get current VECTOR status."""
    try:
        memory_stats = get_memory_stats()
    except Exception as e:
        logger.warning(f"[VECTOR][api][status] memory stats failed: {e}")
        memory_stats = {"error": str(e)}

    try:
        from core.city.agent_registry import get_registry
        agents = get_registry().list_all()
        agent_count = len(agents)
        districts = sorted({a.get("district", "") for a in agents})
    except Exception as e:
        logger.warning(f"[VECTOR][api][status] agent list failed: {e}")
        agents = []
        agent_count = 0
        districts = []

    # Dynamically check Ollama models
    models_status = await _check_ollama_models()

    # Last reflect timestamp from episodic memory
    last_reflect = None
    try:
        from core.api.crud import recall_episodes
        reflect_events = recall_episodes("reflect daily review", limit=1, event_type="reflect")
        if reflect_events:
            last_reflect = reflect_events[0].get("timestamp")
    except Exception:
        pass

    return StatusResponse(
        loop_running=True,
        uptime_seconds=get_uptime_seconds(),
        models=models_status,
        memory=memory_stats,
        agents={"count": agent_count, "districts": districts},
        vector_version="1.0.0",
        last_reflect=last_reflect,
    )

@router.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """Detailed health check for monitoring."""
    import datetime
    checks = {}

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_OLLAMA_HOST}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else f"http_{r.status_code}"
    except Exception as e:
        checks["ollama"] = f"error: {e}"

    # Check SQLite
    try:
        memory_stats = get_memory_stats()
        checks["sqlite"] = "ok" if memory_stats and "error" not in memory_stats else "error"
    except Exception as e:
        checks["sqlite"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())

    return HealthResponse(
        status="ok" if all_ok else "degraded",
        checks=checks,
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        version="1.0.0",
    )

async def _check_ollama_models() -> dict:
    """Dynamically check which Ollama models are loaded."""
    models_status = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                loaded = [m["name"] for m in r.json().get("models", [])]
                # Check key models
                for model_key in ["focus", "reasoning", "coder", "ambient", "deep", "chairman"]:
                    model_name = {
                        "focus": "vector-focus",
                        "reasoning": "vector-reasoning",
                        "coder": "vector-coder",
                        "ambient": "vector-ambient",
                        "deep": "vector-deep",
                        "chairman": "vector-chairman",
                    }.get(model_key, model_key)

                    models_status[model_key] = "loaded" if model_name in loaded else "unloaded"
            else:
                for key in ["focus", "reasoning", "coder", "ambient", "deep", "chairman"]:
                    models_status[key] = "error"
    except Exception as e:
        logger.warning(f"[VECTOR][api][status] Ollama check failed: {e}")
        models_status = {"focus": "unavailable", "reasoning": "unavailable"}

    if not models_status:
        models_status = {"focus": "unknown", "reasoning": "unknown"}

    return models_status


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ status.py OK")
