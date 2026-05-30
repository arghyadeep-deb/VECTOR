"""
WebSearchAgent — wraps vectorcode's web_search_provider/registry for autonomous search.

Vectorcode has a pluggable web search backend (brave-free, ddgs, searxng, exa, tavily,
firecrawl). This agent exposes a clean interface that VECTOR's research/intelligence
districts can call. Falls back to DuckDuckGo if no provider is configured.
"""
from __future__ import annotations

import time


try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from loguru import logger


class WebSearchAgent:
    """
    Vectorcode's unified web search executor.
    Tries the configured backend (via agent/web_search_registry.py) first;
    falls back to direct DuckDuckGo if no backend is registered.
    """

    def __init__(self):
        self._registry = None
        logger.info("[VECTOR][vc_web_search] initialized")

    def _get_registry(self):
        if self._registry is None:
            try:
                from vectorcode.src.agent import web_search_registry as _reg
                self._registry = _reg
            except Exception as e:
                logger.debug("[VECTOR][vc_web_search] registry unavailable: {}", e)
        return self._registry

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search the web. Returns list of {title, url, description}."""
        # Try vectorcode's registered backend first
        registry = self._get_registry()
        if registry:
            try:
                provider = registry.get_active_search_provider()
                if provider:
                    result = provider.search(query)
                    if result.get("success"):
                        items = result.get("data", {}).get("web", [])
                        logger.info("[VECTOR][vc_web_search] backend={} results={}", provider.name, len(items))
                        return items[:max_results]
            except Exception as e:
                logger.debug("[VECTOR][vc_web_search] backend search failed: {}", e)

        # Fallback: DuckDuckGo via httpx
        return self._ddg_search(query, max_results)

    def _ddg_search(self, query: str, max_results: int = 5) -> list[dict]:
        """Direct DuckDuckGo search — no API key needed."""
        if httpx is None:
            return []
        try:
            resp = httpx.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
                timeout=10.0,
                headers={"User-Agent": "VECTOR/1.0"},
            )
            data = resp.json()
            results = []
            for item in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(item, dict) and "Text" in item:
                    results.append({
                        "title": item.get("Text", "")[:80],
                        "url": item.get("FirstURL", ""),
                        "description": item.get("Text", ""),
                    })
            logger.info("[VECTOR][vc_web_search] ddg fallback: {} results", len(results))
            return results
        except Exception as e:
            logger.warning("[VECTOR][vc_web_search] ddg search failed: {}", e)
            return []

    def extract(self, url: str) -> dict:
        """Extract content from a URL using vectorcode's extract backend."""
        registry = self._get_registry()
        if registry:
            try:
                provider = registry.get_active_extract_provider()
                if provider:
                    result = provider.extract([url])
                    if result.get("success"):
                        return result.get("data", [{}])[0]
            except Exception as e:
                logger.debug("[VECTOR][vc_web_search] extract backend failed: {}", e)

        # Fallback: raw httpx fetch
        if httpx:
            try:
                resp = httpx.get(url, timeout=10.0, follow_redirects=True,
                                  headers={"User-Agent": "VECTOR/1.0"})
                return {"url": url, "content": resp.text[:5000], "title": url}
            except Exception as e:
                logger.warning("[VECTOR][vc_web_search] extract fallback failed: {}", e)
        return {"url": url, "content": "", "error": "extraction failed"}


if __name__ == "__main__":
    agent = WebSearchAgent()
    results = agent.search("Python autonomous AI agents 2025", max_results=3)
    print(f"[OK] search: {len(results)} results returned")
    for r in results:
        print(f"  - {r.get('title','')[:60]}")
    print("web_search_agent.py OK")
