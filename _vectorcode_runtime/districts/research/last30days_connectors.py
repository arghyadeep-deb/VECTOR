"""First live connector for the last30days recency-intelligence brief.

districts/research/last30days.py is a pure schema (RecentSignal,
Last30DaysBrief) with zero live connectors by design — its own docstring
says connectors come "after SkillSpector quarantine". SkillSpector now
exists and is manifest-registered. HackerNews is a first-party,
already-used-elsewhere VECTOR data source (research_hub.py's get_hn_top,
a plain public JSON API fetch) — not third-party skill/prompt text, so
SkillSpector's scan-before-trust scope doesn't apply here.

Degrades gracefully: a connector failure adds its name to
Last30DaysBrief.degraded_sources rather than raising, matching the house
convention (resilience first, never propagate from an observe-style call).
"""
from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from districts.research.last30days import Last30DaysBrief, RecentSignal, build_brief

__all__ = [
    "connect_hackernews", "connect_reddit", "connect_github",
    "connect_web_search", "connect_all",
]

_DEFAULT_SUBREDDITS = ["MachineLearning", "LocalLLaMA"]


async def connect_hackernews(query: str, limit: int = 20) -> Last30DaysBrief:
    """Fetch HN top stories and normalize into the last30days brief schema.

    `query` is metadata only (HN's top-stories endpoint isn't search-filterable
    by topic) — recorded on the brief so callers can see what context this
    snapshot was taken for; real topic filtering would need a different
    connector (e.g. HN Algolia search API), left for a future pass.
    """
    try:
        from districts.research.research_hub import ResearchHub

        stories = await ResearchHub().get_hn_top(limit=limit)
        signals = [
            RecentSignal(
                source="hackernews",
                title=story.get("title", ""),
                url=story.get("url", ""),
                # HN's Firebase API doesn't return a timestamp in get_hn_top's
                # current shape — treat as "now" (best-effort; a future pass
                # could thread the item's real `time` field through).
                published_at=datetime.now(timezone.utc).isoformat(),
                engagement=float(story.get("score", 0)),
                confidence=0.8,
                notes=f"by {story.get('by', 'unknown')}, {story.get('comments', 0)} comments",
            )
            for story in stories
        ]
        return build_brief(query, signals)
    except Exception as exc:
        logger.warning("[VECTOR][last30days] hackernews connector failed: {}", exc)
        return build_brief(query, [], degraded_sources=["hackernews"])


async def connect_reddit(query: str, subreddits: list[str] | None = None, limit: int = 10) -> Last30DaysBrief:
    """Fetch hot posts from the given subreddits and normalize into the
    last30days brief schema. Reuses RedditMiner.fetch_hot — already a
    first-party VECTOR connector against Reddit's public read-only JSON API
    (no OAuth), not third-party skill text.
    """
    try:
        from districts.research.reddit_miner import RedditMiner

        miner = RedditMiner()
        subs = subreddits or _DEFAULT_SUBREDDITS
        signals: list[RecentSignal] = []
        for sub in subs:
            posts = await miner.fetch_hot(sub, limit=limit)
            for post in posts:
                signals.append(RecentSignal(
                    source="reddit",
                    title=post.get("title", ""),
                    url=post.get("url", ""),
                    published_at=datetime.now(timezone.utc).isoformat(),
                    engagement=float(post.get("score", 0)),
                    confidence=0.7,
                    notes=f"r/{post.get('subreddit', sub)}, {post.get('comments', 0)} comments",
                ))
        return build_brief(query, signals)
    except Exception as exc:
        logger.warning("[VECTOR][last30days] reddit connector failed: {}", exc)
        return build_brief(query, [], degraded_sources=["reddit"])


async def connect_github(query: str, language: str = "python", limit: int = 10) -> Last30DaysBrief:
    """Fetch GitHub trending repos and normalize into the last30days brief
    schema. Reuses ResearchHub.get_github_trending (public Search API, no auth)."""
    try:
        from districts.research.research_hub import ResearchHub

        repos = await ResearchHub().get_github_trending(language=language, limit=limit)
        signals = [
            RecentSignal(
                source="github",
                title=repo.get("name", ""),
                url=repo.get("url", ""),
                published_at=datetime.now(timezone.utc).isoformat(),
                engagement=float(repo.get("stars", 0)),
                confidence=0.75,
                notes=repo.get("description", ""),
            )
            for repo in repos
        ]
        return build_brief(query, signals)
    except Exception as exc:
        logger.warning("[VECTOR][last30days] github connector failed: {}", exc)
        return build_brief(query, [], degraded_sources=["github"])


async def connect_web_search(query: str, limit: int = 5) -> Last30DaysBrief:
    """General web search via WebScout — covers the doc's "web search"
    source. Reuses WebScout.search(), already free/no-API-key by default
    (DuckDuckGo fallback; Firecrawl/ParallelResearcher are optional
    upgrades on top, not required).
    """
    try:
        from districts.research.web_scout import WebScout

        results = await WebScout().search(query, max_results=limit)
        signals = [
            RecentSignal(
                source="web_search",
                title=r.get("title", ""),
                url=r.get("url", ""),
                published_at=datetime.now(timezone.utc).isoformat(),
                confidence=0.6,
                notes=(r.get("snippet") or "")[:200],
            )
            for r in results
        ]
        return build_brief(query, signals)
    except Exception as exc:
        logger.warning("[VECTOR][last30days] web_search connector failed: {}", exc)
        return build_brief(query, [], degraded_sources=["web_search"])


async def connect_all(query: str, limit: int = 10) -> Last30DaysBrief:
    """Fan out to all connectors and merge into one combined brief — the
    doc's own "source fanout" idea. A single connector's failure only adds
    its name to degraded_sources, it never takes down the whole brief.
    """
    briefs = [
        await connect_hackernews(query, limit=limit),
        await connect_reddit(query, limit=limit),
        await connect_github(query, limit=limit),
        await connect_web_search(query, limit=min(limit, 5)),
    ]
    signals: list[RecentSignal] = []
    degraded: list[str] = []
    for brief in briefs:
        signals.extend(brief.signals)
        degraded.extend(brief.degraded_sources)
    return build_brief(query, signals, degraded_sources=degraded)
