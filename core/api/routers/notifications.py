"""
VECTOR notifications router — Gap 5 A5.
HTTP endpoints for pending hypothesis surfacing + WebSocket push stub.
"""
from __future__ import annotations

__all__ = ["router"]

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/hypotheses")
async def get_pending_hypotheses(limit: int = 10) -> dict:
    """Return pending hypotheses from SuggestionQueue for dashboard display."""
    try:
        from core.brain.suggestion_queue import SuggestionQueue
        sq = SuggestionQueue()
        items = sq.get_top_pending(limit=limit)
        sq.close()
        return {"status": "ok", "count": len(items), "items": items}
    except Exception as e:
        logger.error("[VECTOR][notifications] get_pending_hypotheses failed: {}", e)
        return {"status": "error", "count": 0, "items": [], "detail": str(e)}


@router.get("/hypotheses/all")
async def get_all_hypotheses(limit: int = 50) -> dict:
    """Return all hypotheses (pending + surfaced) for history view."""
    try:
        from core.brain.suggestion_queue import SuggestionQueue
        sq = SuggestionQueue()
        items = sq.get_all(limit=limit)
        sq.close()
        return {"status": "ok", "count": len(items), "items": items}
    except Exception as e:
        logger.error("[VECTOR][notifications] get_all_hypotheses failed: {}", e)
        return {"status": "error", "count": 0, "items": [], "detail": str(e)}


@router.websocket("/ws")
async def hypothesis_websocket(ws: WebSocket) -> None:
    """WebSocket endpoint: clients receive HYPOTHESIS_SURFACED events in real time."""
    await ws.accept()
    logger.info("[VECTOR][notifications] WebSocket client connected")
    try:
        from core.event_bus.types import EventType
        # Send any currently pending hypotheses immediately on connect
        try:
            from core.brain.suggestion_queue import SuggestionQueue
            sq = SuggestionQueue()
            pending = sq.get_top_pending(limit=3)
            sq.close()
            for item in pending:
                await ws.send_json({
                    "event": EventType.HYPOTHESIS_SURFACED.value,
                    "data": item,
                })
        except Exception as _sq_err:
            logger.debug("[VECTOR][notifications] ws initial push failed: {}", _sq_err)
        # Keep connection alive; real-time push is handled by publish_event subscribers
        while True:
            try:
                msg = await ws.receive_text()
                if msg == "ping":
                    await ws.send_text("pong")
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.warning("[VECTOR][notifications] WebSocket error: {}", e)
    finally:
        logger.info("[VECTOR][notifications] WebSocket client disconnected")
