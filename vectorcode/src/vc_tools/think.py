# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Think tool — zero-cost reasoning scratchpad."""

from __future__ import annotations

from typing import Any

from vectorcode.src.vc_core.registry import ToolRegistry
from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec

@ToolRegistry.register("think")
class ThinkTool(BaseTool):
    """Reasoning scratchpad that echoes input for chain-of-thought."""

    tool_id = "think"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="think",
            description=(
                "A reasoning scratchpad. Think through"
                " a problem step by step. Input is echoed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "thought": {
                        "type": "string",
                        "description": "Your reasoning or thought process.",
                    },
                },
                "required": ["thought"],
            },
            category="reasoning",
            cost_estimate=0.0,
            latency_estimate=0.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        thought = params.get("thought", "")
        try:
            from vectorcode.src._rust_bridge import get_rust_module

            _rust = get_rust_module()
            if _rust is None:
                content = thought
            else:
                content = _rust.ThinkTool().execute(thought)
        except (ImportError, ModuleNotFoundError):
            # Pure-Python fallback when Rust extension isn't built
            content = thought
        return ToolResult(
            tool_name="think",
            content=content,
            success=True,
        )

__all__ = ["ThinkTool"]
