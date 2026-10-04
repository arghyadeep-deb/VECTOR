"""MCP protocol manager — tool discovery, version negotiation, lifecycle."""

from typing import Any

from .server import MCPServer
from .transports import HTTPTransport, MCPTransport, StdioTransport

_MCP_SERVERS: dict[str, MCPServer] = {}


def create_server(name: str = "vectorcode") -> MCPServer:
    server = MCPServer()
    _MCP_SERVERS[name] = server
    return server


def get_server(name: str = "vectorcode") -> MCPServer:
    server = _MCP_SERVERS.get(name)
    if server is None:
        server = create_server(name)
    return server


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
