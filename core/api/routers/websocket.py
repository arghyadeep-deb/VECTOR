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
    "require_auth",
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
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from loguru import logger
from typing import Optional

from core.config import CONFIG

router = APIRouter(prefix="/ws", tags=["websocket"])

# Authentication token (same as HTTP)
WS_API_KEY = CONFIG.get("vector_api_key", "")


def require_auth(websocket: WebSocket):
    """Validate WebSocket connection authentication."""
    if not WS_API_KEY:
        # No auth required in dev mode
        return
    
    auth = websocket.query_params.get("token", "")
    if not auth.startswith("Bearer ") or auth[7:] != WS_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized WebSocket connection")

# Global connection manager for broadcasting
class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"[VECTOR][ws] Client connected ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â {len(self._connections)} total")

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info(f"[VECTOR][ws] Client disconnected ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â {len(self._connections)} total")

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
        Client ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ Server:
            {"action": "ping"}           ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ heartbeat
            {"action": "command", "text": "..."}  ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ execute command via intelligence stack
            {"action": "subscribe", "channel": "status"}  ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ start streaming

        Server ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ Client:
            {"type": "status",  ...}     ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ full system status (every 2s)
            {"type": "events",  ...}     ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ recent memory events (every 5s)
            {"type": "agent",   ...}     ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ single agent update
            {"type": "response", ...}    ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ command response
            {"type": "error",   ...}     ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ error message
    """
    try:
        require_auth(websocket)
    except HTTPException:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await manager.connect(websocket)
    try:
        # Send initial status burst
        await manager.send_personal(websocket, await _build_status_payload())
        await manager.send_personal(websocket, await _build_recent_events())

        while True:
            # Non-blocking receive ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â timeout after 30s to allow background pushes
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
                    from core.loop.context_engine import ContextEngine
                    from core.brain.goal_system import GoalSystem
                    from core.loop.decision_engine import Candidate, DecisionEngine
                    from core.loop.permission_gateway import PermissionGateway, Action
                    from core.memory.policy import PolicyMemory

                    # RULE 1 ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Session hydration
                    ctx = ContextEngine()
                    hydration = ctx.session_hydration_prompt()

                    # Get goals
                    goals = GoalSystem()
                    actions = goals.generate_immediate_actions(limit=4)

                    # Build candidates
                    candidates = [
                        Candidate(
                            action_type=a["action"],
                            params={"goal_id": a["goal_id"], "title": a["title"]},
                            goal_ids=[a["goal_id"]],
                            urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(a.get("urgency", "low"), 0.5),
                            confidence=0.7,
                            source="ws_command",
                        )
                        for a in actions
                    ]

                    # Evaluate
                    decision = await DecisionEngine().evaluate(candidates)

                    # Execute via gateway
                    gw = PermissionGateway()
                    result = await gw.execute(
                        Action(
                            action_type=decision.winner.action_type,
                            params=decision.winner.params,
                            proposed_by="dashboard_websocket",
                            priority=msg.get("priority", "normal"),
                        )
                    )

                    # Update policy
                    pm = PolicyMemory()
                    h = PolicyMemory.make_situation_hash(decision.winner.params)
                    pm.update_from_outcome(decision.winner.action_type, h, 0.8 if result.approved else 0.2)

                    await manager.send_personal(websocket, {
                        "type": "response",
                        "action": decision.winner.action_type,
                        "approved": result.approved,
                        "level": result.level,
                        "score": decision.winner.total_score,
                        "reasoning": decision.reasoning,
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


@router.post("/command", response_model=WSCommandResponse)
async def ws_command_http(request: WSCommandRequest):
    """HTTP endpoint for command execution (alternative to WS command)."""
    from core.loop.context_engine import ContextEngine
    from core.brain.goal_system import GoalSystem
    from core.loop.decision_engine import DecisionEngine, Candidate
    from core.loop.permission_gateway import PermissionGateway
    from core.city.governor import GovernorCouncil
    from core.memory.episodic import EpisodicMemory
    import httpx

    try:
        # Route through the full intelligence pipeline via governor
        governor = GovernorCouncil()
        task = {"type": "answer_question", "params": {"query": request.text, "source": "ws_http"}}
        result = await governor.dispatch(task)
        response_text = result.get("response") or result.get("output") or str(result.get("status", "executed"))

        if result.get("status") == "error":
            return WSCommandResponse(response=result.get("error", "command failed"), success=False)

        # Store in memory
        try:
            mem = EpisodicMemory()
            mem.store(
                event_type="command_executed",
                content=request.text,
                importance="medium",
                tags=["ws_command", request.source if hasattr(request, 'source') else "http"],
                context={"response": response_text, "success": True},
                source="ws_command_http",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][ws] memory store failed: {e}")

        return WSCommandResponse(response=response_text, success=True)

    except Exception as e:
        logger.error(f"[VECTOR][ws] HTTP command failed: {e}")
        return WSCommandResponse(response=str(e), success=False, error=str(e))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("ÃƒÂ¢Ã…â€œÃ¢â‚¬Â¦ websocket.py OK")
