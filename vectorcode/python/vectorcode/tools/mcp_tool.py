# Ported from GitHub/NousResearch_hermes-agent/repo/tools/mcp_tool.py
"""MCP tool — connect to external MCP servers and invoke their tools."""
import json
import os
from typing import Any, Optional

from loguru import logger
from .registry import registry


def mcp_call(
    server: str,
    tool: str,
    arguments: Optional[dict] = None,
    context: Any = None,
) -> str:
    """Call a tool on an external MCP server.

    server: MCP server name (from config) or command to spawn
    tool: tool name to call
    arguments: tool arguments dict
    """
    try:
        from vectorcode.mcp_client.client import MCPClient
        client = MCPClient.get_or_create(server)
        result = client.call_tool(tool, arguments or {})
        return json.dumps({"result": result})
    except ImportError:
        return json.dumps({"error": "MCP client not available"})
    except Exception as e:
        logger.error(f"MCP call failed: server={server!r} tool={tool!r}: {e}")
        return json.dumps({"error": str(e)})


def mcp_list_tools(server: str, context: Any = None) -> str:
    """List tools available on an MCP server."""
    try:
        from vectorcode.mcp_client.client import MCPClient
        client = MCPClient.get_or_create(server)
        tools = client.list_tools()
        return json.dumps({"tools": tools, "server": server})
    except ImportError:
        return json.dumps({"error": "MCP client not available"})
    except Exception as e:
        return json.dumps({"error": str(e)})


registry.register(
    name="mcp_call",
    handler=mcp_call,
    schema={
        "description": "Call a tool on an external MCP server.",
        "parameters": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "MCP server name or command"},
                "tool": {"type": "string", "description": "Tool name to call"},
                "arguments": {"type": "object", "description": "Tool arguments"},
            },
            "required": ["server", "tool"],
        },
    },
    toolset="full",
    risk_level="medium",
    emoji="🔌",
)

registry.register(
    name="mcp_list_tools",
    handler=mcp_list_tools,
    schema={
        "description": "List tools available on an MCP server.",
        "parameters": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "MCP server name"},
            },
            "required": ["server"],
        },
    },
    toolset="full",
    risk_level="safe",
    emoji="📋",
)
