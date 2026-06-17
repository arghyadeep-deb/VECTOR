import time
import datetime
import hmac
import os
import sys
from typing import Optional

try:
    from core.config import CONFIG
except Exception:
    # Fallback when deployed to cloud without full VECTOR codebase
    from vector_config import CONFIG  # type: ignore[import]

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


def _is_production() -> bool:
    env = str(os.environ.get("VECTOR_ENV") or CONFIG.get("env", "production")).strip().lower()
    return env in {"prod", "production"}


def _allowed_origins() -> list[str]:
    origins = list(CONFIG.get("allowed_origins", []))
    if _is_production() and "*" in origins:
        logger.warning(
            "[VECTOR][brain_server] refusing wildcard CORS in production; "
            "set VECTOR_ALLOWED_ORIGINS explicitly"
        )
        return []
    return origins

app = FastAPI(
    title="VECTOR Brain Server",
    description="VECTOR autonomous AI — cloud API gateway",
    version=CONFIG.get("version", "0.0.0"),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
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
        if _is_production():
            return JSONResponse(
                status_code=503,
                content={"detail": "Brain server auth not configured: set VECTOR_API_KEY."},
            )
        return await call_next(request)
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if not token or not hmac.compare_digest(token, _API_KEY):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


def _uptime() -> float:
    return round(time.time() - _START_TIME, 1)


# ── Cloud data source ──────────────────────────────────────────────────────────
# On the Fly VM there is no local SQLite file — the data lives in the cloud mesh.
# These helpers read Supabase (the cloud source of truth) so remote endpoints
# return real data. On the co-located laptop, endpoints fall back to local core.

def _supabase_creds():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY", "")
    return (url, key) if url and key else (None, None)


async def _supabase_episodic(event_type: Optional[str] = None, limit: int = 10):
    """Read episodic_memory from Supabase. Returns list, or None if unconfigured/failed."""
    url, key = _supabase_creds()
    if not url or not key:
        return None
    try:
        import httpx
        params = {
            "select": "id,event_type,content,tags,timestamp,source",
            "order": "timestamp.desc",
            "limit": str(limit),
        }
        if event_type:
            params["event_type"] = f"eq.{event_type}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(
                f"{url}/rest/v1/episodic_memory",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params=params,
            )
            if r.status_code == 200:
                return r.json()
            logger.warning(f"[VECTOR][brain_server] Supabase {r.status_code}")
    except Exception as e:
        logger.warning(f"[VECTOR][brain_server] Supabase read failed: {e}")
    return None


# ── Core endpoints ─────────────────────────────────────────────────────────────

@app.get("/status")
async def status():
    """Day 6 gate — returns 200 when VECTOR brain server is online."""
    return {
        "status": "online",
        "system": CONFIG.get("system_name", "VECTOR"),
        "version": CONFIG.get("version", "0.0.0"),
        "environment": CONFIG.get("env", os.environ.get("VECTOR_ENV", "development")),
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
    """List agents. Local (co-located) gives the live roster; remote (Fly) returns
    heartbeat-derived counts since the live roster isn't synced to the cloud."""
    try:
        from core.city.agent_registry import AgentRegistry
        agents = AgentRegistry().list_all()
        return {"agents": agents, "count": len(agents), "source": "local"}
    except Exception:
        hb = _heartbeat_data or {}
        return {
            "agents": [],
            "count": hb.get("agents_alive", hb.get("total_agents", 0)),
            "source": "heartbeat",
            "heartbeat": hb,
            "note": "live agent roster is laptop-local; showing last heartbeat",
        }


@app.get("/memory/recent")
async def recent_memory(limit: int = Query(10, ge=1, le=50)):
    """Recent episodic events — cloud (Supabase) first, local fallback."""
    rows = await _supabase_episodic(limit=limit)
    if rows is not None:
        return {"events": rows, "count": len(rows), "source": "supabase"}
    try:
        from core.memory.episodic import EpisodicMemory
        events = EpisodicMemory().recall("", limit=limit)
        return {"events": events, "count": len(events), "source": "local"}
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
    """Recent council sessions — cloud (Supabase) first, local fallback."""
    rows = await _supabase_episodic(event_type="council_session", limit=limit)
    if rows is not None:
        return {"sessions": rows, "count": len(rows), "source": "supabase"}
    try:
        from core.memory.episodic import EpisodicMemory
        sessions = EpisodicMemory().recall("council", limit=limit, event_type="council_session")
        return {"sessions": sessions, "count": len(sessions), "source": "local"}
    except Exception as e:
        return {"sessions": [], "count": 0, "error": str(e)}


@app.get("/security/recent")
async def security_recent(limit: int = Query(10, ge=1, le=50)):
    """Recent security events — cloud (Supabase) first, local fallback."""
    rows = await _supabase_episodic(event_type="security_scan", limit=limit)
    if rows is not None:
        return {"events": rows, "count": len(rows), "source": "supabase"}
    try:
        from core.memory.episodic import EpisodicMemory
        events = EpisodicMemory().recall("threat", limit=limit, event_type="security_scan")
        return {"events": events, "count": len(events), "source": "local"}
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
