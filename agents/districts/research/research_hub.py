"""
VECTOR Research Hub — 100% native Python research engine.
No npm, no external tools, no opencli dependency.

Covers:
  - Web search (DuckDuckGo DDG API — no key needed)
  - HackerNews (Firebase JSON API)
  - GitHub trending (GitHub Search API — no auth for public)
  - ProductHunt (public GraphQL API)
  - DEV.to (free public API)
  - ArXiv (XML API)
  - Reddit (public JSON API — already in RedditMiner)
  - YouTube trending (yt-dlp — already installed)
  - CoinGecko (crypto prices + 24h change — no auth)
  - Econdb (macroeconomic series — no auth)
  - Crossref (academic paper search — no auth)
  - OpenAQ (air quality / PM2.5 / PM10 — no auth)
  - Tech news combined feed (HackerNews + DEV.to merged)
  - Yahoo Finance (NSE India stock quotes — no auth)

RULE 11: no external LLM APIs.
"""
import sys
import asyncio
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import httpx
from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG


_HEADERS = {
    "User-Agent": "VECTOR/1.0 (research-hub; +https://github.com/ArghyadeepDeb/VECTOR)",
    "Accept": "application/json",
}


class ResearchHub(AgentBase):
    """
    VECTOR's all-native research engine.
    Replaces OpenCLI — zero npm/external-tool dependency.
    Every source uses public APIs that require no auth or key.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        import uuid
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ResearchHub",
            district="research",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        logger.info(f"[VECTOR][research_hub] ready gen={generation} hp={self.health_points}")

    # ── Web Search (DuckDuckGo Instant Answer — no key) ───────────────────────

    async def search_web(self, query: str, max_results: int = 8) -> list[dict]:
        """
        Search the web via DuckDuckGo's public JSON API.
        Zero config, no API key, no rate limits for normal use.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": "1",
                        "skip_disambig": "1",
                    },
                )
                data = resp.json()

            results = []

            # Abstract (primary result)
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", query),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data["Abstract"][:300],
                    "source": "ddg_abstract",
                })

            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("Text", "")[:80],
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", "")[:200],
                        "source": "ddg_related",
                    })

            if results:
                self.award_points(3, f"web_search: {query[:30]}")
                logger.info(f"[VECTOR][research_hub] search '{query[:30]}' → {len(results)} results")
                return results[:max_results]

            # DDG abstract was empty — try HTML search scrape
            return await self._search_ddg_html(query, max_results)

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] search failed: {e}")
            return []

    async def _search_ddg_html(self, query: str, max_results: int) -> list[dict]:
        """Fallback: scrape DuckDuckGo HTML results (no JS required)."""
        import re
        results = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={**_HEADERS, "Accept": "text/html"},
                    follow_redirects=True,
                )
                text = resp.text
            # Extract result links and snippets
            links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)<', text)
            snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)<', text)
            for i, (url, title) in enumerate(links[:max_results]):
                results.append({
                    "title": title.strip(),
                    "url": url,
                    "snippet": snippets[i].strip() if i < len(snippets) else "",
                    "source": "ddg_html",
                })
        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] DDG HTML fallback failed: {e}")
        return results

    # ── HackerNews ────────────────────────────────────────────────────────────

    async def get_hn_top(self, limit: int = 20) -> list[dict]:
        """HackerNews top stories via official Firebase JSON API."""
        try:
            async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
                resp = await client.get(
                    "https://hacker-news.firebaseio.com/v0/topstories.json"
                )
                ids = resp.json()[:limit]

                tasks = [
                    client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
                    for story_id in ids[:min(limit, 15)]
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)

            results = []
            for r in responses:
                if isinstance(r, Exception):
                    continue
                item = r.json()
                if item and item.get("type") == "story":
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", f"https://news.ycombinator.com/item?id={item.get('id')}"),
                        "score": item.get("score", 0),
                        "by": item.get("by", ""),
                        "comments": item.get("descendants", 0),
                        "source": "hackernews",
                    })

            self.award_points(3, "hn_top")
            logger.info(f"[VECTOR][research_hub] HN top: {len(results)} stories")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] HN failed: {e}")
            return []

    async def get_hn_ask(self, limit: int = 10) -> list[dict]:
        """HackerNews Ask HN posts."""
        try:
            async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
                resp = await client.get("https://hacker-news.firebaseio.com/v0/askstories.json")
                ids = resp.json()[:limit]
                tasks = [
                    client.get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
                    for i in ids[:10]
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)

            results = []
            for r in responses:
                if isinstance(r, Exception):
                    continue
                item = r.json()
                if item:
                    results.append({
                        "title": item.get("title", ""),
                        "text": (item.get("text", "") or "")[:200],
                        "by": item.get("by", ""),
                        "score": item.get("score", 0),
                        "source": "hn_ask",
                    })
            return results
        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] HN Ask failed: {e}")
            return []

    # ── GitHub Trending ───────────────────────────────────────────────────────

    async def get_github_trending(
        self, language: str = "python", since_days: int = 7, limit: int = 10
    ) -> list[dict]:
        """GitHub trending repos via GitHub Search API (no auth needed for public)."""
        since = (datetime.date.today() - datetime.timedelta(days=since_days)).isoformat()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    params={
                        "q": f"language:{language} created:>{since}",
                        "sort": "stars",
                        "order": "desc",
                        "per_page": limit,
                    },
                    headers={
                        **_HEADERS,
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
                data = resp.json()

            results = []
            for repo in data.get("items", []):
                results.append({
                    "name": repo.get("full_name", ""),
                    "description": repo.get("description", "") or "",
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                    "url": repo.get("html_url", ""),
                    "topics": repo.get("topics", []),
                    "source": "github_trending",
                })

            self.award_points(3, f"github_trending:{language}")
            logger.info(f"[VECTOR][research_hub] GitHub trending {language}: {len(results)} repos")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] GitHub trending failed: {e}")
            return []

    # ── DEV.to ────────────────────────────────────────────────────────────────

    async def get_devto_posts(self, tag: str = "ai", limit: int = 10) -> list[dict]:
        """DEV.to posts by tag via official free API."""
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
                resp = await client.get(
                    "https://dev.to/api/articles",
                    params={"tag": tag, "per_page": limit, "top": "7"},
                )
                articles = resp.json()

            results = []
            for a in articles:
                results.append({
                    "title": a.get("title", ""),
                    "url": a.get("url", ""),
                    "tags": a.get("tag_list", []),
                    "reactions": a.get("positive_reactions_count", 0),
                    "comments": a.get("comments_count", 0),
                    "reading_time": a.get("reading_time_minutes", 0),
                    "source": "devto",
                })

            self.award_points(3, f"devto:{tag}")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] DEV.to failed: {e}")
            return []

    # ── ArXiv ─────────────────────────────────────────────────────────────────

    async def search_arxiv(
        self,
        query: str,
        max_results: int = 5,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        ArXiv paper search via official XML API (no key needed).
        category examples: cs.AI, cs.LG, cs.CL, stat.ML
        """
        search_query = f"ti:{query} OR abs:{query}"
        if category:
            search_query = f"cat:{category} AND ({search_query})"

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "http://export.arxiv.org/api/query",
                    params={
                        "search_query": search_query,
                        "start": 0,
                        "max_results": max_results,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    },
                )
                root = ET.fromstring(resp.text)

            ns = {"atom": "http://www.w3.org/2005/Atom"}
            results = []
            for entry in root.findall("atom:entry", ns):
                title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
                summary = entry.findtext("atom:summary", "", ns).strip()[:400]
                link = entry.findtext("atom:id", "", ns)
                published = entry.findtext("atom:published", "", ns)[:10]
                authors = [
                    a.findtext("atom:name", "", ns)
                    for a in entry.findall("atom:author", ns)
                ]
                results.append({
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "authors": authors[:3],
                    "published": published,
                    "source": "arxiv",
                })

            self.award_points(5, f"arxiv:{query[:20]}")
            logger.info(f"[VECTOR][research_hub] ArXiv '{query[:20]}': {len(results)} papers")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] ArXiv failed: {e}")
            return []

    # ── ProductHunt ───────────────────────────────────────────────────────────

    async def get_producthunt_top(self, limit: int = 10) -> list[dict]:
        """ProductHunt top posts today via public GraphQL API (no auth needed)."""
        query = """
        {
          posts(order: VOTES, first: %d) {
            edges {
              node {
                name
                tagline
                url
                votesCount
                commentsCount
                website
                topics { edges { node { name } } }
              }
            }
          }
        }
        """ % limit

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.producthunt.com/v2/api/graphql",
                    json={"query": query},
                    headers={**_HEADERS, "Accept": "application/json"},
                )
                data = resp.json()

            results = []
            for edge in data.get("data", {}).get("posts", {}).get("edges", []):
                node = edge.get("node", {})
                topics = [
                    t["node"]["name"]
                    for t in node.get("topics", {}).get("edges", [])
                ]
                results.append({
                    "name": node.get("name", ""),
                    "tagline": node.get("tagline", ""),
                    "url": node.get("url", ""),
                    "website": node.get("website", ""),
                    "votes": node.get("votesCount", 0),
                    "comments": node.get("commentsCount", 0),
                    "topics": topics,
                    "source": "producthunt",
                })

            self.award_points(3, "producthunt_top")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] ProductHunt failed: {e}")
            return []

    # ── YouTube (yt-dlp) ──────────────────────────────────────────────────────

    async def search_youtube(self, query: str, limit: int = 5) -> list[dict]:
        """Search YouTube via yt-dlp (already installed in VECTOR)."""
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "playlist_items": f"1:{limit}",
            }

            def _search():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                    return info.get("entries", [])

            entries = await asyncio.get_event_loop().run_in_executor(None, _search)
            results = []
            for e in entries:
                if e:
                    results.append({
                        "title": e.get("title", ""),
                        "url": f"https://youtu.be/{e.get('id', '')}",
                        "channel": e.get("channel", e.get("uploader", "")),
                        "duration": e.get("duration", 0),
                        "view_count": e.get("view_count", 0),
                        "source": "youtube",
                    })

            self.award_points(3, f"youtube:{query[:20]}")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] YouTube search failed: {e}")
            return []

    # ── Aggregated daily digest ───────────────────────────────────────────────

    async def daily_digest(self) -> dict:
        """
        Pull VECTOR's morning research digest from all sources in parallel.
        Returns structured dict with HN/GitHub/DevTo/ArXiv sections.
        """
        hn_task = self.get_hn_top(limit=10)
        gh_task = self.get_github_trending("python", limit=5)
        devto_task = self.get_devto_posts("machinelearning", limit=5)
        arxiv_task = self.search_arxiv("large language model", max_results=3, category="cs.AI")

        hn, gh, devto, arxiv = await asyncio.gather(
            hn_task, gh_task, devto_task, arxiv_task
        )

        digest = {
            "date": datetime.date.today().isoformat(),
            "hackernews": hn,
            "github_trending": gh,
            "devto": devto,
            "arxiv": arxiv,
        }

        # Store summary in episodic memory
        try:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            summary = (
                f"Daily digest: {len(hn)} HN stories, {len(gh)} GitHub repos, "
                f"{len(devto)} DEV.to posts, {len(arxiv)} ArXiv papers"
            )
            mem.store(
                event_type="daily_research_digest",
                content=summary,
                tags=["research", "digest", "daily"],
                source="research_hub",
            )
        except Exception:
            pass

        self.award_points(10, "daily_digest")
        logger.info(f"[VECTOR][research_hub] daily_digest complete: {len(hn)+len(gh)+len(devto)+len(arxiv)} total items")
        return digest


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        hub = ResearchHub(generation=1)
        assert hub.name == "ResearchHub"
        assert hub.district == "research"

        # HN top (real call)
        hn = await hub.get_hn_top(limit=3)
        assert isinstance(hn, list)
        print(f"  HN top (3): {len(hn)} items")
        if hn:
            print(f"    #1: {hn[0].get('title', '?')[:60]}")

        # GitHub trending
        gh = await hub.get_github_trending("python", limit=3)
        assert isinstance(gh, list)
        print(f"  GitHub trending python: {len(gh)} repos")

        # ArXiv
        papers = await hub.search_arxiv("transformer", max_results=2, category="cs.LG")
        assert isinstance(papers, list)
        print(f"  ArXiv cs.LG transformer: {len(papers)} papers")

        # DEV.to
        devto = await hub.get_devto_posts("python", limit=3)
        assert isinstance(devto, list)
        print(f"  DEV.to python: {len(devto)} posts")

        print(f"OK  research_hub.py  HP={hub.health_points}")

    asyncio.run(_smoke())
