"""OpenAI-compatible API server — connects any OpenAI-compatible frontend to VectorCode.

Endpoints: /v1/chat/completions, /v1/models, /v1/responses, /v1/runs, /health
"""

import asyncio
import json
import time
import uuid
from typing import Any, Optional

from loguru import logger

try:
    from aiohttp import web
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8642


class APIServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._app = None
        self._runner = None
        self._responses: dict[str, dict] = {}
        self._runs: dict[str, dict] = {}
        self._callbacks: dict = {}

    def on_chat(self, callback):
        self._callbacks["chat"] = callback

    async def start(self):
        if not _AIOHTTP:
            logger.warning("aiohttp not installed. Run: pip install aiohttp")
            return
        self._app = web.Application()
        self._app.router.add_post("/v1/chat/completions", self._handle_chat)
        self._app.router.add_get("/v1/models", self._handle_models)
        self._app.router.add_post("/v1/responses", self._handle_responses)
        self._app.router.add_get("/v1/responses/{resp_id}", self._handle_get_response)
        self._app.router.add_post("/v1/runs", self._handle_create_run)
        self._app.router.add_get("/v1/runs/{run_id}/events", self._handle_run_events)
        self._app.router.add_get("/health", self._handle_health)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"API server on {self.host}:{self.port} (OpenAI-compatible)")

    async def _handle_chat(self, request):
        body = await request.json()
        messages = body.get("messages", [])
        model = body.get("model", "vector-focus")
        stream = body.get("stream", False)

        cb = self._callbacks.get("chat")
        content = await cb(messages, model) if cb else f"[VectorCode] Received {len(messages)} messages"

        resp = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

        if stream:
            response = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            chunk = json.dumps({"choices": [{"delta": {"content": content}}]})
            await response.write(f"data: {chunk}\n\n".encode())
            await response.write("data: [DONE]\n\n".encode())
            return response

        return web.json_response(resp)

    async def _handle_models(self, request):
        return web.json_response({
            "object": "list",
            "data": [
                {"id": "vector-focus", "object": "model", "created": int(time.time()), "owned_by": "vectorcode"},
                {"id": "vector-fast", "object": "model", "created": int(time.time()), "owned_by": "vectorcode"},
            ],
        })

    async def _handle_responses(self, request):
        body = await request.json()
        resp_id = f"resp-{uuid.uuid4().hex[:12]}"
        self._responses[resp_id] = {"input": body, "status": "completed", "created": time.time()}
        return web.json_response({"id": resp_id, "object": "response", "status": "completed"})

    async def _handle_get_response(self, request):
        resp_id = request.match_info["resp_id"]
        resp = self._responses.get(resp_id)
        if not resp: return web.json_response({"error": "not found"}, status=404)
        return web.json_response(resp)

    async def _handle_create_run(self, request):
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        self._runs[run_id] = {"status": "running", "events": [{"type": "created", "timestamp": time.time()}]}
        return web.json_response({"id": run_id, "status": "running"}, status=202)

    async def _handle_run_events(self, request):
        run_id = request.match_info["run_id"]
        run = self._runs.get(run_id)
        if not run: return web.json_response({"error": "not found"}, status=404)
        response = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        for event in run.get("events", []):
            await response.write(f"data: {json.dumps(event)}\n\n".encode())
        return response

    async def _handle_health(self, request):
        return web.json_response({"status": "ok", "service": "vectorcode-api", "version": "0.1.0"})

    async def stop(self):
        if self._runner: await self._runner.cleanup()
