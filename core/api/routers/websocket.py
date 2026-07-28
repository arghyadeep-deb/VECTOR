"""WebSocket router for real-time V.E.C.T.O.R. dashboard streaming.

Authentication: WebSocket connections require Bearer token in query param
or must be authenticated via HTTP first (session-based).
Frontend receives pure data streams only.
"""

import sys

__all__ = [
    "broadcast_event",
    "ConnectionManager",
    "manager",
    "require_auth_handshake",
    "router",
    "vector_ws",
    "vector_ws_state",
    "WS_API_KEY",
    "ws_command_http",
    "WSCommandRequest",
    "WSCommandResponse",
]

import asyncio
import datetime
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from loguru import logger
from typing import Optional

from core.config import CONFIG

router = APIRouter(prefix="/ws", tags=["websocket"])

# Authentication token (same as HTTP)
WS_API_KEY = CONFIG.get("vector_api_key", "")


async def require_auth_handshake(websocket: WebSocket) -> bool:
    """Validate WebSocket connection via first-message auth handshake.

    Returns True if auth passed (or not required). Returns False and closes the
    socket if auth is required but the handshake fails or times out.
    Token must NOT be in the URL query string (leaks to server logs / proxies).
    """
    if not WS_API_KEY:
        # No auth required in dev mode
        return True
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        token = auth_msg.get("auth", "").replace("Bearer ", "").strip()
    except (asyncio.TimeoutError, Exception):
        await websocket.close(code=1008, reason="Auth handshake timeout")
        return False
    if token != WS_API_KEY:
        await websocket.close(code=1008, reason="Unauthorized")
        return False
    return True

# Global connection manager for broadcasting
class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"[VECTOR][ws] Client connected — {len(self._connections)} total")

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info(f"[VECTOR][ws] Client disconnected — {len(self._connections)} total")

    async def broadcast(self, message: dict):
        """Send a message to all connected clients."""
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_personal(self, ws: WebSocket, message: dict):
        try:
            await ws.send_json(message)
        except Exception:
            self.disconnect(ws)


manager = ConnectionManager()


async def broadcast_event(message: dict) -> None:
    """Module-level helper used by core.loop.permission_gateway and other
    backend producers to broadcast UI events (orb_state, ui_event, etc.) to
    every connected dashboard. Never raises (RULE 2)."""
    try:
        await manager.broadcast(message)
    except Exception as _bc_err:
        logger.warning(f"[VECTOR][ws] broadcast_event failed: {_bc_err}")


async def _build_status_payload() -> dict:
    """Gather current VECTOR state for dashboard."""
    payload: dict = {
        "type": "status",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "loop_running": False,
        "uptime_seconds": 0,
        "models": {},
        "memory": {},
        "agents": {"count": 0, "districts": []},
        "vector_version": CONFIG.get("version", "1.0.0"),
    }
    try:
        from core.city.agent_registry import get_registry
        reg = get_registry()
        agents = reg.list_all()
        payload["agents"] = {
            "count": len(agents),
            "districts": sorted({a.get("district", "") for a in agents}),
            "alive": len([a for a in agents if a.get("is_alive")]),
            "elite": len([a for a in agents if a.get("health_points", 0) >= 800]),
            "list": agents[:20],  # cap at 20 for WS payload size
        }
    except Exception as e:
        logger.warning(f"[VECTOR][ws] agent stats failed: {e}")

    try:
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        payload["memory"] = mem.get_stats()
    except Exception as e:
        logger.warning(f"[VECTOR][ws] memory stats failed: {e}")

    try:
        import httpx
        ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{ollama_host}/api/tags")
            if r.status_code == 200:
                models = r.json().get("models", [])
                payload["models"] = {m["name"]: "loaded" for m in models}
    except Exception:
        payload["models"] = {"ollama": "unavailable"}

    return payload


async def _build_recent_events(limit: int = 5) -> dict:
    """Fetch recent episodic events."""
    try:
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        events = mem.recall("", limit=limit)
        return {
            "type": "events",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "events": events,
        }
    except Exception as e:
        return {
            "type": "events",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "events": [],
            "error": str(e),
        }


