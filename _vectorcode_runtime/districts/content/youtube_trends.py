"""YouTube trending-topic harvest + competitor channel analysis.

Repo integration (docs/repo_analysis/youtube-automation-agent.md): VECTOR's
content district reads metrics for *its own* posts (analytics_retriever.py)
and gets trend OPINIONS from an LLM (agency/content_strategist.py), but had
no live read of what's trending on YouTube right now, or what a specific
competitor channel is actually doing. Both are real, missing data sources —
this module reuses the same googleapiclient import pattern and credential
seam already in districts/content/uploader.py, but via a read-only Data API
key (YOUTUBE_DATA_API_KEY) rather than the OAuth flow uploads need.

Reimplemented from the absorbed repo's *behavior* (chart=mostPopular pull,
search.list + videos.list competitor enumeration, view-weighted keyword
aggregation) — no JS copied, no hardcoded stop-word list ported verbatim.
"""
from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

# A fresh, minimal English stop-word set for keyword extraction from video
# titles — intentionally short; this is for surfacing salient nouns/phrases
# from trending titles, not a general-purpose NLP stop-word list.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to",
    "for", "with", "is", "are", "was", "were", "be", "this", "that",
    "it", "i", "you", "we", "my", "your", "how", "what", "why", "vs",
    "new", "best", "top", "2024", "2025", "2026", "video", "youtube",
})

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'-]{2,}")


def extract_keywords(titles: list[str], top_n: int = 20) -> list[tuple[str, int]]:
    """Tokenize a batch of video titles, drop stop-words, return the most
    common remaining words ranked by frequency. Pure function, no API calls."""
    counter: Counter = Counter()
    for title in titles:
        for word in _WORD_RE.findall(title.lower()):
            if word not in _STOPWORDS:
                counter[word] += 1
    return counter.most_common(top_n)


