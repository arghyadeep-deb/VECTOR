# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""MCP (Model Context Protocol) layer for VectorCode."""

from vectorcode.src.vc_mcp.client import MCPClient
from vectorcode.src.vc_mcp.protocol import MCPError, MCPNotification, MCPRequest, MCPResponse
from vectorcode.src.vc_mcp.server import MCPServer
from vectorcode.src.vc_mcp.transport import (
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
