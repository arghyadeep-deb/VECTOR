# Ported from GitHub/NousResearch_hermes-agent/repo/tools/memory_tool.py
"""Memory read/write tools with session scoping."""
import json
from typing import Any, Optional

from loguru import logger
from .registry import registry


def memory_read(query: str, limit: int = 5, context: Any = None) -> str:
    """Read memories relevant to a query."""
    mm = getattr(context, "memory_manager", None) if context else None
    if mm is None:
        try:
            from vectorcode.memory.manager import MemoryManager
            mm = MemoryManager.global_instance()
        except Exception:
            return json.dumps({"memories": [], "note": "Memory manager not available"})

    try:
        results = mm.search(query, limit=limit)
        if hasattr(results, "__await__"):
            import asyncio
            results = asyncio.get_event_loop().run_until_complete(results)
        return json.dumps({"memories": results or []})
    except Exception as e:
        return json.dumps({"error": str(e)})


def memory_write(content: str, tags: Optional[list] = None, context: Any = None) -> str:
    """Write a memory entry."""
    mm = getattr(context, "memory_manager", None) if context else None
    if mm is None:
        try:
            from vectorcode.memory.manager import MemoryManager
            mm = MemoryManager.global_instance()
        except Exception:
            return json.dumps({"error": "Memory manager not available"})

    try:
        result = mm.add(content, tags=tags or [])
        if hasattr(result, "__await__"):
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(result)
        return json.dumps({"success": True, "id": str(result) if result else "ok"})
    except Exception as e:
        return json.dumps({"error": str(e)})


registry.register(
    name="memory_read",
    handler=memory_read,
    schema={
        "description": "Search memories for relevant information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    toolset="coding",
    risk_level="safe",
    emoji="🧠",
)

registry.register(
    name="memory_write",
    handler=memory_write,
    schema={
        "description": "Save information to memory for future recall.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Content to remember"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"},
            },
            "required": ["content"],
        },
    },
    toolset="coding",
    risk_level="low",
    emoji="💾",
)
