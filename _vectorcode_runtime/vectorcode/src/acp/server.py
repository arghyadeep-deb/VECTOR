"""ACP server — expose VectorCode as an ACP-compatible agent."""


from loguru import logger

from dataclasses import dataclass, field
from typing import Any, Optional

# ── Module-level singleton ────────────────────────────────────────────────────
_instance: Optional["ACPServer"] = None
_EXECUTION_DISABLED_DETAIL = (
    "ACP execution is unavailable until canonical hydration, privacy and per-tool approval "
    "are integrated. Use the local VectorCode terminal."
)


@dataclass
class ACPMessage:
    role: str        # "user" | "assistant" | "system"
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ACPSession:
    session_id: str
    created_at: str
    messages: list = field(default_factory=list)   # list[ACPMessage]
    model: str = ""
    status: str = "active"   # "active" | "complete" | "error" | "terminated"


class ACPServer:
    """
    Exposes VectorCode as an ACP agent via FastAPI HTTP endpoints.

    ACP endpoints:
      POST /acp/run          - Reserved; execution currently returns 503
      POST /acp/run/stream   - Reserved; execution currently returns 503
      GET  /acp/sessions     - List sessions
      GET  /acp/sessions/{id} - Get session details
      POST /acp/sessions/{id}/resume - Reserved; execution currently returns 503
      DELETE /acp/sessions/{id} - Terminate session
      GET  /acp/health       - Health check
      GET  /acp/info         - Agent info (name, capabilities, version)
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8800) -> None:
        # Unsafe default was "0.0.0.0" -- binds all network interfaces by
        # default on a server with zero authentication on any of its 8
        # routes (/acp/run executes a real AIAgent conversation). The one
        # real caller (vectorcode/src/cli.py's `vector acp serve`) already
        # passes an explicit 127.0.0.1 default at the argparse level, but
        # this class's own default was the unsafe one -- same
        # "fix at the primitive, not just the current caller" bar used
        # repeatedly this cycle. FLAG FOR OWNER, not fixed: none of the 8
        # ACP routes have any authentication at all (unlike
        # core/mcp_server.py's SSE transport, which at least warns about
        # this); adding real auth is a cross-cutting design decision
        # (what scheme, which routes), not a narrow patch.
        self.host = host
        self.port = port
        self._sessions: dict[str, ACPSession] = {}
        self._app = None

    # ── App builder ───────────────────────────────────────────────────────────

    def build_app(self):
        """Build FastAPI app with all ACP routes. Returns the app or None."""
        try:
            from fastapi import FastAPI, HTTPException
            from pydantic import BaseModel
        except ImportError:
            logger.warning(
                "[ACP] FastAPI not installed — ACP server unavailable. "
                "Run: pip install fastapi uvicorn"
            )
            return None

        app = FastAPI(title="VectorCode ACP Server", version="1.0.0")

        class RunRequest(BaseModel):
            input: str
            model: str = ""
            session_id: str = ""
            metadata: dict = {}

        # ── Health & info ─────────────────────────────────────────────────────

        @app.get("/acp/health")
        async def health():
            return {"status": "ok", "agent": "VectorCode"}

        @app.get("/acp/info")
        async def info():
            return {
                "name": "VectorCode",
                "description": "Terminal-native agentic coding tool",
                "version": "1.0.0",
                "capabilities": ["session_metadata"],
                "execution_available": False,
                "model_support": ["ollama/*", "anthropic/*", "openai/*"],
            }

        # ── Run (blocking) ────────────────────────────────────────────────────

        @app.post("/acp/run")
        async def run(req: RunRequest):
            """Refuse execution until ACP can carry canonical approvals."""
            raise HTTPException(status_code=503, detail=_EXECUTION_DISABLED_DETAIL)

        # ── Run (streaming SSE) ───────────────────────────────────────────────

        @app.post("/acp/run/stream")
        async def run_stream(req: RunRequest):
            """Refuse before starting a stream or creating a session."""
            raise HTTPException(status_code=503, detail=_EXECUTION_DISABLED_DETAIL)

        # ── Session management ────────────────────────────────────────────────

        @app.get("/acp/sessions")
        async def list_sessions():
            return [
                {
                    "session_id": s.session_id,
                    "status": s.status,
                    "created_at": s.created_at,
                }
                for s in self._sessions.values()
            ]

        @app.get("/acp/sessions/{session_id}")
        async def get_session(session_id: str):
            s = self._sessions.get(session_id)
            if not s:
                raise HTTPException(status_code=404, detail="Session not found")
            return {
                "session_id": s.session_id,
                "status": s.status,
                "messages": [
                    {"role": m.role, "content": m.content} for m in s.messages
                ],
            }

        @app.post("/acp/sessions/{session_id}/resume")
        async def resume_session(session_id: str, req: RunRequest):
            """Resuming cannot grant authority absent from new ACP runs."""
            raise HTTPException(status_code=503, detail=_EXECUTION_DISABLED_DETAIL)

        @app.delete("/acp/sessions/{session_id}")
        async def delete_session(session_id: str):
            if session_id in self._sessions:
                self._sessions[session_id].status = "terminated"
                del self._sessions[session_id]
            return {"deleted": True}

        self._app = app
        logger.info("[ACP] FastAPI app built — 8 endpoints registered")
        return app

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _create_session(self, session_id: str = "", model: str = "") -> ACPSession:
        """Create or retrieve a session by ID."""
        import uuid
        from datetime import datetime, timezone

        if not session_id:
            session_id = str(uuid.uuid4())

        if session_id not in self._sessions:
            self._sessions[session_id] = ACPSession(
                session_id=session_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                model=model,
            )
        return self._sessions[session_id]

    async def _execute(self, session: ACPSession, user_input: str) -> str:
        """Execute a task via AIAgent. Returns response string."""
        try:
            from vectorcode.engine import AIAgent
            agent = AIAgent(model=session.model or "", session_id=session.session_id)
            agent._history = [{"role": m.role, "content": m.content} for m in session.messages]
            result = await agent.run_conversation(user_input)
            response = result.get("text", "")
            session.messages.append(ACPMessage(role="user", content=user_input))
            session.messages.append(ACPMessage(role="assistant", content=response))
            session.status = "complete"
            return response
        except Exception as exc:
            session.status = "error"
            logger.error(f"[ACP] execute error session={session.session_id}: {exc}")
            return f"Error: {exc}"

    async def _execute_stream(self, session: ACPSession, user_input: str):
        """Async generator yielding response chunks (100-char slices).

        NOTE: Real token-level streaming would require refactoring the transport
        layer inside VectorAgent.run_conversation() to yield partial responses.
        For now the full response is obtained synchronously and chunked here.
        """
        response = await self._execute(session, user_input)
        chunk_size = 100
        for i in range(0, max(len(response), 1), chunk_size):
            yield response[i : i + chunk_size]

    # ── Server start ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the ACP server via uvicorn (async entrypoint)."""
        try:
            import uvicorn
        except ImportError:
            logger.error("[ACP] uvicorn not installed — run: pip install uvicorn")
            return

        app = self.build_app()
        if app is None:
            logger.error("[ACP] Cannot start — FastAPI unavailable.")
            return

        config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        logger.info(f"[ACP] starting on {self.host}:{self.port}")
        await server.serve()


# ── Singleton accessor ────────────────────────────────────────────────────────

def get_acp_server(port: int = 8800) -> "ACPServer":
    """Return the module-level ACPServer singleton, creating it on first call."""
    global _instance
    if _instance is None:
        _instance = ACPServer(port=port)
        logger.debug(f"[ACP] singleton created port={port}")
    return _instance


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test 1 — singleton
    s1 = get_acp_server(8800)
    s2 = get_acp_server(8800)
    assert s1 is s2, "get_acp_server must return the same instance"

    # Test 2 — session creation
    sess = s1._create_session("", "ollama/vector-focus")
    assert sess.session_id, "session_id must be non-empty"
    assert sess.status == "active"

    # Test 3 — dataclasses
    msg = ACPMessage(role="user", content="hello")
    assert msg.role == "user"
    assert msg.metadata == {}

    # Test 4 — build_app (FastAPI optional)
    server = ACPServer(port=8899)
    app = server.build_app()
    if app is not None:
        assert server._app is app, "_app must be set after build_app()"
        logger.info("[ACP] FastAPI available — app built successfully")
    else:
        logger.warning("[ACP] FastAPI not installed — app=None (expected in minimal envs)")

    logger.info("✅ acp/server.py OK")
