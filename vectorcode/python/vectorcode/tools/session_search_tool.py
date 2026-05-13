# Ported from GitHub/NousResearch_hermes-agent/repo/tools/session_search_tool.py
"""FTS5 search over session history."""
import json
from typing import Any, Optional

from .registry import registry


def session_search(query: str, limit: int = 10, context: Any = None) -> str:
    """Search session history using full-text search."""
    db = getattr(context, "session_db", None) if context else None
    if db is None:
        try:
            from vectorcode.session_db import get_session_db
            db = get_session_db()
        except Exception:
            return json.dumps({"results": [], "note": "Session DB not available"})

    try:
        results = db.search_messages(query, limit=limit)
        return json.dumps({"results": results or [], "count": len(results or [])})
    except Exception as e:
        return json.dumps({"error": str(e)})


registry.register(
    name="session_search",
    handler=session_search,
    schema={
        "description": "Search conversation history using full-text search.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": ["query"],
        },
    },
    toolset="coding",
    risk_level="safe",
    emoji="🔎",
)
