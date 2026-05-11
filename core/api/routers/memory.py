"""Memory router — /memory endpoints."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, Query, HTTPException
from loguru import logger

from core.api.schemas import MemoryRecentResponse, GoalsResponse, CouncilHistoryResponse
from core.api.crud import recall_episodes, get_immediate_actions, get_training_data

router = APIRouter(prefix="/memory", tags=["memory"])

@router.get("/recent", response_model=MemoryRecentResponse)
async def recent_memory(limit: int = Query(10, ge=1, le=50)):
    """Get recent episodic events from memory."""
    try:
        events = recall_episodes("", limit=limit)
        return MemoryRecentResponse(events=events, count=len(events))
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
    try:
        actions = get_immediate_actions(limit=5)
        return GoalsResponse(immediate_actions=actions)
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



if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ memory.py OK")
