"""Compatibility shim — canonical implementation lives in vectorcode.src.vc_tools.think."""
from vectorcode.src.vc_tools.think import ThinkTool  # noqa: F401

__all__ = ["ThinkTool", "think"]


def think(thought: str) -> str:
    """Legacy convenience wrapper — delegates to ThinkTool.execute."""
    tool = ThinkTool()
    result = tool.execute(thought=thought)
    return result.content if result.success else thought
