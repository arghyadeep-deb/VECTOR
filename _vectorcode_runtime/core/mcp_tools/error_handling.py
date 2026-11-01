"""Common JSON/error wrappers for MCP tool handlers."""

from __future__ import annotations

import json
from typing import Any, Callable

from loguru import logger


def safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def mcp_call_json(label: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """Run an MCP tool body and return a JSON response with consistent logging."""
    try:
        return safe_json(func(*args, **kwargs))
    except Exception as exc:
        logger.warning("[VECTOR][mcp] {} failed: {}", label, exc)
        return safe_json({"error": str(exc)})


def register_stub_tool(mcp, name: str, doc: str = "") -> None:
    """Register a named stub tool on mcp so it appears in list_tools().

    Used for tools whose backend module is not present in a given install — the
    tool stays discoverable and returns a clear not-implemented message.
    """
    def _fn(input: str = "") -> str:
        return f"[{name}] not yet implemented — backend module missing"
    _fn.__name__ = name
    _fn.__doc__ = doc or f"VectorCode {name} tool."
    mcp.tool(_fn)
