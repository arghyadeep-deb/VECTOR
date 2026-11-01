"""VectorCode HTTP Gateway — REST API for agent execution.

Endpoints:
  POST /run            — synchronous task execution
  POST /stream         — SSE streaming task execution
  GET  /status         — server + session status
  GET  /sessions       — list active sessions
  POST /sessions/{id}/cancel  — cancel a running session
  GET  /health         — health check
  POST /compact        — trigger context compaction on a session
  POST /reset          — reset a session's conversation history
  POST /model          — switch model for a session
"""

import asyncio
import hmac
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


from loguru import logger

from core.security.secrets_manager import get_secret
from vector_cli.auth import has_usable_secret

from .platforms.base import is_network_accessible

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

_VERSION = "1.0.0"
_EXECUTION_UNAVAILABLE = (
    "Agent execution is not available: the standalone gateway runner is not "
    "integrated with VECTOR's Permission Gateway."
)

# ── Request / Response dataclasses ────────────────────────────────────────────

@dataclass
class RunRequest:
    input: str
    model: str = ""
    session_id: str = ""
    project_dir: str = "."
    mode: str = "standard"   # cautious | standard | autonomous | read-only
    metadata: dict = field(default_factory=dict)


@dataclass
class RunResponse:
    session_id: str
    response: str
    tool_calls_made: int
    iterations_used: int
    model: str
    status: str   # "complete" | "error" | "cancelled"


# ── Internal session record ────────────────────────────────────────────────────

def _new_session_record(session_id: str, model: str, project_dir: str) -> dict:
    return {
        "session_id":   session_id,
        "model":        model,
        "project_dir":  project_dir,
        "messages":     [],
        "created_at":   time.time(),
        "last_active":  time.time(),
        "status":       "idle",        # idle | running | cancelled | complete | error
        "cancelled":    False,
        "result":       None,          # RunResponse once done
    }


# ── GatewayServer ─────────────────────────────────────────────────────────────

