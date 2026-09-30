"""
VECTOR notifications router - pending hypothesis HTTP endpoints and WebSocket push.
"""
from __future__ import annotations

__all__ = ["router"]


import asyncio

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
    """WebSocket endpoint: clients receive HYPOTHESIS_SURFACED events in real time.

    Starlette limitation (same as core/api/routers/websocket.py and voice_ws.py):
    the regular HTTP auth_middleware does not cover WebSocket upgrade requests,
    so every websocket endpoint must call require_auth_handshake() explicitly.
    This one didn't -- any client could connect with zero auth and receive a
    live feed of VECTOR's internal hypothesis-engine output (proactive
    insights about the owner) plus the 3 most recent pending hypotheses
    pushed immediately on connect.
    """
    await ws.accept()
    from core.api.routers.websocket import require_auth_handshake
    if not await require_auth_handshake(ws):
        return
    logger.info("[VECTOR][notifications] WebSocket client connected")
    bus = None
    subscription = None
    outbound: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)

    async def _send_event(event) -> None:
        payload = {
            "event": getattr(event.event_type, "value", str(event.event_type)),
            "data": getattr(event, "data", {}),
            "source": getattr(event, "source", ""),
            "correlation_id": getattr(event, "correlation_id", ""),
            "timestamp": getattr(event, "timestamp", 0),
        }
        try:
            outbound.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("[VECTOR][notifications] dropping websocket event; client queue full")

    async def _sender() -> None:
        while True:
            payload = await outbound.get()
            await ws.send_json(payload)

    sender_task = asyncio.create_task(_sender())
    try:
        from core.event_bus.types import EventType
        from core.event_bus.bus import get_event_bus

        bus = await get_event_bus()
        subscription = bus.subscribe(EventType.HYPOTHESIS_SURFACED, _send_event)
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
        if bus is not None and subscription is not None:
            try:
                bus.unsubscribe(subscription)
            except Exception as unsub_err:
                logger.debug("[VECTOR][notifications] unsubscribe failed: {}", unsub_err)
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass
        logger.info("[VECTOR][notifications] WebSocket client disconnected")
