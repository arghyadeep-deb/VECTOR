import sys
import uuid
import asyncio
import datetime
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

# RSS feeds for tech/AI news — no API key required
_RSS_FEEDS = [
    ("Hacker News", "https://news.ycombinator.com/rss"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
]


class NewsAggregator(AgentBase):
    """
    Aggregates tech/AI news from NewsAPI + RSS fallback.
    Delivers a morning brief to Obsidian and optionally via Pushover.
    Runs daily at 7AM.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="NewsAggregator",
            district="research",
            generation=generation,
        )
        self.capabilities = ["daily_digest", "get_recent", "get_top_stories", "news", "research"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        self._newsapi_key = CONFIG["api_keys"].get("newsapi_key", "")
        logger.info(f"[VECTOR][news_aggregator] ready gen={generation} hp={self.health_points}")

    # ── Fetch ──────────────────────────────────────────────────────────────────

    async def fetch_newsapi(self, query: str = "artificial intelligence", max: int = 10) -> list[dict]:
        """NewsAPI headlines. Falls back to empty list if key missing."""
        if not self._newsapi_key:
            return []
        try:
            import httpx
            params = {
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": max,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Keep credentials out of the URL. Request URLs commonly appear
                # in proxy/access logs and in exception strings.
                r = await client.get(
                    "https://newsapi.org/v2/everything",
                    params=params,
                    headers={"X-Api-Key": self._newsapi_key},
                )
            if r.status_code != 200:
                return []
            articles = r.json().get("articles", [])
            return [
                {
                    "title": a.get("title", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "description": (a.get("description") or "")[:200],
                    "published": (a.get("publishedAt") or "")[:10],
                }
                for a in articles
                if a.get("title")
            ]
        except Exception as e:
            logger.warning(f"[VECTOR][news_aggregator] NewsAPI failed: {e}")
            return []

    async def fetch_rss(self, feed_url: str, source_name: str, max: int = 5) -> list[dict]:
        """Fetch and parse an RSS feed. No dependencies beyond stdlib + httpx."""
        try:
            import httpx
            try:
                import defusedxml.ElementTree as ET
            except ImportError:
                import xml.etree.ElementTree as ET
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(feed_url)
            root = ET.fromstring(r.text)
            items = root.findall(".//item")[:max]
            results = []
            for item in items:
                title = (item.findtext("title") or "").strip()
                url = (item.findtext("link") or "").strip()
                desc = (item.findtext("description") or "").strip()[:200]
                pub = (item.findtext("pubDate") or "")[:16]
                if title:
                    results.append({
                        "title": title,
                        "source": source_name,
                        "url": url,
                        "description": desc,
                        "published": pub,
                    })
            return results
        except Exception as e:
            logger.warning(f"[VECTOR][news_aggregator] RSS {source_name} failed: {e}")
            return []

    async def fetch_via_connectors(self, max_per_source: int = 5) -> list[dict]:
        """Pull news via absorbed VectorCode connectors (HackerNews, GitHub releases,
        news_rss aggregator). Each source is guarded — missing connectors are skipped.
        Returns a flat list of {title, source, url, description, published}.
        """
        out: list[dict] = []

        # HackerNews top stories
        try:
            from vectorcode.src.connectors.hackernews import HackerNewsConnector  # type: ignore
            hn = HackerNewsConnector()
            for name in ("get_top_stories", "top_stories", "fetch_top", "today"):
                fn = getattr(hn, name, None)
                if callable(fn):
                    raw = fn(max_per_source)
                    if asyncio.iscoroutine(raw):
                        raw = await raw
                    if isinstance(raw, list):
                        for item in raw[:max_per_source]:
                            if isinstance(item, dict):
                                out.append({
                                    "title": item.get("title", "") or "",
                                    "source": "hackernews",
                                    "url": item.get("url") or item.get("link", "") or "",
                                    "description": (item.get("text") or item.get("description", ""))[:200],
                                    "published": str(item.get("time") or item.get("created_at", ""))[:16],
                                })
                    break
        except Exception as e:
            logger.debug(f"[VECTOR][news_aggregator] hackernews connector unavailable: {e}")

        # GitHub notifications (trending releases / starred-author updates)
        try:
            from vectorcode.src.connectors.github_notifications import (  # type: ignore
                GitHubNotificationsConnector,
            )
            gh = GitHubNotificationsConnector()
            for name in ("get_recent", "recent", "fetch_recent", "today"):
                fn = getattr(gh, name, None)
                if callable(fn):
                    raw = fn(max_per_source)
                    if asyncio.iscoroutine(raw):
                        raw = await raw
                    if isinstance(raw, list):
                        for item in raw[:max_per_source]:
                            if isinstance(item, dict):
                                out.append({
                                    "title": item.get("title") or item.get("subject", "") or "",
                                    "source": "github",
                                    "url": item.get("url") or item.get("html_url", "") or "",
                                    "description": (item.get("body") or item.get("repo", ""))[:200],
                                    "published": str(item.get("updated_at") or item.get("created_at", ""))[:16],
                                })
                    break
        except Exception as e:
            logger.debug(f"[VECTOR][news_aggregator] github connector unavailable: {e}")

        # News RSS aggregator (richer than our raw httpx version)
        try:
            from vectorcode.src.connectors.news_rss import NewsRSSConnector  # type: ignore
            rss = NewsRSSConnector()
            for name in ("get_recent", "fetch_today", "today", "snapshot"):
                fn = getattr(rss, name, None)
                if callable(fn):
                    raw = fn(max_per_source * 5)
                    if asyncio.iscoroutine(raw):
                        raw = await raw
                    if isinstance(raw, list):
                        for item in raw[: max_per_source * 5]:
                            if isinstance(item, dict):
                                out.append({
                                    "title": item.get("title", "") or "",
                                    "source": item.get("feed_name") or "rss",
                                    "url": item.get("url") or item.get("link", "") or "",
                                    "description": (item.get("summary") or item.get("description", ""))[:200],
                                    "published": str(item.get("published", ""))[:16],
                                })
                    break
        except Exception as e:
            logger.debug(f"[VECTOR][news_aggregator] news_rss connector unavailable: {e}")

        return out

    async def gather_news(self, max_per_source: int = 5) -> list[dict]:
        """Gather from NewsAPI + RSS feeds + absorbed connectors. Returns deduplicated list."""
        tasks: list = [self.fetch_newsapi(max=max_per_source)]
        for name, url in _RSS_FEEDS:
            tasks.append(self.fetch_rss(url, name, max=max_per_source))
        # Connector-backed sources in parallel with the legacy ones
        tasks.append(self.fetch_via_connectors(max_per_source=max_per_source))

        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        articles: list[dict] = []
        for r in all_results:
            if isinstance(r, list):
                articles.extend(r)

        # Deduplicate by URL
        seen: set[str] = set()
        unique = []
        for a in articles:
            if a["url"] and a["url"] not in seen:
                seen.add(a["url"])
                unique.append(a)

        logger.info(f"[VECTOR][news_aggregator] gathered {len(unique)} unique articles")
        return unique

    async def morning_brief(self) -> bool:
        """
        Gathers news, filters for relevance, writes to Obsidian Daily/ + Research/.
        Returns True on success.
        """
        articles = await self.gather_news(max_per_source=5)
        date_str = datetime.date.today().isoformat()

        if not articles:
            logger.warning("[VECTOR][news_aggregator] no articles gathered")
            self.deduct_points(10, "no articles gathered")
            return False

        hydration = self._context.session_hydration_prompt()  # RULE 1

        # LLM picks the top 5 most relevant for Arghyadeep
        try:
            from core.inference.vectorcode_llm import chat
            titles_list = "\n".join(
                f"[{i+1}] {a['title']} ({a['source']})" for i, a in enumerate(articles[:20])
            )
            raw = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": hydration},
                    {
                        "role": "user",
                        "content": (
                            "Pick the 5 most relevant tech/AI articles for a CS student and AI engineer "
                            "building a local AI assistant. Return ONLY the numbers as a comma-separated list.\n\n"
                            + titles_list
                        ),
                    },
                ],
                timeout=2.0,
            )
            if not raw:
                raise RuntimeError("empty model response")
            import re
            nums = [int(n.strip()) - 1 for n in re.findall(r"\d+", raw) if 0 < int(n.strip()) <= len(articles)]
            top_articles = [articles[i] for i in nums[:5]]
        except Exception as e:
            logger.warning(f"[VECTOR][news_aggregator] LLM filter unavailable: {e}")
            top_articles = articles[:5]

        # Build note content
        lines = [f"## Morning News Brief — {date_str}\n"]
        for a in top_articles:
            lines.append(f"### [{a['title']}]({a['url']})")
            lines.append(f"*{a['source']}* — {a['published']}")
            if a["description"]:
                lines.append(f"> {a['description']}")
            lines.append("")

        note_content = "\n".join(lines)

        self._memory.store(
            event_type="news_brief",
            content=f"NewsAggregator morning brief — {len(top_articles)} articles",
            tags=["news", "brief", "daily"],
            source="news_aggregator",
        )
        self._memory.store_chain(
            situation="morning_news_brief",
            goal_ids=["stay_informed"],
            steps=["gather_news", "filter_llm", "write_vault"],
            action="morning_brief",
            outcome=f"{len(top_articles)} articles in brief",
            reward=0.8,
        )

        try:
            self._obsidian.write_note(
                title=f"News Brief — {date_str}",
                content=note_content,
                folder="Research",
                tags=["news", "brief", "daily", "vector"],
            )
            self.award_points(35, f"morning brief: {len(top_articles)} articles")
            logger.info(f"[VECTOR][news_aggregator] brief written: {len(top_articles)} articles")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][news_aggregator] vault write failed: {e}")
            self.deduct_points(15, "vault write failed")
            return False

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        results = await self.fetch_newsapi(p.get("query", "artificial intelligence"))
        return {"status": "ok", "articles": results, "count": len(results)}

    async def run_forever(self) -> None:
        """Morning brief at 07:05. RULE 2 — never crashes."""
        logger.info("[VECTOR][news_aggregator] run_forever started — daily at 07:05")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.hour == 7 and 5 <= now.minute < 10:
                    await self.morning_brief()
            except Exception as e:
                logger.error(f"[VECTOR][news_aggregator] tick error: {e}")
                self.deduct_points(10, "tick error")

            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)

        logger.warning("[VECTOR][news_aggregator] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bot = NewsAggregator()
        assert bot.health_points == 500
        assert bot.name == "NewsAggregator"

        import tempfile
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            bot._obsidian._vault = vault

            ok = await bot.morning_brief()
            assert isinstance(ok, bool)

        print(f"✅ news_aggregator.py OK  HP={bot.health_points} ok={ok}")

    asyncio.run(_smoke())
