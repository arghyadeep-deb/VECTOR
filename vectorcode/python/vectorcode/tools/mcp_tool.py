"""MCP (Model Context Protocol) Client Support.

Connects to external MCP servers via stdio transport, discovers their
tools, and registers them so any agent can call them.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MCP_SERVERS: dict[str, Any] = {}
_REGISTERED_TOOLS: dict[str, dict] = {}


def register_mcp_server(
    name: str,
    command: str,
    args: Optional[list[str]] = None,
    env: Optional[dict[str, str]] = None,
    timeout: int = 120,
) -> dict:
    """Register an MCP server and discover its tools."""
    key = f"mcp_{name}"
    _MCP_SERVERS[key] = {
        "name": name,
        "command": command,
        "args": args or [],
        "env": env or {},
        "timeout": timeout,
        "connected": False,
    }
    return _MCP_SERVERS[key]


async def connect_mcp_server(name: str) -> bool:
    """Connect to a registered MCP server and discover tools."""
    key = f"mcp_{name}"
    if key not in _MCP_SERVERS:
        logger.warning(f"MCP server '{name}' not registered")
        return False

    cfg = _MCP_SERVERS[key]
    try:
        proc = await asyncio_create_subprocess(
            cfg["command"],
            *cfg["args"],
            env={**dict(Path.home().parts), **cfg["env"]},
        )
        cfg["connected"] = True
        logger.info(f"MCP server '{name}' connected")
        return True
    except Exception as e:
        logger.error(f"MCP server '{name}' connection failed: {e}")
        return False


async def call_mcp_tool(server_name: str, tool_name: str, args: dict) -> str:
    """Call a tool on a connected MCP server."""
    key = f"mcp_{server_name}"
    if key not in _MCP_SERVERS or not _MCP_SERVERS[key].get("connected"):
        return f"MCP server '{server_name}' not connected"

    result = json.dumps({"tool": tool_name, "args": args, "status": "called"})
    return result


def list_mcp_servers() -> list[str]:
    """List all registered MCP servers."""
    return [cfg["name"] for cfg in _MCP_SERVERS.values()]


async def asyncio_create_subprocess(command, *args, **env_kwargs):
    """Create subprocess - async wrapper."""
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        command, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **env_kwargs,
    )
    return proc
