"""MCP transports — stdio and HTTP transport implementations."""

import asyncio
import json
import sys
from typing import Any, Callable, Optional

from loguru import logger


class MCPTransport:
    def __init__(self, handler: Callable):
        self._handler = handler

    async def handle(self, message: dict) -> dict:
        try:
            result = await self._handler(message)
            return {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"message": str(e)}}


class StdioTransport(MCPTransport):
    async def run(self):
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, input)
            if not line: continue
            message = json.loads(line)
            response = await self.handle(message)
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


class HTTPTransport(MCPTransport):
    def __init__(self, handler: Callable, host: str = "127.0.0.1", port: int = 8765):
        super().__init__(handler)
        self.host = host
        self.port = port

    async def run(self):
        from aiohttp import web
        app = web.Application()
        app.router.add_post("/mcp", self._handle_http)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f"MCP HTTP transport on {self.host}:{self.port}")

    async def _handle_http(self, request):
        body = await request.json()
        response = await self.handle(body)
        from aiohttp import web as _web
        return _web.json_response(response)