class GatewayServer:
    """VectorCode HTTP gateway — exposes agent execution over REST + SSE."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8900) -> None:
        self.host = host
        self.port = port
        self._api_key = get_secret("VECTOR_GATEWAY_KEY").strip()
        self._sessions: Dict[str, dict] = {}          # session_id → session state
        self._running: Dict[str, asyncio.Task] = {}   # session_id → asyncio.Task
        self._app: Any = None
        self._start_time: float = time.time()

    # ── App factory ───────────────────────────────────────────────────────────

    def build_app(self) -> Any:
        """Build and return the FastAPI application."""
        try:
            from fastapi import FastAPI, HTTPException
            from fastapi.middleware.cors import CORSMiddleware
            from fastapi.responses import JSONResponse
        except ImportError as exc:
            logger.error("[VECTOR][gateway] FastAPI not installed: {}", exc)
            raise RuntimeError(
                "FastAPI is required for GatewayServer. "
                "Install it with: pip install fastapi uvicorn"
            ) from exc

        try:
            from pydantic import BaseModel
        except ImportError as exc:
            logger.error("[VECTOR][gateway] pydantic not installed: {}", exc)
            raise RuntimeError("pydantic is required") from exc

        # ── Pydantic schemas (for FastAPI route validation) ────────────────────

        class RunRequestModel(BaseModel):
            input: str
            model: str = ""
            session_id: str = ""
            project_dir: str = "."
            mode: str = "standard"
            metadata: dict = {}

        class CompactRequestModel(BaseModel):
            session_id: str

        class ResetRequestModel(BaseModel):
            session_id: str

        class ModelRequestModel(BaseModel):
            session_id: str
            model: str

        # ── FastAPI app ────────────────────────────────────────────────────────

        app = FastAPI(
            title="VectorCode Gateway",
            description="REST API for VectorCode agent execution",
            version=_VERSION,
        )

        # Keep wildcard origins for existing clients, without browser credentials.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        server_ref = self  # closure reference

        @app.middleware("http")
        async def authenticate_request(request, call_next):
            if (
                request.url.path == "/health"
                or request.method == "OPTIONS"
                or not server_ref._api_key
            ):
                return await call_next(request)

            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                if hmac.compare_digest(token, server_ref._api_key):
                    return await call_next(request)

            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "message": "Invalid API key",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # ── GET /health ────────────────────────────────────────────────────────

        @app.get("/health")
        async def health():
            return {"status": "ok", "version": _VERSION}

        # ── GET /status ────────────────────────────────────────────────────────

        @app.get("/status")
        async def status():
            active = sum(
                1 for s in server_ref._sessions.values()
                if s["status"] == "running"
            )
            return {
                "status": "running",
                "active_sessions": active,
                "total_sessions": len(server_ref._sessions),
                "version": _VERSION,
                "uptime_seconds": int(time.time() - server_ref._start_time),
            }

        # ── GET /sessions ──────────────────────────────────────────────────────

        @app.get("/sessions")
        async def list_sessions():
            summaries = []
            for sid, s in server_ref._sessions.items():
                summaries.append({
                    "session_id":  sid,
                    "model":       s["model"],
                    "project_dir": s["project_dir"],
                    "status":      s["status"],
                    "created_at":  s["created_at"],
                    "last_active": s["last_active"],
                    "message_count": len(s["messages"]),
                })
            return {"sessions": summaries}

        # ── POST /sessions/{session_id}/cancel ─────────────────────────────────

        @app.post("/sessions/{session_id}/cancel")
        async def cancel_session(session_id: str):
            if session_id not in server_ref._sessions:
                raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
            sess = server_ref._sessions[session_id]
            sess["cancelled"] = True
            task = server_ref._running.get(session_id)
            if task and not task.done():
                task.cancel()
                sess["status"] = "cancelled"
                logger.info("[VECTOR][gateway] session {} cancelled", session_id)
            return {"session_id": session_id, "status": "cancelled"}

        # ── POST /run ──────────────────────────────────────────────────────────

        @app.post("/run")
        async def run(_req: RunRequestModel):
            # Fail closed. The lightweight engine's Permission Gateway field is
            # not consulted by its tool-dispatch loop, so constructing an agent
            # here would expose an ungoverned action path.
            raise HTTPException(status_code=503, detail=_EXECUTION_UNAVAILABLE)

        # ── POST /stream ───────────────────────────────────────────────────────

        @app.post("/stream")
        async def stream(_req: RunRequestModel):
            # Streaming must enforce the same boundary as /run; do not create a
            # session or start an executor while governance is unavailable.
            raise HTTPException(status_code=503, detail=_EXECUTION_UNAVAILABLE)

        # ── POST /compact ──────────────────────────────────────────────────────

        @app.post("/compact")
        async def compact(req: CompactRequestModel):
            session_id = req.session_id
            if session_id not in server_ref._sessions:
                raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

            sess = server_ref._sessions[session_id]
            messages = sess.get("messages", [])
            before_count = len(messages)

            try:
                from context.compactor import ContextCompactor
                model = sess.get("model", "vector-focus")
                compactor = ContextCompactor(model=model)
                compacted = compactor.compact(messages)
                sess["messages"] = compacted
                logger.info(
                    "[VECTOR][gateway] /compact session={} {} -> {} messages",
                    session_id, before_count, len(compacted),
                )
                return {
                    "session_id": session_id,
                    "messages_before": before_count,
                    "messages_after": len(compacted),
                    "status": "ok",
                }
            except Exception as exc:
                logger.error("[VECTOR][gateway] /compact error session={}: {}", session_id, exc)
                raise HTTPException(status_code=500, detail=str(exc))

        # ── POST /reset ────────────────────────────────────────────────────────

        @app.post("/reset")
        async def reset(req: ResetRequestModel):
            session_id = req.session_id
            if session_id not in server_ref._sessions:
                raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

            sess = server_ref._sessions[session_id]
            sess["messages"] = []
            sess["status"] = "idle"
            sess["cancelled"] = False
            sess["result"] = None
            sess["last_active"] = time.time()
            logger.info("[VECTOR][gateway] /reset session={}", session_id)
            return {"session_id": session_id, "status": "reset"}

        # ── POST /model ────────────────────────────────────────────────────────

        @app.post("/model")
        async def switch_model(req: ModelRequestModel):
            session_id = req.session_id
            if session_id not in server_ref._sessions:
                raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

            old_model = server_ref._sessions[session_id]["model"]
            server_ref._sessions[session_id]["model"] = req.model
            server_ref._sessions[session_id]["last_active"] = time.time()
            logger.info(
                "[VECTOR][gateway] /model session={} {} -> {}",
                session_id, old_model, req.model,
            )
            return {"session_id": session_id, "model": req.model, "previous_model": old_model}

        self._app = app
        logger.info("[VECTOR][gateway] FastAPI app built — {} routes", len(app.routes))
        return app

    # ── Core task runner ──────────────────────────────────────────────────────

    async def _run_task(self, session_id: str, req: RunRequest) -> RunResponse:
        """Async wrapper — delegates to synchronous _run_task_sync in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._run_task_sync, session_id, req
        )

    def _run_task_sync(self, session_id: str, req: RunRequest) -> RunResponse:
        """Synchronous task runner — calls AIAgent and returns RunResponse."""
        sess = self._sessions.get(session_id)
        model = req.model or (sess["model"] if sess else "ollama/vector-focus")

        try:
            from vectorcode.engine import AIAgent
        except ImportError:
            logger.warning("[VECTOR][gateway] AIAgent not available")
            return RunResponse(
                session_id=session_id,
                response="[AIAgent unavailable — engine not installed]",
                tool_calls_made=0, iterations_used=0, model=model, status="error",
            )

        try:
            history = (sess["messages"] if sess else []) or []
            agent = AIAgent(model=model, session_id=session_id, quiet_mode=True)
            agent._history = list(history)

            import asyncio
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(agent.run_conversation(req.input))
            finally:
                loop.close()

            response_text = result.get("text", "")
            tool_calls_total = result.get("tool_calls_total", 0)
            iterations = result.get("iterations_used", 0)

            if sess is not None:
                sess["messages"] = agent._history
                sess["last_active"] = time.time()

            return RunResponse(
                session_id=session_id,
                response=response_text,
                tool_calls_made=tool_calls_total,
                iterations_used=iterations,
                model=model,
                status=result.get("status", "ok"),
            )

        except Exception as exc:
            logger.error("[VECTOR][gateway] _run_task_sync error session={}: {}", session_id, exc)
            if sess is not None:
                sess["status"] = "error"
            return RunResponse(
                session_id=session_id,
                response=f"[Error: {exc}]",
                tool_calls_made=0,
                iterations_used=0,
                model=model,
                status="error",
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the gateway via uvicorn."""
        network_accessible = is_network_accessible(self.host)
        if network_accessible and not self._api_key:
            message = (
                f"Refusing to start gateway on {self.host}: network-accessible "
                "bindings require VECTOR_GATEWAY_KEY. Set a strong key or use "
                "127.0.0.1."
            )
            logger.error("[VECTOR][gateway] {}", message)
            raise RuntimeError(message)

        if network_accessible and not has_usable_secret(self._api_key, min_length=8):
            message = (
                "Refusing to start gateway: VECTOR_GATEWAY_KEY is too short or "
                "a placeholder. Configure a real secret of at least 8 characters "
                f"before exposing the gateway on {self.host}."
            )
            logger.error("[VECTOR][gateway] {}", message)
            raise RuntimeError(message)

        if not self._api_key:
            logger.warning(
                "[VECTOR][gateway] No VECTOR_GATEWAY_KEY configured; authentication "
                "is disabled for loopback-only binding {}",
                self.host,
            )

        if self._app is None:
            self.build_app()

        try:
            import uvicorn
        except ImportError as exc:
            raise RuntimeError(
                "uvicorn is required to start GatewayServer. "
                "Install it with: pip install uvicorn"
            ) from exc

        config = uvicorn.Config(
            app=self._app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        logger.info(
            "[VECTOR][gateway] starting on http://{}:{}", self.host, self.port
        )
        await server.serve()

    async def stop(self) -> None:
        """Graceful shutdown — cancel all running tasks."""
        logger.info("[VECTOR][gateway] stopping — cancelling {} running tasks", len(self._running))
        for session_id, task in list(self._running.items()):
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass  # intentional: we cancelled the task, swallowing is correct during shutdown
            sess = self._sessions.get(session_id)
            if sess:
                sess["status"] = "cancelled"
        self._running.clear()
        logger.info("[VECTOR][gateway] shutdown complete")


# ── Module-level singleton ────────────────────────────────────────────────────

_gateway_singleton: Optional[GatewayServer] = None


def get_gateway_server(port: int = 8900) -> GatewayServer:
    """Return the module-level singleton GatewayServer, creating it if needed."""
    global _gateway_singleton
    if _gateway_singleton is None:
        _gateway_singleton = GatewayServer(port=port)
    return _gateway_singleton


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio as _asyncio
    import json as _json

    sys.stdout.reconfigure(encoding="utf-8")

    # ── Test 1: dataclasses ────────────────────────────────────────────────────
    req = RunRequest(input="hello", model="ollama/vector-focus")
    assert req.input == "hello"
    assert req.mode == "standard"
    assert req.project_dir == "."
    assert req.metadata == {}

    resp = RunResponse(
        session_id="s1",
        response="done",
        tool_calls_made=2,
        iterations_used=3,
        model="ollama/vector-focus",
        status="complete",
    )
    assert resp.status == "complete"
    assert resp.tool_calls_made == 2
    print("RunRequest / RunResponse dataclasses OK")

    # ── Test 2: singleton ──────────────────────────────────────────────────────
    gw1 = get_gateway_server(port=8900)
    gw2 = get_gateway_server(port=8900)
    assert gw1 is gw2, "get_gateway_server must return the same singleton"
    print("get_gateway_server singleton OK")

    # ── Test 3: build_app ──────────────────────────────────────────────────────
    gw = GatewayServer(host="127.0.0.1", port=8901)
    try:
        app = gw.build_app()
        assert app is not None, "build_app() returned None"
        assert gw._app is not None
        print("build_app() OK")
    except RuntimeError as e:
        print(f"build_app() skipped (FastAPI not installed): {e}")
        sys.exit(0)

    # ── Test 4: /health route handler (direct call) ───────────────────────────
    # Find the /health route function and call it directly
    health_handler = None
    for route in app.routes:
        if hasattr(route, "path") and route.path == "/health":
            health_handler = route.endpoint
            break

    assert health_handler is not None, "/health route not registered"

    health_result = _asyncio.run(health_handler())
    assert health_result == {"status": "ok", "version": _VERSION}, (
        f"Unexpected /health response: {health_result}"
    )
    print("/health handler OK — returned", health_result)

    # ── Test 5: /status route ──────────────────────────────────────────────────
    status_handler = None
    for route in app.routes:
        if hasattr(route, "path") and route.path == "/status":
            status_handler = route.endpoint
            break

    assert status_handler is not None, "/status route not registered"
    status_result = _asyncio.run(status_handler())
    assert status_result["status"] == "running"
    assert "active_sessions" in status_result
    assert "uptime_seconds" in status_result
    print("/status handler OK — returned", status_result)

    # ── Test 6: session management helpers ────────────────────────────────────
    sid = str(uuid.uuid4())
    gw._sessions[sid] = _new_session_record(sid, "vector-focus", ".")
    assert gw._sessions[sid]["status"] == "idle"
    assert gw._sessions[sid]["messages"] == []
    assert gw._sessions[sid]["cancelled"] is False
    print("_new_session_record OK")

    # ── Test 7: /sessions list ────────────────────────────────────────────────
    sessions_handler = None
    for route in app.routes:
        if hasattr(route, "path") and route.path == "/sessions":
            sessions_handler = route.endpoint
            break

    assert sessions_handler is not None, "/sessions route not registered"
    sessions_result = _asyncio.run(sessions_handler())
    assert "sessions" in sessions_result
    assert any(s["session_id"] == sid for s in sessions_result["sessions"])
    print("/sessions handler OK — %d session(s)" % len(sessions_result["sessions"]))

    # ── Test 8: _run_task_sync fallback (no agent available) ──────────────────
    test_req = RunRequest(input="test", model="", session_id=sid)
    # This will hit the ImportError stub path or error gracefully
    result = gw._run_task_sync(sid, test_req)
    assert isinstance(result, RunResponse)
    assert result.session_id == sid
    print(f"_run_task_sync OK — status={result.status}")

    # ── Test 9: stop (no running tasks) ───────────────────────────────────────
    _asyncio.run(gw.stop())
    print("stop() OK")

    print("\ngateway/server.py OK")
