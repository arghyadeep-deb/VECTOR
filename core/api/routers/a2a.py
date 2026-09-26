"""VECTOR Agent-to-Agent (A2A) router.

Exposes every district registered in VECTOR's agent registry as an A2A
endpoint compatible with Google's A2A protocol spec. External agents can:

  GET  /a2a/.well-known/agent.json    — discovery manifest
  GET  /a2a/agents                    — list of all available agents
  GET  /a2a/districts/{name}             — single agent's manifest
  POST /a2a/districts/{name}/invoke      — dispatch a task to an agent
  GET  /a2a/districts/{name}/tasks/{id}  — fetch task status
  POST /a2a/sessions                  — create a session (multi-turn)
  POST /a2a/sessions/{id}/messages    — send a message in session

Backed by vectorcode.src.a2a if absorbed, with VECTOR-native fallback that
uses the existing agent registry. Always returns 200 OK with structured
responses; never crashes the API surface.
"""
from __future__ import annotations

__all__ = [
    "agent_event_stream",
    "create_session",
    "get_agent",
    "get_task",
    "invoke_agent",
    "InvokeRequest",
    "InvokeResponse",
    "list_agents",
    "router",
    "session_message",
    "SessionMessageRequest",
    "SessionRequest",
    "well_known",
]


import asyncio
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger


router = APIRouter(prefix="/a2a", tags=["a2a"])


# â"€â"€ In-memory task store + durable session store â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


_TASKS: dict[str, dict] = {}
_SESSIONS_FALLBACK: dict[str, dict] = {}
_SESSION_STORE: Any | None = None


def _get_session_store() -> Any | None:
    """Lazily resolve the SessionStore from FastAPI app.state.

    Falls back to in-memory dict if the absorbed module isn't available.
    """
    global _SESSION_STORE
    if _SESSION_STORE is not None:
        return _SESSION_STORE
    try:
        from vectorcode.src.vc_sessions.session import SessionStore
        _SESSION_STORE = SessionStore()
    except Exception:
        _SESSION_STORE = object()  # sentinel: don't retry
    return _SESSION_STORE if not isinstance(_SESSION_STORE, object) else None


# â"€â"€ Request / response models â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


class InvokeRequest(BaseModel):
    """A2A invoke request body."""
    task: dict | str = ""
    params: dict = {}
    session_id: str | None = None
    stream: bool = False


class InvokeResponse(BaseModel):
    task_id: str
    agent: str
    status: str
    output: Any = None
    error: str | None = None


class SessionRequest(BaseModel):
    agent: str
    initial_message: str | None = None


class SessionMessageRequest(BaseModel):
    message: str
    role: str = "user"


# â"€â"€ Discovery â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


@router.get("/.well-known/agent.json")
async def well_known() -> dict:
    """A2A discovery manifest. Compatible with Google's A2A spec."""
    return {
        "schema_version": "1.0",
        "name": "VECTOR",
        "description": "Personal AI city — 27+ districts, local-first, energy-aware",
        "url": "/a2a",
        "version": "1.0.0",
        "owner": "Arghyadeep Deb",
        "capabilities": {
            "streaming": True,
            "multi_turn": True,
            "file_attachments": False,
            "voice": True,
        },
        "auth": {
            "type": "none_localhost",
            "note": "API keys required for non-loopback addresses",
        },
        "endpoints": {
            "agents":   "/a2a/agents",
            "invoke":   "/a2a/districts/{name}/invoke",
            "sessions": "/a2a/sessions",
        },
    }


@router.get("/agents")
async def list_agents() -> dict:
    """Return every district agent that VECTOR exposes via A2A."""
    try:
        from vectorcode.src.agents.registry import get_registry
        reg = get_registry()
        agents_list = []
        for defn in reg.list_all():
            agents_list.append({
                "name": defn.name,
                "class_name": getattr(defn, "class_name", ""),
                "district": getattr(defn, "district", ""),
                "description": getattr(defn, "description", ""),
                "model": getattr(defn, "model", ""),
                "capabilities": getattr(defn, "capabilities", []),
            })
        return {"count": len(agents_list), "agents": agents_list}
    except Exception as e:
        logger.warning(f"[VECTOR][a2a] list_agents failed: {e}")
        return {"count": 0, "agents": [], "error": str(e)}


