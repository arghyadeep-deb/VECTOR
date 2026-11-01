"""Compatibility shim — canonical types live in vc_tools and vc_core."""
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec, ToolExecutor, build_tool_descriptions  # noqa: F401
from vectorcode.src.vc_core.types import ToolResult  # noqa: F401

__all__ = ["BaseTool", "ToolResult", "ToolSpec", "ToolExecutor", "build_tool_descriptions"]
