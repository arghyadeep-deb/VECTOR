"""ACP (Agent Communication Protocol) client — editor integration shim.

Provides an OpenAI-compatible HTTP API that forwards requests to VectorCode's
provider router, enabling editor integration (VS Code, JetBrains, etc.) via
the ACP protocol.

NOTE: this module's ACPServer is a separate, dormant stub -- not VECTOR's
real, wired ACP server (vectorcode/src/acp/server.py's ACPServer, used by
cli.py). _get_completion() here never actually calls any provider/router;
it returns a canned echo response, contradicting this docstring's
"forwards requests to VectorCode's provider router" claim. Zero real
callers of this file today (confirmed via repo-wide grep). Flagged for the
owner alongside the jcode/vectorcode duplication question rather than
guessed at: either wire this to the real router or retire it in favor of
acp/server.py.
"""

import json
import uuid
from typing import Any, Optional

from loguru import logger

try:
    from aiohttp import web
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

class ACPServer:
    """ACP protocol server — listens on HTTP and forwards to VectorCode."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9876):
        self.host = host
        self.port = port
        self._app = None
        self._runner = None
        self._sessions: dict[str, dict] = {}

    async def start(self):
        if not _AIOHTTP:
            logger.warning("aiohttp not installed. Run: pip install aiohttp")
            return
        self._app = web.Application()
        self._app.router.add_post("/v1/chat/completions", self._handle_chat)
        self._app.router.add_get("/v1/models", self._handle_models)
        self._app.router.add_post("/acp/session/create", self._handle_session_create)
        self._app.router.add_post("/acp/session/{id}/message", self._handle_session_message)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"ACP server listening on {self.host}:{self.port}")

    async def _handle_chat(self, request):
        body = await request.json()
        messages = body.get("messages", [])
        model = body.get("model", "vector-focus")
        try:
            response = self._get_completion(messages, model)
            return web.json_response(response)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_models(self, request):
        return web.json_response({
            "object": "list",
            "data": [
                {"id": "vector-focus", "object": "model"},
                {"id": "vector-fast", "object": "model"},
            ],
        })

    async def _handle_session_create(self, request):
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {"messages": [], "created": session_id}
        return web.json_response({"session_id": session_id, "status": "created"})

    async def _handle_session_message(self, request):
        session_id = request.match_info["id"]
        body = await request.json()
        if session_id not in self._sessions:
            return web.json_response({"error": "session not found"}, status=404)
        self._sessions[session_id]["messages"].append(body.get("message", ""))
        return web.json_response({"status": "received", "session_id": session_id})

    def _get_completion(self, messages: list, model: str) -> dict:
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": f"[ACP] Received {len(messages)} messages"}, "finish_reason": "stop"}],
        }

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
