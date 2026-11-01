"""Compatibility shim — canonical implementation lives in vectorcode.src.vc_tools.knowledge_search."""
from vectorcode.src.vc_tools.knowledge_search import KnowledgeSearchTool  # noqa: F401

__all__ = ["KnowledgeSearchTool", "knowledge_search"]


async def knowledge_search(query: str, k: int = 5, **kw) -> list:
    """Legacy convenience wrapper — delegates to KnowledgeSearchTool."""
    tool = KnowledgeSearchTool()
    result = tool.execute(query=query, top_k=k, **kw)
    return [] if not result.success else [result]
