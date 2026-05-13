# Ported from GitHub/NousResearch_hermes-agent/repo/tools/web_tools.py
"""Web search and extraction tools."""
import json
import os
from typing import Any, List, Optional

from loguru import logger
from .registry import registry


def _get_backend() -> str:
    return os.getenv("VECTOR_WEB_BACKEND", os.getenv("WEB_BACKEND", "ddg"))


async def _search_ddg(query: str, limit: int) -> list:
    """DuckDuckGo search via HTTPX (no API key needed)."""
    import httpx
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    results = []
    for item in data.get("RelatedTopics", [])[:limit]:
        if isinstance(item, dict) and "Text" in item:
            results.append({"title": item.get("Text", "")[:100], "url": item.get("FirstURL", ""), "snippet": item.get("Text", "")})
    return results


async def _search_tavily(query: str, limit: int) -> list:
    import httpx
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": limit},
        )
        r.raise_for_status()
        data = r.json()
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")} for x in data.get("results", [])]


async def _search_exa(query: str, limit: int) -> list:
    import httpx
    api_key = os.getenv("EXA_API_KEY", "")
    if not api_key:
        return []
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": api_key},
            json={"query": query, "numResults": limit},
        )
        r.raise_for_status()
        data = r.json()
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("text", "")} for x in data.get("results", [])]


def web_search(query: str, limit: int = 5, context: Any = None) -> str:
    """Search the web and return results."""
    import asyncio
    backend = _get_backend()
    try:
        if backend == "tavily":
            results = asyncio.run(_search_tavily(query, limit))
        elif backend == "exa":
            results = asyncio.run(_search_exa(query, limit))
        else:
            results = asyncio.run(_search_ddg(query, limit))
        if not results:
            return json.dumps({"results": [], "note": f"No results from {backend}"})
        return json.dumps({"results": results, "count": len(results), "backend": backend})
    except Exception as e:
        logger.warning(f"web_search failed ({backend}): {e}")
        return json.dumps({"error": str(e), "backend": backend})


async def _extract_url(url: str) -> str:
    import httpx
    # Try Firecrawl first if key available
    fc_key = os.getenv("FIRECRAWL_API_KEY", "")
    if fc_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={"Authorization": f"Bearer {fc_key}"},
                    json={"url": url, "formats": ["markdown"]},
                )
                r.raise_for_status()
                data = r.json()
                return data.get("data", {}).get("markdown", "") or data.get("markdown", "")
        except Exception:
            pass
    # Fallback: raw httpx fetch
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "VectorCode/0.1"})
        r.raise_for_status()
        text = r.text
    # Strip HTML tags roughly
    import re
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:20000]


def web_extract(urls: list, context: Any = None) -> str:
    """Extract content from one or more URLs."""
    import asyncio
    if isinstance(urls, str):
        urls = [urls]
    results = []
    for url in urls[:5]:  # cap at 5
        try:
            content = asyncio.run(_extract_url(url))
            results.append({"url": url, "content": content[:5000]})
        except Exception as e:
            results.append({"url": url, "error": str(e)})
    return json.dumps({"results": results})


registry.register(
    name="web_search",
    handler=web_search,
    schema={
        "description": "Search the web for information. Returns titles, URLs, and snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["query"],
        },
    },
    toolset="research",
    risk_level="safe",
    emoji="🌐",
)

registry.register(
    name="web_extract",
    handler=web_extract,
    schema={
        "description": "Extract content from one or more URLs.",
        "parameters": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to extract"},
            },
            "required": ["urls"],
        },
    },
    toolset="research",
    risk_level="safe",
    emoji="📄",
)
