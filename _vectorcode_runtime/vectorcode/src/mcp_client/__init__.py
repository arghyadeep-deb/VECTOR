"""VectorCode MCP client package."""
try:
    from vectorcode.mcp_client.client import MCPClient
except ImportError:
    try:
        from mcp_client.client import MCPClient
    except ImportError:
        MCPClient = None

__all__ = ["MCPClient"]
