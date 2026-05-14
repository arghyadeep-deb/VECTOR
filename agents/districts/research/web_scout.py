import sys
import uuid
import asyncio
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
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
        """DuckDuckGo search — no API key required. Returns list of {title, url, snippet}."""
        try:
            import httpx
            encoded = query.replace(" ", "+")
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            headers = {"User-Agent": "Mozilla/5.0 (compatible; VECTOR/1.0)"}
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(url, headers=headers)
            results = self._parse_ddg_html(r.text, max_results)
            logger.info(f"[VECTOR][web_scout] search '{query}' → {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"[VECTOR][web_scout] search failed: {e}")
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

    async def fetch_page(self, url: str) -> str:
        """Fetch a URL and convert to markdown via MarkItDown."""
        try:
            import httpx
            sys.path.insert(0, str(Path(__file__).parent))
            from markitdown import MarkItDown

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                r = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0 (compatible; VECTOR/1.0)"}
                )
            md = MarkItDown()
            result = md.convert_stream(
                __import__("io").BytesIO(r.content),
                file_extension=".html",
            )
            return result.text_content[:8000]
        except Exception as e:
            logger.warning(f"[VECTOR][web_scout] fetch_page failed {url}: {e}")
            return ""

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
            from core.inference.ollama_safe import chat
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

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
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
