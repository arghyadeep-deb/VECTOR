"""WebSocket bridge: EventBus -> connected WebSocket clients."""

from __future__ import annotations

import asyncio
import os
import secrets
from typing import Any

from loguru import logger

from vectorcode.src.vc_core.events import Event, EventBus, EventType

try:
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
except ImportError:  # pragma: no cover
    pass  # FastAPI is optional; create_ws_router will fail at call time

# Agent-related event types to forward
_AGENT_EVENTS = {
    EventType.AGENT_TICK_START,
    EventType.AGENT_TICK_END,
    EventType.AGENT_TICK_ERROR,
    EventType.AGENT_BUDGET_EXCEEDED,
    EventType.AGENT_STALL_DETECTED,
    EventType.AGENT_MESSAGE_RECEIVED,
    EventType.AGENT_CHECKPOINT_SAVED,
    EventType.TOOL_CALL_START,
    EventType.TOOL_CALL_END,
    EventType.INFERENCE_START,
    EventType.INFERENCE_END,
}

def create_ws_router(event_bus: EventBus) -> Any:
    """Create a FastAPI router with a WebSocket endpoint for agent events."""
    router = APIRouter()
    # Each connected client gets a queue + loop ref for thread-safe event delivery
    clients: dict[WebSocket, tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = {}

    def _on_event(event: Event) -> None:
        """Forward event to all connected WebSocket client queues (thread-safe)."""
        payload = {
            "type": event.event_type.value,
            "timestamp": event.timestamp,
            "data": event.data or {},
        }
        for ws, (queue, loop) in list(clients.items()):
            agent_filter = getattr(ws, "_agent_filter", None)
            event_agent = (event.data or {}).get("agent_id")
            if agent_filter and event_agent != agent_filter:
                continue
            try:
                loop.call_soon_threadsafe(queue.put_nowait, payload)
            except (RuntimeError, asyncio.QueueFull) as exc:
                logger.debug("WS event delivery skipped for a client: {}", exc)

    # Subscribe to all agent events
    for event_type in _AGENT_EVENTS:
        event_bus.subscribe(event_type, _on_event)

    @router.websocket("/v1/agents/events")
    async def agent_events(websocket: WebSocket) -> None:
        # Starlette's BaseHTTPMiddleware (used by AuthMiddleware on the
        # HTTP side) only runs for scope["type"] == "http" -- it never
        # sees websocket connections, so this endpoint was completely
        # unauthenticated regardless of whether an API key is configured,
        # even though /v1/* HTTP routes are protected. Re-check the same
        # key here, supplied via a query param since browsers can't set
        # an Authorization header on a WebSocket handshake.
        configured_key = os.environ.get("OPENVECTOR_API_KEY", "")
        if configured_key:
            supplied_key = websocket.query_params.get("api_key", "")
            if not secrets.compare_digest(supplied_key, configured_key):
                await websocket.close(code=4401)
                return
        await websocket.accept()
        # Parse agent_id filter from query string
        agent_id = websocket.query_params.get("agent_id")
        websocket._agent_filter = agent_id  # type: ignore[attr-defined]
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        loop = asyncio.get_running_loop()
        clients[websocket] = (queue, loop)
        try:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            logger.debug("Agent-events WebSocket client disconnected")
        finally:
            clients.pop(websocket, None)

    return router

__all__ = ["create_ws_router"]
