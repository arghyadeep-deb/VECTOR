"""VCMCP-5 regression: tool exceptions stay server-side and correlated."""
from __future__ import annotations

import re

from loguru import logger

from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_mcp.protocol import INTERNAL_ERROR, MCPRequest
from vectorcode.src.vc_mcp.server import MCPServer
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec


class _FailingCalculator(BaseTool):
    tool_id = "calculator"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name="calculator", description="test")

    def execute(self, **params) -> ToolResult:
        raise RuntimeError("path=C:/private/provider.json password=supersecretvalue")


def test_tool_exception_is_generic_to_client_and_correlated_in_redacted_log() -> None:
    messages: list[str] = []
    sink_id = logger.add(messages.append, format="{message}")
    try:
        server = MCPServer(tools=[_FailingCalculator()])

        class _RaisingExecutor:
            def execute(self, tool_call):
                raise RuntimeError(
                    "path=C:/private/provider.json password=supersecretvalue"
                )

        server._executor = _RaisingExecutor()
        response = server.handle(
            MCPRequest(
                method="tools/call",
                params={"name": "calculator", "arguments": {}},
                id=7,
            )
        )
    finally:
        logger.remove(sink_id)

    assert response is not None and response.error is not None
    assert response.error["code"] == INTERNAL_ERROR
    assert response.error["message"] == "Tool execution failed"
    serialized = response.to_json()
    assert "provider.json" not in serialized
    assert "supersecretvalue" not in serialized
    correlation_id = response.error["data"]["correlation_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", correlation_id)
    joined = "\n".join(messages)
    assert correlation_id in joined
    assert "supersecretvalue" not in joined
    assert "***REDACTED***" in joined


def test_executor_wrapped_tool_failure_is_also_generic() -> None:
    server = MCPServer(tools=[_FailingCalculator()])
    response = server.handle(
        MCPRequest(
            method="tools/call",
            params={"name": "calculator", "arguments": {}},
            id=8,
        )
    )
    assert response is not None and response.result["isError"] is True
    assert response.result["content"][0]["text"] == "Tool execution failed"
    assert re.fullmatch(r"[0-9a-f]{32}", response.result["correlation_id"])
    assert "supersecretvalue" not in response.to_json()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
