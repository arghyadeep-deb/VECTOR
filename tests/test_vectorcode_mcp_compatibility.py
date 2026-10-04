"""Regression tests for the legacy VectorCode MCP compatibility package."""

import asyncio

from vectorcode.src.mcp import protocol_manager
from vectorcode.src.mcp.server import MCPServer, MCPTool


def test_protocol_manager_uses_local_mcp_implementation() -> None:
    """The compatibility manager must not import the unrelated PyPI package."""
    assert protocol_manager.MCPServer is MCPServer


def test_get_server_preserves_existing_registered_server() -> None:
    name = "regression-existing-server"
    created = protocol_manager.create_server(name)

    assert protocol_manager.get_server(name) is created
    assert protocol_manager.get_server(name) is created


def test_call_tool_awaits_async_handler() -> None:
    async def handler(value: int) -> int:
        return value + 1

    server = MCPServer()
    server.register_tool(MCPTool("increment", "Increment a value", handler))

    result = asyncio.run(server.call_tool("increment", {"value": 4}))

    assert result == {"result": 5}
