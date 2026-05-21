"""VECTOR Agent-to-Agent (A2A) router.

Exposes every district registered in VECTOR's agent registry as an A2A
endpoint compatible with Google's A2A protocol spec. External agents can:

  GET  /a2a/.well-known/agent.json    â€” discovery manifest
  GET  /a2a/agents                    â€” list of all available agents
  GET  /a2a/districts/{name}             â€” single agent's manifest
  POST /a2a/districts/{name}/invoke      â€” dispatch a task to an agent
  GET  /a2a/districts/{name}/tasks/{id}  â€” fetch task status
  POST /a2a/sessions                  â€” create a session (multi-turn)
  POST /a2a/sessions/{id}/messages    â€” send a message in session

Backed by vectorcode.src.a2a if absorbed, with VECTOR-native fallback that
uses the existing agent registry. Always returns 200 OK with structured
responses; never crashes the API surface.
"""
from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger


router = APIRouter(prefix="/a2a", tags=["a2a"])


# â”€â”€ In-memory task store + durable session store â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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


# â”€â”€ Request / response models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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


# â”€â”€ Discovery â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@router.get("/.well-known/agent.json")
async def well_known() -> dict:
    """A2A discovery manifest. Compatible with Google's A2A spec."""
    return {
        "schema_version": "1.0",
        "name": "VECTOR",
        "description": "Personal AI city â€” 27+ districts, local-first, energy-aware",
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
        from vectorcode.src.districts.registry import get_registry
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
        from vectorcode.src.districts.registry import get_registry
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# â”€â”€ Invocation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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


# â”€â”€ Sessions (multi-turn) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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


# â”€â”€ Internal dispatch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


async def _dispatch(agent_name: str, task: dict | str, params: dict) -> Any:
    """Try multiple paths to actually run the agent.

    Order:
      1. Direct vectorcode.src.a2a.client.invoke (if absorbed module wired)
      2. Look up agent in registry, instantiate via class_name, call .run()
      3. Return placeholder if nothing succeeds
    """
    # 1) Try absorbed A2A client
    try:
        from vectorcode.src.a2a.client import A2AClient  # type: ignore
        client = A2AClient()
        if hasattr(client, "invoke"):
            result = client.invoke(agent_name, task, params=params)
            if asyncio.iscoroutine(result):
                result = await result
            if result is not None:
                return result
    except Exception as e:
        logger.debug(f"[VECTOR][a2a] A2A client unavailable: {e}")

    # 2) Try VECTOR's own agent registry â€” instantiate + call .run()
    try:
        from vectorcode.src.districts.registry import get_registry
        reg = get_registry()
        defn = reg.get(agent_name)
        if defn is None:
            raise HTTPException(
                status_code=404, detail=f"agent '{agent_name}' not in registry",
            )
        # Try to materialize an instance
        instance = await _materialize_agent(defn)
        if instance is None:
            return {
                "status": "ack",
                "note": f"agent definition found but no instance materializable",
                "agent": agent_name,
                "task": task,
                "params": params,
            }
        # Build a task dict (some agents accept str, some dict)
        task_payload = task if isinstance(task, dict) else {"task": task, **params}
        if hasattr(instance, "run"):
            result = instance.run(task_payload)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        return {"status": "ok", "note": "agent has no run() method", "agent": agent_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[VECTOR][a2a] dispatch fallback failed: {e}")
        return {"status": "error", "error": str(e), "agent": agent_name}


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


# â”€â”€ Server-Sent Events stream for live agent activity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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
