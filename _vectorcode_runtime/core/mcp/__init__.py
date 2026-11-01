"""
VECTOR MCP Layer
MCP server (exposes VECTOR tools) + MCP client (consumes external tools).

core/mcp_server.py  — MCP SERVER: exposes VECTOR's 14+ tools to Claude Desktop etc.
core/mcp/client.py  — MCP CLIENT: lets VECTOR connect to and USE external MCP servers.
"""
from core.mcp.client import MCPClient

__all__ = ["MCPClient"]
