"""VectorCode MCP client package.

Provides StdioMCPClient and MCPClientRegistry for connecting to external
MCP (Model Context Protocol) servers via JSON-RPC 2.0 over stdio.
"""

from vectorcode.mcp.client import StdioMCPClient, MCPClientRegistry, get_mcp_registry

__all__ = ["StdioMCPClient", "MCPClientRegistry", "get_mcp_registry"]
