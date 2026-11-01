import sys
import uuid
import asyncio
import datetime
import os
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from core.security.ssrf_guard import is_safe_url
from loguru import logger
from core.security.secrets_manager import get_secret


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
        self.capabilities = ["research", "search", "search_web", "stealth_search", "web_extract"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][web_scout] ready gen={generation} hp={self.health_points}")

    def _offline_summary(self, query: str, source_text: str, snippets: str) -> str:
        """Return a deterministic brief for offline tests and local no-key runs."""
        text = (source_text or snippets).strip()
        if not text:
            return f"No results found for '{query}'"
        return f"Research brief for '{query}': {text[:1000]}"

    # ── Search ─────────────────────────────────────────────────────────────────

    async def _search_firecrawl(self, query: str, max_results: int = 5) -> list[dict]:
        """Use Firecrawl for structured web search when API key available."""
        try:
            api_key = get_secret("FIRECRAWL_API_KEY")
            if not api_key:
                return []
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=api_key)
            result = app.search(query, limit=max_results)
            return [
                {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("markdown", "")}
                for r in (result.get("data") or [])
            ]
        except Exception as e:
            logger.warning("[VECTOR][web_scout] Firecrawl failed: {}", e)
            return []

    async def _scrape_with_playwright(self, url: str) -> str:
        """Use playwright-mcp for JS-heavy pages that DDG can't parse."""
        try:
            from core.browser.playwright_mcp_client import PlaywrightMCPClient
            client = PlaywrightMCPClient()
            if not await client.is_available():
                return ""
            return await client.scrape_page(url)
        except Exception as e:
            logger.warning("[VECTOR][web_scout] playwright scrape failed: {}", e)
            return ""

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Multi-source parallel search: Firecrawl (primary) → ParallelResearcher → DuckDuckGo.
        Firecrawl provides structured full-page extraction when FIRECRAWL_API_KEY is set.
        Falls back through parallel researcher and then single-source DuckDuckGo.
        """
        # Try Firecrawl first (structured, full-page extraction)
        results = await self._search_firecrawl(query, max_results)
        if results:
            logger.info("[VECTOR][web_scout] search '{}' → {} results (firecrawl)", query, len(results))
            return results

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
            # Enrich top 2 DDG results with Playwright for JS-heavy pages that DDG can't parse
            for res in results[:2]:
                if not res.get("content") or len(res.get("content", "")) < 100:
                    full = await self._scrape_with_playwright(res.get("url", ""))
                    if full:
                        res["content"] = full[:2000]
            return results
        except Exception as e:
            logger.warning("[VECTOR][web_scout] search failed: {}", e)
            return []

    def _parse_ddg_html(self, html: str, limit: int) -> list[dict]:
        """Parse DuckDuckGo HTML results using BeautifulSoup (DDG changes HTML structure frequently)."""
        results = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            # Current DDG structure: results in <article> or <div class="results_links">
            # Try multiple selectors for resilience
            selectors = [
                ('article[data-testid="result"]', 'a[data-testid="result-title-a"]', '[data-result="snippet"]'),
                ('.result', '.result__a', '.result__snippet'),
                ('.web-result', '.result__title a', '.result__snippet'),
            ]
            for result_sel, title_sel, snippet_sel in selectors:
                items = soup.select(result_sel)
                if items:
                    for item in items[:limit]:
                        title_el = item.select_one(title_sel) or item.select_one('a[href]')
                        snippet_el = item.select_one(snippet_sel) or item.select_one('p')
                        if title_el:
                            url = title_el.get('href', '')
                            if url.startswith('/url?'):
                                from urllib.parse import parse_qs, urlparse
                                url = parse_qs(urlparse(url).query).get('uddg', [''])[0]
                            results.append({
                                'title': title_el.get_text(strip=True),
                                'url': url,
                                'snippet': snippet_el.get_text(strip=True) if snippet_el else '',
                            })
                    if results:
                        return results
            # Last resort: any link with href starting with http
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('http') and 'duckduckgo.com' not in href:
                    results.append({'title': a.get_text(strip=True), 'url': href, 'snippet': ''})
                    if len(results) >= limit:
                        break
        except ImportError:
            # BeautifulSoup not installed — use regex fallback with updated selectors
            import re
            # Match any href in anchor tags that look like real URLs
            urls = re.findall(r'href="(https?://[^"]+)"', html)
            titles = re.findall(r'<a[^>]+href="https?://[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
            for url, title in zip(urls, titles):
                if 'duckduckgo.com' not in url:
                    results.append({'title': re.sub('<[^>]+>', '', title).strip(), 'url': url, 'snippet': ''})
                    if len(results) >= limit:
                        break
        except Exception as e:
            logger.warning("[VECTOR][web_scout] DDG parse failed: {}", e)
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
        if not is_safe_url(url):
            logger.warning("[VECTOR][web_scout] SSRF blocked (stealth): {}", url)
            return ""
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

        summary = self._offline_summary(query, source_text, snippets)
        if os.getenv("VECTOR_WEB_SCOUT_LLM") == "1":
            try:
                from core.inference.vectorcode_llm import chat
                from core.prompt_library import get_library as _gl
                _sys = _gl().get_for_agent("web_scout") or hydration
                summary = chat(
                    model=CONFIG["models"]["reasoning"],
                    domain="research",   # glm-4.7 → gemini-2.5-pro → o4-mini → ollama
                    messages=[
                        {"role": "system", "content": _sys},
                        {
                            "role": "user",
                            "content": (
                                f"Research brief for: '{query}'\n\n"
                                "Summarize the key findings in 2-3 paragraphs. Be factual and concise.\n\n"
                                + source_text
                            ),
                        },
                    ],
                    timeout=60.0,
                )
                if not summary:
                    raise RuntimeError("empty model response")
            except Exception as e:
                logger.warning(f"[VECTOR][web_scout] LLM unavailable: {e}")
                summary = self._offline_summary(query, source_text, snippets)

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
            steps=["search_ddg", "fetch_page", "summarize"],
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

    async def web_extract(self, url: str, fields: dict | None = None, want_links: bool = True,
                          max_links: int = 50) -> dict:
        """Read-only page fetch + structured extraction (core/browser/page_extract.py). The fetch is blocking network
        I/O, so it runs in a worker thread. HP follows the honest status: only a fully "ok" extraction is rewarded."""
        from core.browser.page_extract import extract_page

        result = await asyncio.to_thread(
            extract_page, url, fields or {}, want_links=want_links, max_links=int(max_links))
        if result.get("status") == "ok":
            self.award_points(5, "web_extract_ok")
        else:
            self.deduct_points(3, f"web_extract_{result.get('status', 'error')}")
        return result

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        if task.get("type") == "web_extract" or p.get("action") == "web_extract":
            fields = p.get("fields")
            return await self.web_extract(
                p.get("url", ""),
                fields if isinstance(fields, dict) else {},
                want_links=bool(p.get("links", True)),
                max_links=p.get("max_links", 50),
            )
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
