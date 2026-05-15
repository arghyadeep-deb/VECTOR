# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/mcp/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""MCP (Model Context Protocol) layer for VectorCode."""

from vectorcode.src.oj_mcp.client import MCPClient
from vectorcode.src.oj_mcp.protocol import MCPError, MCPNotification, MCPRequest, MCPResponse
from vectorcode.src.oj_mcp.server import MCPServer
from vectorcode.src.oj_mcp.transport import (
    InProcessTransport,
    MCPTransport,
    SSETransport,
    StdioTransport,
    StreamableHTTPTransport,
)

__all__ = [
    "MCPClient",
    "MCPError",
    "MCPNotification",
    "MCPRequest",
    "MCPResponse",
    "MCPServer",
    "MCPTransport",
    "InProcessTransport",
    "SSETransport",
    "StdioTransport",
    "StreamableHTTPTransport",
]
