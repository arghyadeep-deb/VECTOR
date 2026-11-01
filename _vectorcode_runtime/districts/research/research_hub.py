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
import re
import asyncio
import datetime
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
from typing import Optional


import httpx
from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG


_HEADERS = {
    "User-Agent": "VECTOR/1.0 (research-hub; +https://github.com/ArghyadeepDeb/VECTOR)",
    "Accept": "application/json",
}


# arXiv boolean operators + filler words that would make an AND query match nothing.
_ARXIV_STOPWORDS = frozenset({
    "and", "or", "not", "andnot", "a", "an", "the", "of", "on", "in", "for", "to", "with",
    "about", "like", "any", "some", "new", "recent", "latest", "papers", "paper",
})


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
        self.capabilities = ["daily_digest", "find", "find_api", "get_hn", "get_india_stocks", "research", "search", "search_arxiv", "search_web", "task_completed"]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info(f"[VECTOR][research_hub] ready gen={generation} hp={self.health_points}")
        # Phase 2B: subscribe to research-triggering events
        self.subscribe_to("task_completed")
        self.subscribe_to("decision_made")

    # Internal action names that are NOT researchable topics — web-searching these
    # is meaningless and used to fire a 15s search on every decision (2026-07-11).
    _SKIP_QUERIES = frozenset({
        "analyze_progress", "research_topic", "respond", "wait", "no_action",
        "analyze", "reflect", "observe", "think", "act", "idle",
    })
    # query -> last-researched epoch; skip repeats within the cooldown.
    _recent_research: dict = {}
    _RESEARCH_COOLDOWN_S = 1800   # 30 min — don't re-research the same query

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Auto-launch deep research on knowledge gap events."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        data = event.get("data", {})
        query = data.get("query") or data.get("topic") or data.get("action_type", "")
        q_norm = str(query).strip().lower()
        # Skip internal action-names and recently-researched queries (debounce).
        if q_norm in self._SKIP_QUERIES:
            return {"status": "skipped", "agent": self.name, "event": et, "reason": "internal-action"}
        import time as _t
        last = self._recent_research.get(q_norm, 0.0)
        if q_norm and _t.time() - last < self._RESEARCH_COOLDOWN_S:
            return {"status": "skipped", "agent": self.name, "event": et, "reason": "cooldown"}
        if query and et in ("task_completed", "decision_made"):
            self._recent_research[q_norm] = _t.time()
            try:
                logger.info(f"[VECTOR][research_hub] event-triggered research: {et} query={query[:50]}")
                results = await self.search_web(str(query)[:100], max_results=5)
                # Store findings in memory for other agents. ConsolidationBot
                # is the memory_curator district's actual registered .name —
                # there is no agent literally named "memory_curator".
                await self.request_agent_help("memory_curator", {
                    "type": "store_findings",
                    "params": {"topic": str(query)[:100], "findings": str(results)[:500]},
                })
            except Exception as e:
                logger.debug(f"[VECTOR][research_hub] handle_event failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

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
        # PRE-RG-D2 (Target B, correction pass): an unquoted `ti:X OR abs:X` with a
        # multi-word topic is not parsed by arXiv as that topic — real retrieval
        # returned the newest papers of ANY subject. Each content term becomes an
        # explicit `all:` AND term (alphanumerics only, so the text cannot inject
        # arXiv query syntax; boolean words / filler dropped).
        terms = [
            t for t in re.findall(r"[A-Za-z0-9]+", query)
            if t.lower() not in _ARXIV_STOPWORDS
        ]
        if not terms:
            return []
        search_query = " AND ".join(f"all:{t}" for t in terms)
        if category:
            search_query = f"cat:{category} AND ({search_query})"

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    # PRE-RG-D2 (Target B): the http:// endpoint now answers with an
                    # EMPTY 301 redirect (ET.fromstring("") -> swallowed -> always []);
                    # https:// returns the Atom feed. PaperReader already uses https.
                    "https://export.arxiv.org/api/query",
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

    # ── CoinGecko crypto prices ───────────────────────────────────────────────

    async def get_crypto_prices(
        self,
        coins: list[str] = ["bitcoin", "ethereum", "solana"],
        vs_currency: str = "usd",
    ) -> list[dict]:
        """
        Fetch live crypto prices + 24h change from CoinGecko free API.
        No auth or API key required.
        """
        ids = ",".join(coins)
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_HEADERS) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={
                        "ids": ids,
                        "vs_currencies": vs_currency,
                        "include_24hr_change": "true",
                    },
                )
                data = resp.json()

            results = []
            for coin in coins:
                coin_data = data.get(coin, {})
                price = coin_data.get(vs_currency)
                change = coin_data.get(f"{vs_currency}_24h_change")
                if price is not None:
                    results.append({
                        "coin": coin,
                        "price": price,
                        "change_24h": round(change, 2) if change is not None else None,
                        "currency": vs_currency,
                        "source": "coingecko",
                    })

            self.award_points(5, "coingecko")
            logger.info(f"[VECTOR][research_hub] crypto prices: {len(results)} coins fetched")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] CoinGecko failed: {e}")
            return []

    # ── Econdb macroeconomic data ─────────────────────────────────────────────

    async def get_economic_data(self, series: str = "RGDP+USA") -> list[dict]:
        """
        Fetch macroeconomic time-series data from Econdb free API (no auth).
        Common series: RGDP+USA (real GDP), CPI+USA, URATE+USA, RGDP+IND.
        Returns last 5 observations sorted newest-first.
        """
        try:
            async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
                resp = await client.get(
                    f"https://www.econdb.com/api/series/{series}/",
                    params={"format": "json", "freq": "A"},
                )
                data = resp.json()

            observations = data.get("data", {}).get("values", [])
            dates = data.get("data", {}).get("dates", [])
            dataset_name = data.get("verbose_name", series)

            results = []
            paired = list(zip(dates, observations))
            for date, value in reversed(paired[-5:]):
                results.append({
                    "series": series,
                    "dataset": dataset_name,
                    "date": date,
                    "value": value,
                    "source": "econdb",
                })

            self.award_points(5, "econdb")
            logger.info(f"[VECTOR][research_hub] economic data '{series}': {len(results)} points")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] Econdb failed: {e}")
            return []

    # ── Crossref academic paper search ────────────────────────────────────────

    async def search_papers(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search academic papers via Crossref free API (no auth required).
        Returns DOI, title, authors, year, and URL for each result.
        """
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        try:
            async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
                resp = await client.get(
                    "https://api.crossref.org/works",
                    params={
                        "query": query,
                        "rows": max_results,
                        "select": "DOI,title,author,published,URL",
                    },
                )
                data = resp.json()

            items = data.get("message", {}).get("items", [])
            results = []
            for item in items:
                title_list = item.get("title", [])
                title = title_list[0] if title_list else ""
                doi = item.get("DOI", "")
                url = item.get("URL", f"https://doi.org/{doi}" if doi else "")
                published = item.get("published", {})
                date_parts = published.get("date-parts", [[None]])
                year = date_parts[0][0] if date_parts and date_parts[0] else None
                authors_raw = item.get("author", [])
                authors = [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in authors_raw[:3]
                ]
                results.append({
                    "title": title,
                    "doi": doi,
                    "url": url,
                    "year": year,
                    "authors": authors,
                    "source": "crossref",
                })

            self.award_points(5, f"crossref:{query[:20]}")
            logger.info(f"[VECTOR][research_hub] Crossref '{query[:20]}': {len(results)} papers")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] Crossref failed: {e}")
            return []

    # ── OpenAQ air quality ────────────────────────────────────────────────────

    async def get_air_quality(self, city: str = "Kolkata") -> list[dict]:
        """
        Fetch air quality readings (PM2.5, PM10) from OpenAQ free API (no auth).
        Returns up to 3 monitoring stations near the requested city.
        """
        try:
            async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
                resp = await client.get(
                    "https://api.openaq.org/v3/locations",
                    params={
                        "city": city,
                        "limit": 3,
                        "order_by": "lastUpdated",
                    },
                )
                data = resp.json()

            results = []
            for loc in data.get("results", []):
                sensors = loc.get("sensors", [])
                pm25 = next(
                    (s.get("lastValue") for s in sensors if s.get("parameter", {}).get("name") == "pm25"),
                    None,
                )
                pm10 = next(
                    (s.get("lastValue") for s in sensors if s.get("parameter", {}).get("name") == "pm10"),
                    None,
                )
                # Simple AQI proxy from PM2.5 (US EPA breakpoints rough approximation)
                aqi = None
                if pm25 is not None:
                    if pm25 <= 12:
                        aqi = "Good"
                    elif pm25 <= 35.4:
                        aqi = "Moderate"
                    elif pm25 <= 55.4:
                        aqi = "Unhealthy for Sensitive Groups"
                    elif pm25 <= 150.4:
                        aqi = "Unhealthy"
                    else:
                        aqi = "Very Unhealthy"
                results.append({
                    "location": loc.get("name", ""),
                    "city": city,
                    "pm25": pm25,
                    "pm10": pm10,
                    "aqi": aqi,
                    "updated_at": loc.get("datetimeLast", {}).get("utc", ""),
                    "source": "openaq",
                })

            self.award_points(5, f"openaq:{city}")
            logger.info(f"[VECTOR][research_hub] air quality '{city}': {len(results)} stations")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] OpenAQ failed: {e}")
            return []

    # ── Combined tech news feed ───────────────────────────────────────────────

    async def get_tech_news(self, limit: int = 10) -> list[dict]:
        """
        Combined tech news from HackerNews + DEV.to, fetched concurrently.
        Merges, deduplicates by URL, and sorts by score/reactions descending.
        Returns top `limit` items.
        """
        try:
            hn_results, devto_results = await asyncio.gather(
                self.get_hn_top(limit=limit),
                self.get_devto_posts(tag="webdev", limit=limit),
                return_exceptions=True,
            )

            merged: list[dict] = []

            if isinstance(hn_results, list):
                for item in hn_results:
                    merged.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "score": item.get("score", 0),
                        "source": item.get("source", "hackernews"),
                    })

            if isinstance(devto_results, list):
                seen_urls = {m["url"] for m in merged}
                for item in devto_results:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        merged.append({
                            "title": item.get("title", ""),
                            "url": url,
                            "score": item.get("reactions", 0),
                            "source": item.get("source", "devto"),
                        })
                        seen_urls.add(url)

            merged.sort(key=lambda x: x.get("score", 0), reverse=True)
            result = merged[:limit]

            self.award_points(5, "tech_news_combined")
            logger.info(f"[VECTOR][research_hub] tech_news combined: {len(result)} items (HN + DEV.to)")
            return result

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] get_tech_news failed: {e}")
            return []

    # ── NSE India stock quotes (Yahoo Finance) ────────────────────────────────

    async def get_india_stocks(
        self, symbols: list[str] = ["RELIANCE", "TCS", "INFY"]
    ) -> list[dict]:
        """
        Fetch NSE India stock quotes via Yahoo Finance compatible endpoint (no auth).
        Appends .NS suffix for NSE listings. Returns price, % change, and volume.
        """
        results = []
        try:
            async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
                tasks = [
                    client.get(
                        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.NS",
                        params={"interval": "1d", "range": "1d"},
                    )
                    for sym in symbols
                ]
                responses = await asyncio.gather(*tasks, return_exceptions=True)

            for sym, resp in zip(symbols, responses):
                if isinstance(resp, Exception):
                    logger.warning(f"[VECTOR][research_hub] Yahoo Finance {sym} failed: {resp}")
                    continue
                try:
                    data = resp.json()
                    meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
                    price = meta.get("regularMarketPrice")
                    prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")
                    volume = meta.get("regularMarketVolume")
                    change_pct = None
                    if price is not None and prev_close:
                        change_pct = round((price - prev_close) / prev_close * 100, 2)
                    results.append({
                        "symbol": sym,
                        "exchange": "NSE",
                        "price": price,
                        "change_pct": change_pct,
                        "volume": volume,
                        "currency": meta.get("currency", "INR"),
                        "source": "yahoo_finance",
                    })
                except Exception as parse_err:
                    logger.warning(f"[VECTOR][research_hub] Yahoo Finance parse {sym}: {parse_err}")

            if results:
                self.award_points(5, "india_stocks")
                logger.info(f"[VECTOR][research_hub] india_stocks: {len(results)}/{len(symbols)} fetched")
            return results

        except Exception as e:
            logger.warning(f"[VECTOR][research_hub] get_india_stocks failed: {e}")
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
        crypto_task = self.get_crypto_prices()
        tech_news_task = self.get_tech_news(limit=10)

        hn, gh, devto, arxiv, crypto, tech_news = await asyncio.gather(
            hn_task, gh_task, devto_task, arxiv_task, crypto_task, tech_news_task
        )

        digest = {
            "date": datetime.date.today().isoformat(),
            "hackernews": hn,
            "github_trending": gh,
            "devto": devto,
            "arxiv": arxiv,
            "crypto_prices": crypto,
            "tech_news": tech_news,
        }

        # Store summary in episodic memory
        try:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            summary = (
                f"Daily digest: {len(hn)} HN stories, {len(gh)} GitHub repos, "
                f"{len(devto)} DEV.to posts, {len(arxiv)} ArXiv papers, "
                f"{len(crypto)} crypto prices, {len(tech_news)} tech news items"
            )
            mem.store(
                event_type="daily_research_digest",
                content=summary,
                tags=["research", "digest", "daily"],
                source="research_hub",
            )
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)

        self.award_points(10, "daily_digest")
        total = len(hn) + len(gh) + len(devto) + len(arxiv) + len(crypto) + len(tech_news)
        logger.info(f"[VECTOR][research_hub] daily_digest complete: {total} total items")
        return digest


    async def run_forever(self) -> None:
        logger.info("[VECTOR][research_hub] run_forever started — fires at 06:00")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.hour == 6 and now.minute == 0:
                    await self.daily_digest()
            except Exception as e:
                logger.error(f"[VECTOR][research_hub] tick error: {e}")
                self.deduct_points(5, "tick_error")
            for _ in range(3600):
                if not self.is_alive:
                    break
                await asyncio.sleep(1)
        logger.warning("[VECTOR][research_hub] died — HP=0")

    @staticmethod
    def _format_list_response(label: str, items: list[dict]) -> str:
        """
        Render a list-of-dicts result into readable text.

        2026-07-22: every branch below used to return raw structured data
        under a "results"/"apis" key with no matching entry in
        avatar/avatar_voice.py::_extract_text()'s checked-key list
        (response/result/content/message/text/output — note "results" !=
        "result"), so real search/digest data was silently swallowed into
        a bare "Task completed — status: ok." stub (KNOWN_ISSUES.md #1
        pattern). Now every branch also populates `response` with a
        formatted summary built from this same data.
        """
        if not items:
            return f"No {label.lower()} found."
        lines = [f"{label} ({len(items)}):"]
        for it in items[:8]:
            if not isinstance(it, dict):
                lines.append(f"- {it}")
                continue
            title = it.get("title") or it.get("symbol") or it.get("name") or str(it)[:60]
            extra = it.get("url") or it.get("snippet") or it.get("price")
            lines.append(f"- {title} — {extra}" if extra else f"- {title}")
        return "\n".join(lines)

    @staticmethod
    def _digest_response(digest: dict) -> str:
        return (
            f"Daily research digest ({digest.get('date', '?')}): "
            f"{len(digest.get('hackernews', []) or [])} HN stories, "
            f"{len(digest.get('github_trending', []) or [])} GitHub repos, "
            f"{len(digest.get('devto', []) or [])} DEV.to posts, "
            f"{len(digest.get('arxiv', []) or [])} ArXiv papers, "
            f"{len(digest.get('tech_news', []) or [])} tech news items."
        )

    async def run(self, task: dict) -> dict:
        """Governor dispatch interface."""
        t = task.get("type", "")
        p = task.get("params", {})
        if t in ("search_web", "search", "find"):
            query = p.get("query", "")
            results = await self.search_web(query)
            response = self._format_list_response(f"Web search results for '{query}'", results)
            return {"status": "ok", "response": response, "results": results}
        if t in ("daily_digest", "morning_brief"):
            digest = await self.daily_digest()
            return {"status": "ok", "response": self._digest_response(digest), **digest}
        if t in ("search_arxiv", "paper"):
            query = p.get("query", "AI")
            results = await self.search_arxiv(query)
            response = self._format_list_response(f"ArXiv papers for '{query}'", results)
            return {"status": "ok", "response": response, "results": results}
        if t in ("get_hn", "hackernews", "news"):
            results = await self.get_hn_top(p.get("limit", 10))
            response = self._format_list_response("Top HackerNews stories", results)
            return {"status": "ok", "response": response, "results": results}
        if t in ("get_india_stocks", "stocks"):
            results = await self.get_india_stocks(p.get("symbols", ["RELIANCE", "TCS"]))
            response = self._format_list_response("India stock quotes", results)
            return {"status": "ok", "response": response, "results": results}
        if t in ("find_api", "discover_api", "api_catalog"):
            # Use public-apis catalog to find data sources
            try:
                from districts.research.api_catalog import search_apis
                results = search_apis(p.get("query", ""), p.get("category", ""), limit=p.get("limit", 10))
                response = self._format_list_response("Matching APIs", results)
                return {"status": "ok", "response": response, "apis": results, "count": len(results)}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        # default: run daily digest
        digest = await self.daily_digest()
        return {"status": "ok", "response": self._digest_response(digest), **digest}


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
