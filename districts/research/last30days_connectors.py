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

from loguru import logger

from districts.research.last30days import Last30DaysBrief, RecentSignal, build_brief

__all__ = ["connect_hackernews"]


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
                published_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
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
