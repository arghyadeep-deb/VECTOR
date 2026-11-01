"""
VECTOR Smart Routing — Partner API Registry
Python port of ClawRouter/src/partners/

Registry of partner service APIs accessible through the routing layer.
Includes web search (Exa), document retrieval, and specialized tools.

Usage:
    registry = PartnerRegistry()
    exa = registry.get("exa")
    results = await exa.search("AI agent frameworks 2026")
"""
from __future__ import annotations

__all__ = [
    "ExaClient",
    "get_registry",
    "JinaClient",
    "PartnerClient",
    "PartnerConfig",
    "PartnerRegistry",
]


import asyncio
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.config import CONFIG
from loguru import logger


@dataclass
class PartnerConfig:
    id: str
    name: str
    description: str
    base_url: str
    api_key_env: str           # environment variable name for API key
    endpoints: dict[str, str] = field(default_factory=dict)


PARTNER_REGISTRY: dict[str, PartnerConfig] = {
    "exa": PartnerConfig(
        id="exa",
        name="Exa Search",
        description="Neural web search — returns full page content, not just snippets",
        base_url="https://api.exa.ai",
        api_key_env="EXA_API_KEY",
        endpoints={
            "search": "/search",
            "find_similar": "/findSimilar",
            "get_contents": "/contents",
        },
    ),
    "jina": PartnerConfig(
        id="jina",
        name="Jina Reader",
        description="Convert any URL to clean markdown for LLM consumption",
        base_url="https://r.jina.ai",
        api_key_env="JINA_API_KEY",
        endpoints={
            "read": "/",  # GET r.jina.ai/{url}
        },
    ),
    "serper": PartnerConfig(
        id="serper",
        name="Serper Google Search",
        description="Real-time Google Search results via Serper API",
        base_url="https://google.serper.dev",
        api_key_env="SERPER_API_KEY",
        endpoints={
            "search":  "/search",
            "images":  "/images",
            "news":    "/news",
            "scholar": "/scholar",
        },
    ),
    "firecrawl": PartnerConfig(
        id="firecrawl",
        name="Firecrawl",
        description="Web scraping with JS rendering and structured extraction",
        base_url="https://api.firecrawl.dev/v0",
        api_key_env="FIRECRAWL_API_KEY",
        endpoints={
            "scrape":   "/scrape",
            "crawl":    "/crawl",
            "map":      "/map",
            "extract":  "/extract",
        },
    ),
}


class PartnerClient:
    """Generic HTTP client for partner APIs."""

    def __init__(self, config: PartnerConfig) -> None:
        self._cfg = config
        import os
        self._api_key = (
            os.environ.get(config.api_key_env, "")
            or CONFIG.get("api_keys", {}).get(config.api_key_env.lower(), "")
        )

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def call(self, endpoint: str, payload: dict | None = None, method: str = "POST") -> dict:
        """Make an authenticated API call to this partner."""
        import httpx
        ep = self._cfg.endpoints.get(endpoint, endpoint)
        url = self._cfg.base_url.rstrip("/") + "/" + ep.lstrip("/")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        async with httpx.AsyncClient(timeout=30.0) as c:
            if method == "GET":
                r = await c.get(url, headers=headers, params=payload)
            else:
                r = await c.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()


class ExaClient(PartnerClient):
    """Exa neural web search client."""

    async def search(
        self,
        query: str,
        num_results: int = 5,
        use_autoprompt: bool = True,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[dict]:
        if not self.is_configured():
            logger.debug("[VECTOR][partners] EXA_API_KEY not set")
            return []
        try:
            payload: dict = {
                "query": query,
                "numResults": num_results,
                "useAutoprompt": use_autoprompt,
                "contents": {"text": True},
            }
            if include_domains:
                payload["includeDomains"] = include_domains
            if exclude_domains:
                payload["excludeDomains"] = exclude_domains
            result = await self.call("search", payload)
            return result.get("results", [])
        except Exception as e:
            logger.warning("[VECTOR][partners] Exa search failed: {}", e)
            return []


class JinaClient(PartnerClient):
    """Jina Reader — convert any URL to clean markdown."""

    async def read(self, url: str) -> str:
        try:
            import httpx
            full_url = f"{self._cfg.base_url}/{url}"
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.get(full_url, headers=headers)
                return r.text
        except Exception as e:
            logger.warning("[VECTOR][partners] Jina read failed: {}", e)
            return ""


class PartnerRegistry:
    """Registry of all partner API clients."""

    def __init__(self) -> None:
        self._clients: dict[str, PartnerClient] = {}
        self._build_clients()

    def _build_clients(self) -> None:
        for pid, cfg in PARTNER_REGISTRY.items():
            if pid == "exa":
                self._clients[pid] = ExaClient(cfg)
            elif pid == "jina":
                self._clients[pid] = JinaClient(cfg)
            else:
                self._clients[pid] = PartnerClient(cfg)

    def get(self, partner_id: str) -> PartnerClient | None:
        return self._clients.get(partner_id)

    def configured_partners(self) -> list[str]:
        return [pid for pid, c in self._clients.items() if c.is_configured()]

    def list_all(self) -> list[dict]:
        return [
            {
                "id":           cfg.id,
                "name":         cfg.name,
                "description":  cfg.description,
                "configured":   self._clients[cfg.id].is_configured(),
            }
            for cfg in PARTNER_REGISTRY.values()
        ]


# Module-level singleton
_registry: PartnerRegistry | None = None


def get_registry() -> PartnerRegistry:
    global _registry
    if _registry is None:
        _registry = PartnerRegistry()
    return _registry


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    registry = PartnerRegistry()
    all_partners = registry.list_all()
    configured = registry.configured_partners()

    print(f"OK partners.py — {len(all_partners)} partner APIs registered")
    for p in all_partners:
        status = "configured" if p["configured"] else "needs API key"
        print(f"  {p['id']:12} {p['name']} — {status}")
    print(f"  Configured: {configured or 'none (set EXA_API_KEY, JINA_API_KEY, etc.)'}")
