"""Knowledge search tool."""
from __future__ import annotations
from typing import Any, Dict, List

async def knowledge_search(query: str, k: int = 5, **kw: Any) -> List[Dict[str, Any]]:
    """Search the VECTOR knowledge base."""
    return []
class KnowledgeSearchTool:
    def run(self, q: str) -> list: return []

