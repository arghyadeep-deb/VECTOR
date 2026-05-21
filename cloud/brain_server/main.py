import sys
import time
import datetime
import os
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from loguru import logger

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

_START_TIME = time.time()
_last_heartbeat: Optional[str] = None
_heartbeat_data: dict = {}

# API key read from environment — never hardcoded
_API_KEY: str = os.environ.get("VECTOR_API_KEY", "")
_PUBLIC_PATHS = {"/status", "/health", "/docs", "/openapi.json", "/redoc"}

app = FastAPI(
    title="VECTOR Brain Server",
    description="VECTOR autonomous AI — cloud API gateway",
    version=CONFIG["version"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CONFIG["allowed_origins"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    """Require Bearer token for all non-public endpoints."""
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    if not _API_KEY:
        # No key configured — allow (dev mode / local)
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != _API_KEY:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


def _uptime() -> float:
    return round(time.time() - _START_TIME, 1)


# ── Core endpoints ─────────────────────────────────────────────────────────────

@app.get("/status")
async def status():
    """Day 6 gate — returns 200 when VECTOR brain server is online."""
    return {
        "status": "online",
        "system": CONFIG["system_name"],
        "version": CONFIG["version"],
        "environment": CONFIG["env"],
        "uptime_sec": _uptime(),
        "last_heartbeat": _last_heartbeat,
    }


@app.get("/health")
async def health():
    """Detailed health for Fly.io monitoring (used as the health check path)."""
    db_ok = False
    stats: dict = {}
    try:
        from core.memory.episodic import EpisodicMemory
        stats = EpisodicMemory().get_stats()
        db_ok = True
    except Exception as e:
        logger.warning(f"[VECTOR][brain_server] DB unavailable: {e}")

    return {
        "status": "healthy" if db_ok else "degraded",
        "uptime_sec": _uptime(),
        "db_connected": db_ok,
        "memory_stats": stats,
    }


@app.get("/agents")
async def list_agents():
    """List all registered agents with HP."""
    try:
        from core.city.agent_registry import AgentRegistry
        agents = AgentRegistry().list_all()
        return {"agents": agents, "count": len(agents)}
    except Exception as e:
        logger.warning(f"[VECTOR][brain_server] agents failed: {e}")
        return {"agents": [], "count": 0, "error": str(e)}


@app.get("/memory/recent")
async def recent_memory(limit: int = Query(10, ge=1, le=50)):
    """Recent episodic events."""
    try:
        from core.memory.episodic import EpisodicMemory
        events = EpisodicMemory().recall("", limit=limit)
        return {"events": events, "count": len(events)}
    except Exception as e:
        return {"events": [], "count": 0, "error": str(e)}


@app.get("/goals")
async def get_goals():
    """Current VECTOR goals and immediate actions."""
    try:
        from core.brain.goal_system import GoalSystem
        actions = GoalSystem().generate_immediate_actions()
        return {"immediate_actions": actions}
    except Exception as e:
        return {"immediate_actions": [], "error": str(e)}


@app.get("/council/history")
async def council_history(limit: int = Query(5, ge=1, le=20)):
    """Recent council sessions from episodic memory."""
    try:
        from core.memory.episodic import EpisodicMemory
        sessions = EpisodicMemory().recall("council", limit=limit, event_type="council_session")
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        return {"sessions": [], "count": 0, "error": str(e)}


@app.get("/security/recent")
async def security_recent(limit: int = Query(10, ge=1, le=50)):
    """Recent security events."""
    try:
        from core.memory.episodic import EpisodicMemory
        events = EpisodicMemory().recall("threat", limit=limit, event_type="security_scan")
        return {"events": events, "count": len(events)}
    except Exception as e:
        return {"events": [], "count": 0, "error": str(e)}


# ── Push endpoints (local VECTOR → cloud) ─────────────────────────────────────

@app.post("/heartbeat")
async def receive_heartbeat(data: dict):
    """Receive a heartbeat push from the local VECTOR instance (Legion Pro 5)."""
    global _last_heartbeat, _heartbeat_data
    _last_heartbeat = datetime.datetime.now().isoformat()
    _heartbeat_data = data
    logger.info(f"[VECTOR][brain_server] heartbeat: {list(data.keys())}")
    return {"ok": True, "received_at": _last_heartbeat}


@app.get("/heartbeat")
async def get_heartbeat():
    """Return last heartbeat from local instance."""
    return {
        "last_heartbeat": _last_heartbeat,
        "data": _heartbeat_data,
        "age_sec": (
            round((datetime.datetime.now() - datetime.datetime.fromisoformat(_last_heartbeat)).total_seconds())
            if _last_heartbeat else None
        ),
    }


# ── Failover API (resilience hot-failover) ────────────────────────────────────

try:
    from core.resilience.hot_failover_api import router as failover_router
    app.include_router(failover_router)
    logger.info("[VECTOR][brain_server] failover API router registered")
except Exception as e:
    logger.warning(f"[VECTOR][brain_server] failover API router failed: {e}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"[VECTOR][brain_server] starting on :{port}")
    uvicorn.run("main:app", host=os.environ.get("BIND_HOST", "0.0.0.0"), port=port, log_level="info", reload=False)