@router.websocket("")
async def vector_ws(websocket: WebSocket):
    """Main WebSocket endpoint for dashboard real-time stream.

    Authentication: requires ?token=Bearer <API_KEY> query param when
    vector_api_key is configured. Unauthenticated connections are rejected
    immediately before any data is sent.

    Message protocol:
        Client → Server:
            {"action": "ping"}           → heartbeat
            {"action": "command", "text": "..."}  → execute command via intelligence stack
            {"action": "subscribe", "channel": "status"}  → start streaming

        Server → Client:
            {"type": "status",  ...}     → full system status (every 2s)
            {"type": "events",  ...}     → recent memory events (every 5s)
            {"type": "agent",   ...}     → single agent update
            {"type": "response", ...}    → command response
            {"type": "error",   ...}     → error message
    """
    await manager.connect(websocket)
    if not await require_auth_handshake(websocket):
        manager.disconnect(websocket)
        return
    try:
        # Send initial status burst
        await manager.send_personal(websocket, await _build_status_payload())
        await manager.send_personal(websocket, await _build_recent_events())

        while True:
            # Non-blocking receive — timeout after 30s to allow background pushes
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a keep-alive ping
                await manager.send_personal(websocket, {"type": "ping", "time": datetime.datetime.now(datetime.timezone.utc).isoformat()})
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_personal(websocket, {"type": "error", "detail": "Invalid JSON"})
                continue

            action = msg.get("action", "")

            if action == "ping":
                await manager.send_personal(websocket, {"type": "pong", "time": datetime.datetime.now(datetime.timezone.utc).isoformat()})

            elif action == "status":
                await manager.send_personal(websocket, await _build_status_payload())

            elif action == "events":
                await manager.send_personal(websocket, await _build_recent_events(msg.get("limit", 5)))

            elif action == "command":
                # Execute through the full intelligence stack like /command endpoint
                text = msg.get("text", "")
                if not text:
                    await manager.send_personal(websocket, {"type": "error", "detail": "Missing 'text' field"})
                    continue

                try:
                    # 2026-07-21 KNOWN_ISSUES #12: this used to completely
                    # ignore `text` -- it built candidates from GoalSystem's
                    # autonomous goal queue and executed whichever goal won,
                    # regardless of what was actually typed, despite the
                    # comment above claiming parity with /command. Confirmed
                    # nothing in the current frontend actually sends this WS
                    # action (frontend/js/vector-core.js's V.command(), used
                    # by every real chat/terminal path, POSTs to the HTTP
                    # /command endpoint instead) -- so this was unreachable
                    # from the live UI, but a real bug for any direct WS
                    # caller. Now reuses the same real pipeline as HTTP
                    # /command (commands.py::command_endpoint(), which
                    # itself now routes through classify_chat_intent() +
                    # Governor.dispatch() per issue #1) instead of
                    # duplicating a second, broken implementation.
                    from core.api.routers.commands import command_endpoint
                    from core.api.schemas import CommandRequest
                    from core.api.dependencies import (
                        get_context_engine, get_decision_engine,
                        get_permission_gateway, get_episodic_memory,
                    )
                    cmd_result = await command_endpoint(
                        body=CommandRequest(
                            text=text, source="ws_command",
                            priority=msg.get("priority", "normal"),
                        ),
                        ctx_engine=get_context_engine(websocket),
                        decision_engine=get_decision_engine(websocket),
                        perm_gateway=get_permission_gateway(websocket),
                        episodic_mem=get_episodic_memory(websocket),
                    )

                    await manager.send_personal(websocket, {
                        "type": "response",
                        "response": cmd_result.response,
                        "action": cmd_result.action_taken,
                        "score": cmd_result.winner_score,
                        "candidates_evaluated": cmd_result.candidates_evaluated,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    })

                except Exception as e:
                    logger.error(f"[VECTOR][ws] command execution failed: {e}")
                    await manager.send_personal(websocket, {"type": "error", "detail": str(e)})

            elif action == "subscribe":
                channel = msg.get("channel", "")
                if channel == "status":
                    # Start background broadcaster for this client
                    asyncio.create_task(_status_broadcaster(websocket))
                await manager.send_personal(websocket, {"type": "subscribed", "channel": channel})

            else:
                await manager.send_personal(websocket, {"type": "error", "detail": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        # A client dropping mid-handshake/stream surfaces as a Starlette state
        # error ("not connected"/"need to call accept first"/disconnect). That's
        # a benign race, not a fault — log it quietly and just clean up.
        _m = str(e).lower()
        if any(s in _m for s in ("not connected", "accept", "disconnect", "close message")):
            logger.debug(f"[VECTOR][ws] client dropped: {e}")
        else:
            logger.error(f"[VECTOR][ws] connection error: {e}")
        manager.disconnect(websocket)


@router.websocket("/state")
async def vector_ws_state(websocket: WebSocket):
    """D1 — event_bus bridge: forward autonomous_loop events to dashboard in real time.

    Subscribes to DECISION_MADE, AGENT_HP_CHANGED, TASK_ROUTED,
    HYPOTHESIS_SURFACED, and ANOMALY_DETECTED; broadcasts each as a
    state_event JSON frame to the connected client.  Never raises (RULE 2).
    """
    await manager.connect(websocket)
    bus = None
    subs = []
    try:
        from core.event_bus.bus import get_event_bus
        from core.event_bus.types import Event, EventType as ET

        STATE_EVENTS = {
            ET.DECISION_MADE,
            ET.AGENT_HP_CHANGED,
            ET.TASK_ROUTED,
            ET.HYPOTHESIS_SURFACED,
            ET.ANOMALY_DETECTED,
        }

        bus = await get_event_bus()

        async def _forward(event: Event) -> None:
            try:
                await manager.send_personal(websocket, {
                    "type": "state_event",
                    "event_type": event.event_type.value,
                    "data": event.data,
                    "source": event.source,
                    "ts": event.timestamp,
                })
            except Exception:
                logger.warning("[VECTOR] silent swallow")
                pass

        subs = [bus.subscribe(et, _forward) for et in STATE_EVENTS]

        # Send initial ping so client knows it's connected
        await manager.send_personal(websocket, {"type": "state_ready"})

        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                await manager.send_personal(websocket, {"type": "ping"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("[VECTOR][ws/state] connection error: {}", e)
    finally:
        if bus is not None:
            for sub in subs:
                try:
                    bus.unsubscribe(sub)
                except Exception:
                    logger.warning("[VECTOR] silent swallow")
                    pass
        manager.disconnect(websocket)


async def _status_broadcaster(ws: WebSocket):
    """Background task that pushes status updates every 2 seconds."""
    try:
        while ws in manager._connections:
            payload = await _build_status_payload()
            await manager.send_personal(ws, payload)
            await asyncio.sleep(2.0)
    except Exception:
        logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)


class WSCommandRequest(BaseModel):
    text: str
    priority: str = "normal"
    source: str = "http"


class WSCommandResponse(BaseModel):
    response: str
    success: bool = True
    error: Optional[str] = None
    district: Optional[str] = None
    task_type: Optional[str] = None


@router.post("/command", response_model=WSCommandResponse)
async def ws_command_http(request: WSCommandRequest):
    """HTTP endpoint for command execution (alternative to WS command)."""
    from core.loop.context_engine import ContextEngine
    from core.brain.goal_system import GoalSystem
    from core.loop.decision_engine import DecisionEngine, Candidate
    from core.loop.permission_gateway import PermissionGateway
    from core.city.governor import GovernorCouncil, classify_chat_intent
    from core.memory.episodic import EpisodicMemory
    import httpx

    try:
        # Route through the full intelligence pipeline via governor
        governor = GovernorCouncil()
        # 2026-07-21 KNOWN_ISSUES #1: this used to hardcode every request to
        # task_type="answer_question", which Governor.dispatch() special-cases
        # to skip district routing entirely — meaning nothing typed in chat
        # could ever reach a real district agent. classify_chat_intent()
        # decides per-message whether this is plain Q&A or a real action;
        # it defaults to answer_question on any doubt, so this is additive,
        # not a regression of the stub-answer fix that method exists for.
        intent = await classify_chat_intent(request.text)
        task = {
            "type": intent["type"],
            "params": {"query": request.text, "content": request.text, "source": "ws_http"},
        }
        if intent.get("district"):
            task["district"] = intent["district"]
        result = await governor.dispatch(task)
        response_text = result.get("response") or result.get("output") or str(result.get("status", "executed"))
        result_district = result.get("district")
        result_task_type = intent.get("type")

        if result.get("status") == "error":
            return WSCommandResponse(
                response=result.get("error", "command failed"), success=False,
                district=result_district, task_type=result_task_type,
            )

        # Store in memory
        try:
            # 2026-07-21: this passed importance="medium", which
            # EpisodicMemory.store() has never accepted (signature is
            # event_type, content, tags, context, source — no importance
            # kwarg). Every call raised TypeError, silently swallowed by
            # this except block, so nothing sent through /ws/command has
            # ever actually been persisted — confirmed by a write-then-read
            # memory test that came back completely empty.
            mem = EpisodicMemory()
            mem.store(
                event_type="command_executed",
                content=request.text,
                tags=["ws_command", request.source if hasattr(request, 'source') else "http"],
                context={"response": response_text, "success": True},
                source="ws_command_http",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][ws] memory store failed: {e}")

        return WSCommandResponse(
            response=response_text, success=True,
            district=result_district, task_type=result_task_type,
        )

    except Exception as e:
        logger.error(f"[VECTOR][ws] HTTP command failed: {e}")
        return WSCommandResponse(response=str(e), success=False, error=str(e))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ websocket.py OK")