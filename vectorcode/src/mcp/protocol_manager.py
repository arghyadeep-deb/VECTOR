"""MCP protocol manager — tool discovery, version negotiation, lifecycle."""

import logging
from typing import Any

from mcp.server import MCPServer
from mcp.transports import MCPTransport, StdioTransport, HTTPTransport

logger = logging.getLogger(__name__)

_MCP_SERVERS: dict[str, MCPServer] = {}


def create_server(name: str = "vectorcode") -> MCPServer:
    server = MCPServer()
    _MCP_SERVERS[name] = server
    return server


def get_server(name: str = "vectorcode") -> MCPServer:
    return _MCP_SERVERS.get(name, create_server(name))


def create_transport(server: MCPServer, transport_type: str = "stdio", **kwargs) -> MCPTransport:
    handler = _build_handler(server)
    if transport_type == "http":
        return HTTPTransport(handler, **kwargs)
    return StdioTransport(handler)


def _build_handler(server: MCPServer):
    async def handler(message: dict) -> Any:
        method = message.get("method", "")
        params = message.get("params", {})

        if method == "tools/list":
            return {"tools": server.list_tools()}
        elif method == "tools/call":
            return await server.call_tool(params.get("name", ""), params.get("arguments", {}))
        elif method == "initialize":
            return {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "vectorcode", "version": "0.1.0"}}
        elif method == "notifications/initialized":
            return {}
        return {"error": f"Unknown method: {method}"}

    return handler
