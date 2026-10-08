"""Memory router — /memory endpoints."""

import sys

__all__ = [
    "backup_memory",
    "council_history",
    "goals_endpoint",
    "recent_memory",
    "recent_memory_by_type",
    "restore_memory",
    "router",
    "training_data",
]


from fastapi import APIRouter, Query, HTTPException
from loguru import logger

from core.api.schemas import MemoryRecentResponse, GoalsResponse, CouncilHistoryResponse
from core.api.crud import recall_episodes, get_immediate_actions, get_training_data
from core.api.cache import memory_cache, goals_cache

router = APIRouter(prefix="/memory", tags=["memory"])

@router.get("/recent", response_model=MemoryRecentResponse)
async def recent_memory(limit: int = Query(10, ge=1, le=50)):
    """Get recent episodic events from memory."""
    key = f"recent_{limit}"
    cached = memory_cache.get(key)
    if cached:
        return cached
    try:
        events = recall_episodes("", limit=limit)
        result = MemoryRecentResponse(events=events, count=len(events))
        memory_cache.set(key, result)
        return result
    except Exception as e:
        logger.error(f"[VECTOR][api][memory] recent failed: {e}")
        return MemoryRecentResponse(events=[], count=0, error=str(e))

@router.get("/recent/{event_type}", response_model=MemoryRecentResponse)
async def recent_memory_by_type(event_type: str, limit: int = Query(10, ge=1, le=50)):
    """Get recent episodes filtered by event type."""
    try:
        events = recall_episodes("", limit=limit, event_type=event_type)
        return MemoryRecentResponse(events=events, count=len(events))
    except Exception as e:
        logger.error(f"[VECTOR][api][memory] type filter failed: {e}")
        return MemoryRecentResponse(events=[], count=0, error=str(e))

@router.get("/training-data")
async def training_data(limit: int = Query(100, ge=1, le=500)):
    """Get reasoning chains marked as training data."""
    try:
        data = get_training_data(limit=limit)
        return {"training_data": data, "count": len(data)}
    except Exception as e:
        logger.error(f"[VECTOR][api][memory] training data failed: {e}")
        return {"training_data": [], "count": 0, "error": str(e)}


@router.get("/goals", response_model=GoalsResponse)
async def goals_endpoint():
    """Get current goals and immediate actions."""
    cached = goals_cache.get("active")
    if cached:
        return cached
    try:
        actions = get_immediate_actions(limit=5)
        result = GoalsResponse(immediate_actions=actions)
        goals_cache.set("active", result)
        return result
    except Exception as e:
        logger.error(f"[VECTOR][api][memory] goals failed: {e}")
        return GoalsResponse(immediate_actions=[], error=str(e))


@router.get("/council/history", response_model=CouncilHistoryResponse)
async def council_history(limit: int = Query(5, ge=1, le=20)):
    """Get recent council sessions from episodic memory."""
    try:
        events = recall_episodes("", limit=limit, event_type="council_session")
        return CouncilHistoryResponse(sessions=events, count=len(events))
    except Exception as e:
        logger.error(f"[VECTOR][api][memory] council history failed: {e}")
        return CouncilHistoryResponse(sessions=[], count=0, error=str(e))


# ── Gap 19: Backup / Restore ──────────────────────────────────────────────────

@router.post("/backup")
async def backup_memory():
    """Dump the full local SQLite database to a JSON backup file."""
    try:
        from core.memory.multi_db_manager import get_manager
        path = get_manager().backup()
        return {"status": "ok", "backup_path": path}
    except Exception as e:
        logger.error(f"[VECTOR][api][memory] backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore")
async def restore_memory(backup_path: str, overwrite: bool = False):
    """Restore the local SQLite database from a JSON backup file."""
    try:
        from core.loop.autonomous_loop import AutonomousLoop

        # Match core/api/tasks.py: use the running singleton; fall back to a
        # throwaway instance only for gateway evaluation when no loop is running.
        loop = AutonomousLoop.get_instance()
        gateway = (loop or AutonomousLoop())._get_gateway()
        source = "api_memory_restore"
        gateway_result = await gateway.evaluate_external(
            "memory_restore",
            {"backup_path": backup_path, "overwrite": overwrite},
            source,
        )
        if not gateway_result.approved:
            return {
                "status": "blocked", "source": source,
                "reason": gateway_result.reason, "level": gateway_result.level,
            }
        from core.memory.multi_db_manager import get_manager
        result = get_manager().restore(backup_path, overwrite=overwrite)
        return {"status": "ok", **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[VECTOR][api][memory] restore failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ memory.py OK")
