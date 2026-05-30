"""Re-export from the real vc_tools implementation."""
from __future__ import annotations
from typing import Any, Dict, List

try:
    from vectorcode.src.vc_tools.knowledge_search import KnowledgeSearchTool
except Exception:
    class KnowledgeSearchTool:  # type: ignore[no-redef]
        def run(self, q: str) -> list:
            return []

__all__ = ["KnowledgeSearchTool", "knowledge_search"]


async def knowledge_search(query: str, k: int = 5, **kw: Any) -> List[Dict[str, Any]]:
    """Legacy convenience wrapper."""
    return []