@router.get("/districts/{name}")
async def get_agent(name: str) -> dict:
    """Single-agent manifest."""
    try:
        from vectorcode.src.agents.registry import get_registry
        reg = get_registry()
        defn = reg.get(name)
        if defn is None:
            raise HTTPException(status_code=404, detail=f"agent '{name}' not found")
        return {
            "name": defn.name,
            "class_name": getattr(defn, "class_name", ""),
            "district": getattr(defn, "district", ""),
            "description": getattr(defn, "description", ""),
            "model": getattr(defn, "model", ""),
            "capabilities": getattr(defn, "capabilities", []),
            "endpoints": {
                "invoke": f"/a2a/districts/{name}/invoke",
            },
        }
    except HTTPException:
        raise
    except Exception:
        # Registry unavailable — treat as unknown agent, not server error
        raise HTTPException(status_code=404, detail=f"agent '{name}' not found")


# â"€â"€ Invocation â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


@router.post("/districts/{name}/invoke")
async def invoke_agent(name: str, body: InvokeRequest) -> InvokeResponse:
    """Dispatch a task to a named agent and return the result."""
    task_id = secrets.token_urlsafe(12)
    _TASKS[task_id] = {
        "agent": name,
        "status": "queued",
        "started_at": time.time(),
        "params": body.params,
    }
    try:
        result = await _dispatch(name, body.task, body.params)
        _TASKS[task_id].update({
            "status": "ok",
            "finished_at": time.time(),
            "output": result,
        })
        return InvokeResponse(task_id=task_id, agent=name, status="ok", output=result)
    except HTTPException:
        raise
    except Exception as e:
        _TASKS[task_id].update({
            "status": "failed",
            "finished_at": time.time(),
            "error": str(e),
        })
        return InvokeResponse(task_id=task_id, agent=name, status="failed", error=str(e))


