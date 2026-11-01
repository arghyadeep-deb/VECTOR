"""MCP research engine tools."""

from loguru import logger


def add_research_tools(mcp) -> None:
    """Register deep research tools (4 tools) using VECTOR Research Engine.

    All research uses local Ollama models (VECTOR Rule 11 — no cloud API).
    Default search: DuckDuckGo + Wikipedia + ArXiv (no API key required).
    """
    import json as _json

    try:
        from districts.research.research_api import (
            quick_research as _qr,
            generate_report as _gr,
            research_papers as _rp,
            research_news as _rn,
        )
        _research_available = True
    except ImportError as e:
        logger.warning("[VECTOR][mcp] research tools unavailable: {}", e)
        _research_available = False

    if not _research_available:
        return

    @mcp.tool
    def research_quick(query: str, save_to_brain: bool = True) -> str:
        """Quick research summary using local Ollama (1-3 min).
        Uses DuckDuckGo + Wikipedia + ArXiv. No API key required.
        Returns: summary, findings, sources."""
        try:
            result = _qr(query, save_to_brain=save_to_brain)
            return _json.dumps({
                "summary": result.get("summary", ""),
                "sources": result.get("sources", [])[:10],
                "findings_count": len(result.get("findings", [])),
                "brain_path": result.get("brain_path", ""),
            })
        except Exception as e:
            return _json.dumps({"error": str(e)})

    @mcp.tool
    def research_report(query: str, searches_per_section: int = 2) -> str:
        """Generate full structured research report (10-30 min).
        Multi-section markdown with citations. Saves to VECTOR Brain.
        Returns: content (markdown), metadata."""
        try:
            result = _gr(query, searches_per_section=searches_per_section,
                          save_to_brain=True)
            content = result.get("content", "")
            return _json.dumps({
                "content": content[:5000],  # truncate for MCP response
                "full_length": len(content),
                "metadata": result.get("metadata", {}),
                "brain_path": result.get("brain_path", ""),
            })
        except Exception as e:
            return _json.dumps({"error": str(e)})

    @mcp.tool
    def research_papers(query: str, max_results: int = 10) -> str:
        """Academic paper research via ArXiv + PubMed + Semantic Scholar.
        Returns: summary of papers, findings with citations."""
        try:
            result = _rp(query, max_results=max_results)
            return _json.dumps({
                "summary": result.get("summary", ""),
                "sources": result.get("sources", [])[:15],
                "findings_count": len(result.get("findings", [])),
            })
        except Exception as e:
            return _json.dumps({"error": str(e)})

    @mcp.tool
    def research_news(query: str, max_results: int = 10) -> str:
        """Fast news research using DuckDuckGo + Wikinews.
        No API key required. Best for current events.
        Returns: summary, sources."""
        try:
            result = _rn(query, max_results=max_results)
            return _json.dumps({
                "summary": result.get("summary", ""),
                "sources": result.get("sources", [])[:10],
            })
        except Exception as e:
            return _json.dumps({"error": str(e)})

    logger.info("[VECTOR][mcp] Research tools registered: research_quick, research_report, research_papers, research_news")