class YouTubeTrendScout(AgentBase):
    """Live YouTube trending + competitor-channel intelligence.

    Degrades to {"simulated": True} when YOUTUBE_DATA_API_KEY is unset,
    mirroring uploader.py's graceful-fallback pattern — never raises on
    missing credentials.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "YouTubeTrendScout", "content")
        self.capabilities = ["content", "trends", "youtube", "youtube_competitor", "youtube_trending"]
        if ghost:
            self.inherit_ghost(ghost)
        self._api_credentials = CONFIG.get("api_keys", {})
        logger.info("[VECTOR][youtube_trends] YouTubeTrendScout initialized")

    def _get_client(self):
        """Return a read-only googleapiclient YouTube resource, or None if
        no API key is configured or the dependency isn't installed."""
        api_key = self._api_credentials.get("youtube_data_api_key", "")
        if not api_key:
            return None
        try:
            from googleapiclient.discovery import build
            return build("youtube", "v3", developerKey=api_key)
        except ImportError:
            logger.warning("[VECTOR][youtube_trends] googleapiclient not installed")
            return None

    def fetch_trending(self, region: str = "US", max_results: int = 25, category_id: Optional[str] = None) -> dict:
        """Pull what's trending on YouTube right now (chart=mostPopular) for
        a region, and mine keywords from the trending titles.

        Returns {"status": "ok", "region": ..., "videos": [...], "top_keywords": [...]}
        or {"status": "simulated", ...} when no API key is configured.
        """
        client = self._get_client()
        if client is None:
            return {
                "status": "simulated",
                "region": region,
                "videos": [],
                "top_keywords": [],
                "note": "YOUTUBE_DATA_API_KEY not configured — set it to enable live trending data",
            }

        try:
            params = {
                "part": "snippet,statistics",
                "chart": "mostPopular",
                "regionCode": region,
                "maxResults": max_results,
            }
            if category_id:
                params["videoCategoryId"] = category_id
            response = client.videos().list(**params).execute()

            videos = []
            titles = []
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                title = snippet.get("title", "")
                titles.append(title)
                videos.append({
                    "video_id": item.get("id", ""),
                    "title": title,
                    "channel": snippet.get("channelTitle", ""),
                    "category_id": snippet.get("categoryId", ""),
                    "view_count": int(stats.get("viewCount", 0) or 0),
                    "like_count": int(stats.get("likeCount", 0) or 0),
                })

            top_keywords = extract_keywords(titles)
            self.award_points(15, f"trending_fetched_{region}")
            logger.info("[VECTOR][youtube_trends] fetched {} trending videos for {}", len(videos), region)
            return {
                "status": "ok",
                "region": region,
                "videos": videos,
                "top_keywords": top_keywords,
            }
        except Exception as e:
            logger.error("[VECTOR][youtube_trends] fetch_trending failed: {}", e)
            return {"status": "error", "error": str(e), "region": region}

    def analyze_competitor(self, channel_id: str, max_videos: int = 25) -> dict:
        """Enumerate a competitor channel's recent uploads and aggregate
        view-weighted topic keywords, upload frequency, and average views.

        Returns {"status": "ok", "channel_id": ..., "video_count": ...,
                 "avg_views": ..., "top_keywords": [...], "videos": [...]}
        or {"status": "simulated", ...} when no API key is configured.
        """
        client = self._get_client()
        if client is None:
            return {
                "status": "simulated",
                "channel_id": channel_id,
                "videos": [],
                "top_keywords": [],
                "note": "YOUTUBE_DATA_API_KEY not configured — set it to enable competitor analysis",
            }

        try:
            search_resp = client.search().list(
                part="id",
                channelId=channel_id,
                order="date",
                type="video",
                maxResults=max_videos,
            ).execute()
            video_ids = [
                item["id"]["videoId"]
                for item in search_resp.get("items", [])
                if item.get("id", {}).get("videoId")
            ]
            if not video_ids:
                return {"status": "ok", "channel_id": channel_id, "video_count": 0, "avg_views": 0, "top_keywords": [], "videos": []}

            videos_resp = client.videos().list(
                part="snippet,statistics",
                id=",".join(video_ids),
            ).execute()

            videos = []
            titles_weighted: list[str] = []
            total_views = 0
            for item in videos_resp.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                title = snippet.get("title", "")
                views = int(stats.get("viewCount", 0) or 0)
                total_views += views
                videos.append({
                    "video_id": item.get("id", ""),
                    "title": title,
                    "published_at": snippet.get("publishedAt", ""),
                    "view_count": views,
                })
                # View-weighted keyword aggregation: repeat higher-view
                # titles more times so their words dominate the count.
                weight = max(1, views // 10000)
                titles_weighted.extend([title] * min(weight, 10))

            avg_views = total_views // len(videos) if videos else 0
            top_keywords = extract_keywords(titles_weighted)

            self.award_points(15, f"competitor_analyzed_{channel_id[:12]}")
            logger.info("[VECTOR][youtube_trends] analyzed {} videos for competitor {}", len(videos), channel_id)
            return {
                "status": "ok",
                "channel_id": channel_id,
                "video_count": len(videos),
                "avg_views": avg_views,
                "top_keywords": top_keywords,
                "videos": videos,
            }
        except Exception as e:
            logger.error("[VECTOR][youtube_trends] analyze_competitor failed: {}", e)
            return {"status": "error", "error": str(e), "channel_id": channel_id}

    async def run(self, task: dict) -> dict:
        """Governor-dispatchable entrypoint — branches on task["type"]."""
        task_type = task.get("type", "")
        params = task.get("params", {}) or {}

        if task_type in ("youtube_trending", "fetch_trending"):
            return self.fetch_trending(
                region=params.get("region", "US"),
                max_results=params.get("max_results", 25),
                category_id=params.get("category_id"),
            )
        if task_type in ("youtube_competitor", "analyze_competitor"):
            channel_id = params.get("channel_id", "")
            if not channel_id:
                return {"status": "error", "error": "channel_id is required"}
            return self.analyze_competitor(channel_id, max_videos=params.get("max_videos", 25))

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": ["youtube_trending", "youtube_competitor"]}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    kws = extract_keywords([
        "Top 5 Python Tricks for Beginners 2026",
        "Python Tricks Every Developer Should Know",
        "5 Python Tips and Tricks Explained",
    ])
    assert ("python", 3) in kws or kws[0][0] == "python", kws
    print(f"[youtube_trends] extract_keywords OK: {kws[:5]}")

    scout = YouTubeTrendScout()
    result = scout.fetch_trending()
    assert result["status"] == "simulated"  # no API key configured in this env
    print(f"[youtube_trends] fetch_trending graceful fallback OK: {result['status']}")

    result2 = scout.analyze_competitor("UC_test_channel")
    assert result2["status"] == "simulated"
    print(f"[youtube_trends] analyze_competitor graceful fallback OK: {result2['status']}")

    print("✅ youtube_trends.py OK")