@router.get("/districts/{name}/tasks/{task_id}")
async def get_task(name: str, task_id: str) -> dict:
    rec = _TASKS.get(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task_id": task_id, **rec}


# â"€â"€ Sessions (multi-turn) â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


@router.post("/sessions")
async def create_session(body: SessionRequest) -> dict:
    sid = secrets.token_urlsafe(16)
    store = _get_session_store()
    if store is not None:
        try:
            store.create(sid=sid, agent=body.agent,
                         messages=[{"role": "user", "content": body.initial_message}]
                         if body.initial_message else [])
            return {"session_id": sid, "agent": body.agent}
        except Exception:
            logger.warning("[VECTOR] suppressed exception (fallback degraded)", exc_info=True)
    # Fallback: in-memory
    import uuid as _uuid
    sid = sid or str(_uuid.uuid4())
    _SESSIONS_FALLBACK[sid] = {"agent": body.agent, "messages": [], "created_at": time.time()}
    if body.initial_message:
        _SESSIONS_FALLBACK[sid]["messages"].append({
            "role": "user", "content": body.initial_message, "ts": time.time(),
        })
    return {"session_id": sid, **_SESSIONS_FALLBACK[sid]}


@router.post("/sessions/{session_id}/messages")
async def session_message(session_id: str, body: SessionMessageRequest) -> dict:
    # Try durable store first
    store = _get_session_store()
    if store is not None:
        try:
            sess = store.get(session_id)
            if sess is None:
                raise HTTPException(status_code=404, detail="session not found")
            store.append(session_id, {"role": body.role, "content": body.message,
                                       "ts": time.time()})
            if body.role == "user":
                agent_response = await _dispatch(
                    sess.get("agent", ""), body.message, {"session_id": session_id},
                )
                store.append(session_id, {"role": "assistant", "content": str(agent_response),
                                           "ts": time.time()})
                return {"reply": agent_response}
            return {"ok": True}
        except HTTPException:
            raise
        except Exception:
            logger.warning("[VECTOR] suppressed exception (fallback degraded)", exc_info=True)

    # Fallback: in-memory
    sess = _SESSIONS_FALLBACK.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    sess["messages"].append({
        "role": body.role, "content": body.message, "ts": time.time(),
    })
    if body.role == "user":
        try:
            agent_response = await _dispatch(
                sess["agent"], body.message, {"session_id": session_id},
            )
            sess["messages"].append({
                "role": "assistant", "content": str(agent_response), "ts": time.time(),
            })
            return {"reply": agent_response, "messages": sess["messages"][-2:]}
        except Exception as e:
            return {"error": str(e), "messages": sess["messages"][-1:]}
    return {"messages": sess["messages"][-1:]}


# â"€â"€ Internal dispatch â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def _resolve_action_type(task: dict | str, params: dict) -> str | None:
    """RR-3.7A (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
    RR3_7A_A2A_AUTHORIZATION_REPORT.md): deterministically extract the real
    action_type PermissionGateway must classify, or return None to fail
    closed. Never guesses via an LLM (mission Section 6).

    `task` (InvokeRequest) is free-form `dict | str`; `params` may also
    carry a type/action key (SessionMessageRequest has no task field at
    all, so this always returns None for session messages -- see Section
    19 of the report: every session message therefore fails closed to a
    non-executing response, never a silent guess).

    Checked in order, first match wins, matching the literal key
    convention Governor.dispatch()'s own task dicts use ("type") and the
    one alternate convention observed in real district agent run()
    implementations ("action"):
      task["type"], task["action"], params["type"], params["action"]
    A bare string `task` (no dict, no structured field) never resolves.
    """
    if isinstance(task, dict):
        for key in ("type", "action"):
            val = task.get(key)
            if isinstance(val, str) and val:
                return val
    for key in ("type", "action"):
        val = params.get(key)
        if isinstance(val, str) and val:
            return val
    return None


async def _dispatch(agent_name: str, task: dict | str, params: dict) -> Any:
    """Authorize and execute an A2A request through the SAME canonical
    authorization boundary /command and /ws/command use.

    RR-3.7A: this function used to instantiate the caller-named agent and
    call `instance.run(task_payload)` directly -- zero PermissionGateway,
    zero Governor, zero action-type classification of any kind. Confirmed
    by source: every currently-materializable agent behind this registry
    (vectorcode.src.agents.registry, a DISTINCT registry from the real
    district-agent core.city.agent_registry Governor/PermissionGateway
    route to) either doesn't exist as an importable class at all
    (coding.yaml's 5 definitions) or resolves to a dynamically-generated
    wrapper (agent_types.py's ~60 classes) that never overrides
    AgentBase.run() -- so today this gap is latent, not live-dangerous,
    but the architectural gap itself (no authorization boundary at all)
    was real and would become immediately exploitable the moment any real
    capability is ever registered here.

    Fixed by treating the caller-named agent as informational only (used
    for the existence check below, matching prior behavior/API contract)
    and routing the REAL execution decision through
    PermissionGateway.execute() -- the single authorization+execution
    boundary already used by /command and /ws/command. instance.run() is
    never called after authorization: PermissionGateway.execute() IS the
    execution (via its own internal dispatcher), eliminating any
    double-dispatch risk by construction rather than by careful sequencing.
    If no deterministic action_type can be extracted from the request,
    this fails closed -- no Gateway call, no execution, an honest response
    only (Section 6: never guess via an LLM).
    """
    # 0) Fast existence check — prevents a request naming an unknown agent
    # from silently proceeding; also the source of the requested agent's
    # own metadata for the audit-trail params below.
    try:
        from vectorcode.src.agents.registry import get_registry
        defn = get_registry().get(agent_name)
        if defn is None:
            raise HTTPException(
                status_code=404, detail=f"agent '{agent_name}' not in registry",
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("[VECTOR] silent swallow")
        defn = None  # Registry unavailable — fall through, action-type check below still fail-closes

    # 1) Deterministic action-identity extraction — fail closed if absent.
    action_type = _resolve_action_type(task, params)
    if action_type is None:
        return {
            "status": "blocked",
            "reason": "no_deterministic_action_identity",
            "note": (
                "could not determine a real action_type from this request "
                "(expects task={'type': '<action_type>', ...} or a 'type'/"
                "'action' key in params) -- refusing to guess or execute"
            ),
            "agent": agent_name,
        }

    # 2) Route through the real, unmodified PermissionGateway -- the same
    # authorization+execution boundary /command and /ws/command use. The
    # requested agent's identity is preserved as informational params only
    # (never determines which code executes -- Gateway's own real tier
    # resolution and _execute_action()/Governor routing does).
    try:
        from core.loop.permission_gateway import PermissionGateway, Action
        gw_params = dict(params)
        if isinstance(task, dict):
            gw_params = {**task, **gw_params}
        gw_params["_a2a_requested_agent"] = agent_name
        gateway_result = await PermissionGateway().execute(Action(
            action_type=action_type,
            params=gw_params,
            proposed_by="a2a",
        ))
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[VECTOR][a2a] gateway dispatch failed: {e}")
        return {"status": "error", "error": str(e), "agent": agent_name}

    result = dict(gateway_result.result or {})
    if not gateway_result.approved:
        return {
            "status": "blocked",
            "reason": gateway_result.reason,
            "tier": gateway_result.level,
            "agent": agent_name,
            "action_type": action_type,
        }
    if result.get("status") == "not_implemented":
        # Never report approved+executed as success when nothing real happened.
        return {
            "status": "not_implemented",
            "note": result.get("note") or f"'{action_type}' is not implemented",
            "agent": agent_name,
            "action_type": action_type,
        }
    result.setdefault("status", "ok")
    result["agent"] = agent_name
    result["action_type"] = action_type
    return result


async def _materialize_agent(defn: Any) -> Any:
    """Lazy-import the agent class and instantiate it."""
    cls_name = getattr(defn, "class_name", "")
    if not cls_name:
        return None
    # Walk through likely package roots
    import importlib
    import inspect
    import sys as _sys
    candidates = ["agents", "agents", "vectorcode.src.agents"]
    for pkg in candidates:
        try:
            importlib.import_module(pkg)
        except Exception:
            continue
        for mod_name, mod in list(_sys.modules.items()):
            if not mod_name.startswith(pkg):
                continue
            obj = getattr(mod, cls_name, None)
            if obj is not None and inspect.isclass(obj):
                try:
                    return obj()
                except Exception:
                    logger.warning("[VECTOR] suppressed exception (fallback degraded)", exc_info=True)
    return None


# â"€â"€ Server-Sent Events stream for live agent activity â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


@router.get("/events")
async def agent_event_stream():
    """Live SSE stream of agent activity. Used by the frontend's
    useAgentEvents() hook. Polls the in-memory task store for status changes.
    """
    from fastapi.responses import StreamingResponse

    async def gen():
        last_seen: set[str] = set()
        try:
            while True:
                for tid, rec in list(_TASKS.items()):
                    if tid in last_seen:
                        continue
                    if rec.get("status") in ("ok", "failed"):
                        last_seen.add(tid)
                        ev = {
                            "id": tid,
                            "ts": rec.get("finished_at", time.time()),
                            "district": "",  # could derive from agent name -> registry lookup
                            "agent": rec.get("agent", ""),
                            "kind": "completed" if rec["status"] == "ok" else "failed",
                            "payload": {
                                "duration": (rec.get("finished_at", 0) - rec.get("started_at", 0)),
                                "error": rec.get("error"),
                            },
                        }
                        import json as _json
                        yield f"data: {_json.dumps(ev)}\n\n"
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── Internal A2A: the governed bus between the real city's agents (core/city/a2a_bus.py) ───────────────────────────────
# Everything above serves EXTERNAL agents over the A2A HTTP spec from a separate wrapper registry. These read/drive the bus the
# 230 real district agents use with each other. Same bearer-token gate as the rest of /a2a.

class InternalAskRequest(BaseModel):
    task_type: str
    params: dict = {}
    to: str | None = None            # agent name/id, or "district:<name>"
    capability: str | None = None
    sender: str = "owner_api"        # an existing live agent's name may be given to act as that agent; otherwise a plain label
    timeout: float | None = None


@router.get("/internal/directory")
async def internal_directory():
    """district -> agents (id, name, capabilities, HP, status): who can be asked."""
    from core.city.a2a_bus import get_bus
    directory = get_bus().directory()
    return {"districts": directory, "district_count": len(directory), "agent_count": sum(len(v) for v in directory.values())}


@router.get("/internal/ping-all")
async def internal_ping_all():
    """Conformance: ping every live agent over the bus; who answered, per district, and which districts declare no capabilities."""
    from core.city.a2a_bus import get_bus
    return await get_bus().ping_all()


@router.get("/internal/work-board")
async def internal_work_board():
    """Practice-drill coverage: which agents have a verifiable drill, which districts have none, and whether the gym is on."""
    from core.city.work_board import get_board
    return get_board().coverage()


@router.get("/internal/agent/{name}")
async def internal_agent(name: str):
    """One agent's experience: lineage XP/level/deaths, per-task skills and its current playbook."""
    from core.city import experience
    from core.city.a2a_bus import get_bus
    agent = get_bus().resolve(name)
    if agent is None:
        return {"found": False, "name": name}
    return {"found": True, "stats": experience.lineage_stats(agent), "skills": experience.skill_table(agent),
            "playbook": experience.playbook(agent, k=8)}


@router.get("/internal/recent")
async def internal_recent(limit: int = 50):
    """The most recent agent-to-agent messages (newest first), including refusals, with the bus counters."""
    from core.city.a2a_bus import get_bus
    bus = get_bus()
    return {"messages": bus.recent(max(1, min(int(limit), 200))), "stats": dict(bus.stats)}


@router.get("/internal/conversation/{correlation_id}")
async def internal_conversation(correlation_id: str):
    from core.city.a2a_bus import get_bus
    return {"correlation_id": correlation_id, "messages": get_bus().conversation(correlation_id)}


@router.post("/internal/ask")
async def internal_ask(body: InternalAskRequest):
    """Owner-initiated request into the bus. Information/analysis task types only: YELLOW/RED come back `requires_approval`
    (use /command for those). The reply says who answered, in what state, and why anything was refused."""
    from core.city.a2a_bus import get_bus
    bus = get_bus()
    sender = bus.resolve(body.sender) or body.sender
    reply = await bus.ask(sender, body.task_type, body.params, to=body.to, capability=body.capability,
                          timeout=body.timeout, origin="owner_api")
    return reply.to_dict()
