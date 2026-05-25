import sys
import uuid
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from core.security.ssrf_guard import is_safe_url
from loguru import logger


class WebScout(AgentBase):
    """
    Searches the web and converts pages to markdown.
    Uses DuckDuckGo (no API key) + httpx for fetching + MarkItDown for conversion.
    Stores results in episodic_memory and Obsidian Research/ folder.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="WebScout",
            district="research",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][web_scout] ready gen={generation} hp={self.health_points}")

    # ── Search ─────────────────────────────────────────────────────────────────

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Multi-source parallel search (DuckDuckGo + Wikipedia + ArXiv).
        Falls back to single-source DuckDuckGo if parallel researcher unavailable.
        """
        try:
            from core.engine.research.parallel_researcher import ParallelResearcher
            researcher = ParallelResearcher()
            report = await researcher.research(query, mode="fast", max_per_source=max_results)
            if report.results:
                results = [
                    {"title": r.title, "url": r.url, "snippet": r.snippet}
                    for r in report.results[:max_results]
                    if r.url
                ]
                logger.info(
                    "[VECTOR][web_scout] parallel search '{}' → {} results ({} sources)",
                    query, len(results), len({r.source for r in report.results}),
                )
                return results
        except Exception as e:
            logger.debug("[VECTOR][web_scout] parallel researcher unavailable: {} — falling back", e)

        # Fallback: single-source DuckDuckGo
        try:
            import httpx
            encoded = query.replace(" ", "+")
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            headers = {"User-Agent": "Mozilla/5.0 (compatible; VECTOR/1.0)"}
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(url, headers=headers)
            results = self._parse_ddg_html(r.text, max_results)
            logger.info("[VECTOR][web_scout] search '{}' → {} results (ddg)", query, len(results))
            return results
        except Exception as e:
            logger.warning("[VECTOR][web_scout] search failed: {}", e)
            return []

    def _parse_ddg_html(self, html: str, limit: int) -> list[dict]:
        """Minimal parser for DuckDuckGo HTML results."""
        import re
        results = []
        # Extract result blocks: title, URL, snippet
        pattern = re.compile(
            r'class="result__title"[^>]*>.*?href="([^"]+)"[^>]*>(.*?)</a>.*?'
            r'class="result__snippet"[^>]*>(.*?)</span>',
            re.DOTALL,
        )
        for m in pattern.finditer(html):
            url = m.group(1).strip()
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            snippet = re.sub(r"<[^>]+>", "", m.group(3)).strip()
            if url.startswith("http"):
                results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= limit:
                break
        return results

    async def fetch_page(self, url: str, stealth: bool = False) -> str:
        """
        Fetch a URL and convert to markdown.
        Uses VECTOR Scraper (TLS fingerprint impersonation + adaptive tracking).
        Falls back to stealth mode for Cloudflare-protected sites.
        """
        if not is_safe_url(url):
            logger.warning("[VECTOR][web_scout] SSRF blocked: {}", url)
            return ""
        try:
            from core.scraper.vector_scraper import get_scraper
            scraper = get_scraper()
            result = await scraper.smart_fetch(url, try_stealth_on_fail=stealth)
            if result.markdown:
                return result.markdown[:8000]
            return result.content[:8000]
        except ImportError:
            # Fallback to httpx if scraper not available
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    r = await client.get(
                        url, headers={"User-Agent": "Mozilla/5.0 (compatible; VECTOR/1.0)"}
                    )
                return r.text[:8000]
            except Exception as e2:
                logger.warning(f"[VECTOR][web_scout] fetch_page fallback failed {url}: {e2}")
                return ""
        except Exception as e:
            logger.warning(f"[VECTOR][web_scout] fetch_page failed {url}: {e}")
            return ""

    async def fetch_page_stealth(self, url: str) -> str:
        """Fetch with full anti-bot bypass for Cloudflare / bot-protected sites."""
        try:
            from core.scraper.vector_scraper import get_scraper
            scraper = get_scraper()
            result = await scraper.fetch_stealth(url)
            return result.markdown or result.content[:8000]
        except Exception as e:
            logger.warning(f"[VECTOR][web_scout] stealth fetch failed {url}: {e}")
            return await self.fetch_page(url)

    async def research(self, query: str, save_note: bool = True) -> dict:
        """
        Full pipeline: search → fetch top result → LLM summarize → store.
        Returns dict with query, results, summary.
        """
        hydration = self._context.session_hydration_prompt()  # RULE 1
        results = await self.search(query, max_results=5)

        page_content = ""
        if results:
            page_content = await self.fetch_page(results[0]["url"])

        snippets = "\n".join(
            f"[{i+1}] {r['title']}: {r['snippet']}" for i, r in enumerate(results)
        )
        source_text = page_content[:3000] if page_content else snippets

        summary = ""
        try:
            from core.inference.vectorcode_llm import chat
            summary = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": hydration},
                    {
                        "role": "user",
                        "content": (
                            f"Research brief for: '{query}'\n\n"
                            "Summarize the key findings in 2-3 paragraphs. Be factual and concise.\n\n"
                            + source_text
                        ),
                    },
                ],
                timeout=2.0,
            )
            if not summary:
                raise RuntimeError("empty model response")
        except Exception as e:
            logger.warning(f"[VECTOR][web_scout] LLM unavailable: {e}")
            summary = snippets[:1000] if snippets else f"No results found for '{query}'"

        # Store in episodic memory
        self._memory.store(
            event_type="research",
            content=f"WebScout: {query} — {len(results)} results",
            tags=["research", "web_scout"],
            source="web_scout",
        )
        self._memory.store_chain(
            situation="web_research",
            goal_ids=["gather_knowledge"],
            steps=["search_ddg", "fetch_page", "summarize_llm"],
            action="research",
            outcome=f"{len(results)} results for '{query}'",
            reward=0.8 if results else 0.3,
        )

        # Write to Obsidian Research/
        if save_note and results:
            try:
                ts = datetime.date.today().isoformat()
                safe_title = "".join(c for c in query if c.isalnum() or c in " -_")[:60]
                note_content = f"**Query:** {query}\n\n## Summary\n\n{summary}\n\n## Sources\n\n"
                note_content += "\n".join(f"- [{r['title']}]({r['url']})" for r in results)
                self._obsidian.write_note(
                    title=f"Research — {safe_title} — {ts}",
                    content=note_content,
                    folder="Research",
                    tags=["research", "web", "auto", "vector"],
                )
            except Exception as e:
                logger.warning(f"[VECTOR][web_scout] vault write failed: {e}")

        if results:
            self.award_points(30, f"research completed: {query}")
        else:
            self.deduct_points(10, f"no results: {query}")

        return {"query": query, "results": results, "summary": summary}

    async def stealth_search(self, query: str, engine: str = "google") -> dict:
        """
        Search using anti-detection browser (bypasses Google/Cloudflare bot detection).
        Falls back to regular DuckDuckGo search if stealth server not running.
        """
        try:
            from core.stealth_browser.client import StealthBrowserClient
            async with StealthBrowserClient() as client:
                if not await client.is_healthy():
                    logger.debug("[VECTOR][web_scout] stealth server not running — using regular search")
                    results = await self.search(query)
                    return {"query": query, "engine": "duckduckgo", "results": results, "fallback": True}
                result = await client.search(query, engine=engine)
                return result
        except Exception as e:
            logger.warning("[VECTOR][web_scout] stealth_search failed: {} — falling back", e)
            results = await self.search(query)
            return {"query": query, "engine": "duckduckgo", "results": results, "fallback": True}

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        action = p.get("action", "search")
        if action == "stealth_search":
            return await self.stealth_search(p.get("query", ""), p.get("engine", "google"))
        results = await self.search(p.get("query", "VECTOR AI"))
        return {"status": "ok", "results": results}

    async def run_forever(self) -> None:
        """Runs on demand (triggered by governor). No autonomous loop needed here."""
        logger.info("[VECTOR][web_scout] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][web_scout] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bot = WebScout()
        assert bot.health_points == 500
        assert bot.name == "WebScout"

        # search test (no network required for structure check)
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            bot._obsidian._vault = vault

            result = await bot.research("Python asyncio best practices", save_note=True)
            assert isinstance(result, dict)
            assert "query" in result
            assert "results" in result
            assert "summary" in result

        print(f"✅ web_scout.py OK  HP={bot.health_points} results={len(result['results'])}")

    asyncio.run(_smoke())
