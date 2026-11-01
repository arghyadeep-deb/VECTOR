"""
VECTOR StealthScoutAgent — District 07: research
Anti-detection browser for research on bot-protected sites.

Regular web_scout.py gets blocked on Google, LinkedIn, Cloudflare sites.
This agent uses the Camoufox Firefox fork (C++ anti-detection) to bypass them.

Governor routes: stealth_scrape, stealth_search, youtube_transcript, stealth_snapshot

Usage:
    agent = StealthScoutAgent()
    result = asyncio.run(agent.run({
        "params": {"action": "youtube_transcript",
                   "url": "https://youtu.be/dQw4w9WgXcQ"}
    }))
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from core.stealth_browser.client import StealthBrowserClient
from core.stealth_browser.transcripts import get_youtube_transcript
from core.stealth_browser.macros import macro_url, list_engines
from loguru import logger


class StealthScoutAgent(AgentBase):
    """
    VECTOR's anti-detection research agent.
    Uses Camoufox (Firefox + C++ fingerprint spoofing) to access bot-protected sites.
    Falls back gracefully to regular scraping if stealth server is not running.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="StealthScoutAgent",
            district="research",
            generation=generation,
        )
        self.capabilities = ["list_engines", "research", "scrape", "scrape_stealth", "scrape_url", "stealth_scrape", "stealth_search", "stealth_snapshot", "youtube_transcript"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        logger.info("[VECTOR][stealth_scout] ready gen={} hp={}", generation, self.health_points)

    # ── Actions ───────────────────────────────────────────────────────────────

    async def stealth_scrape(self, url: str, wait_ms: int = 1500) -> dict:
        """Scrape a URL with anti-detection. Returns snapshot + links."""
        logger.info("[VECTOR][stealth_scout] scraping {}", url[:80])
        try:
            async with StealthBrowserClient() as client:
                if not await client.is_healthy():
                    return await self._fallback_scrape(url)
                result = await client.scrape_page(url, wait_ms=wait_ms)
                self._store("stealth_scrape", url, result)
                self.award_points(20, f"stealth scrape: {url[:40]}")
                return result
        except Exception as e:
            logger.warning("[VECTOR][stealth_scout] stealth scrape failed: {} — falling back", e)
            return await self._fallback_scrape(url)

    async def stealth_search(
        self,
        query: str,
        engine: str = "google",
        wait_ms: int = 2000,
    ) -> dict:
        """Search using anti-detection browser to bypass bot blocks."""
        logger.info("[VECTOR][stealth_scout] search engine={} query={!r:.60}", engine, query)
        try:
            async with StealthBrowserClient() as client:
                if not await client.is_healthy():
                    return {"query": query, "engine": engine, "snapshot": "",
                            "error": "stealth server not running"}
                result = await client.search(query, engine=engine, wait_ms=wait_ms)
                self._store("stealth_search", query, result)
                self.award_points(20, f"stealth search: {query[:30]}")
                return result
        except Exception as e:
            logger.warning("[VECTOR][stealth_scout] stealth search failed: {}", e)
            return {"query": query, "engine": engine, "snapshot": "", "error": str(e)}

    async def youtube_transcript(self, url: str) -> dict:
        """Extract YouTube video transcript (yt-dlp → browser fallback)."""
        logger.info("[VECTOR][stealth_scout] transcript: {}", url[:80])
        result = await get_youtube_transcript(url)
        self._store("youtube_transcript", url, result)
        if result.get("transcript"):
            self.award_points(20, f"transcript: {result.get('title', url)[:40]}")
        return result

    async def stealth_snapshot(self, url: str) -> dict:
        """Get token-efficient accessibility snapshot of any page (90% smaller than HTML)."""
        logger.info("[VECTOR][stealth_scout] snapshot: {}", url[:80])
        try:
            async with StealthBrowserClient() as client:
                if not await client.is_healthy():
                    return {"url": url, "snapshot": "", "error": "stealth server not running"}
                tab = await client.create_tab(url)
                tab_id = tab.get("tabId") or tab.get("id", "")
                await asyncio.sleep(1.5)
                snap = await client.snapshot(tab_id)
                links = await client.get_links(tab_id)
                await client.close_tab(tab_id)
                result = {"url": url, "snapshot": snap, "links": links}
                self._store("stealth_snapshot", url, result)
                self.award_points(15, f"snapshot: {url[:40]}")
                return result
        except Exception as e:
            logger.warning("[VECTOR][stealth_scout] snapshot failed: {}", e)
            return {"url": url, "snapshot": "", "error": str(e)}

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _fallback_scrape(self, url: str) -> dict:
        """Fallback to regular httpx scraping when stealth server unavailable."""
        try:
            from core.scraper.vector_scraper import VectorScraper
            scraper = VectorScraper()
            result = await scraper.fetch(url)
            return {"url": url, "snapshot": result.content[:5000], "links": [], "fallback": True}
        except Exception as e:
            return {"url": url, "snapshot": "", "error": str(e)}

    def _store(self, event_type: str, context: str, result: dict) -> None:
        snap_len = len(result.get("snapshot") or result.get("transcript") or "")
        self._memory.store(
            event_type=event_type,
            content=f"StealthScoutAgent {event_type}: {context[:60]} → {snap_len} chars",
            tags=["research", "stealth", event_type],
            source="stealth_scout_agent",
        )

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        action = p.get("action", "stealth_scrape")

        if action in ("stealth_scrape", "scrape"):
            return await self.stealth_scrape(
                url=p.get("url", ""),
                wait_ms=int(p.get("wait_ms", 1500)),
            )
        elif action in ("stealth_search", "search"):
            return await self.stealth_search(
                query=p.get("query", p.get("q", "")),
                engine=p.get("engine", "google"),
                wait_ms=int(p.get("wait_ms", 2000)),
            )
        elif action in ("youtube_transcript", "transcript"):
            return await self.youtube_transcript(url=p.get("url", ""))
        elif action in ("stealth_snapshot", "snapshot"):
            return await self.stealth_snapshot(url=p.get("url", ""))
        elif action == "list_engines":
            return {"engines": list_engines()}
        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][stealth_scout] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][stealth_scout] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = StealthScoutAgent()
        assert agent.health_points == 500
        assert agent.name == "StealthScoutAgent"
        assert agent.district == "research"

        # Engine list (no server needed)
        result = await agent.run({"params": {"action": "list_engines"}})
        assert "engines" in result
        assert len(result["engines"]) >= 13

        print(f"OK stealth_scout_agent.py HP={agent.health_points}")
        print(f"  engines: {result['engines']}")

    asyncio.run(_smoke())
