"""
VECTOR Content Analytics Retriever — inspired by Postiz's post analytics pipeline.

After publishing a post (YouTube, Instagram), fetches real performance metrics:
views, likes, comments, shares, watch_time, impressions, reach.

Closes the feedback loop: publish → track → optimize future content.
Used by the content district's nightly reflection cycle.

Usage:
    retriever = AnalyticsRetriever()
    metrics = retriever.get_youtube_metrics("dQw4w9WgXcQ")
    metrics = retriever.get_instagram_metrics("17854360229135492")
    batch = retriever.get_batch_metrics([
        PostRef(platform="youtube", post_id="dQw4w9WgXcQ"),
        PostRef(platform="instagram", post_id="17854360229135492"),
    ])
"""

from __future__ import annotations

__all__ = ["AnalyticsRetriever", "PostMetrics", "PostRef"]

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

@dataclass
class PostRef:
    platform: str   # "youtube" | "instagram" | "tiktok" | "linkedin"
    post_id: str
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class PostMetrics:
    platform: str
    post_id: str
    fetched_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0
    reach: int = 0
    watch_time_minutes: float = 0.0
    engagement_rate: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "post_id": self.post_id,
            "fetched_at": self.fetched_at,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "impressions": self.impressions,
            "reach": self.reach,
            "watch_time_minutes": self.watch_time_minutes,
            "engagement_rate": self.engagement_rate,
            "error": self.error,
        }

class AnalyticsRetriever:
    """
    Fetches post-publish performance metrics from YouTube and Instagram APIs.
    All methods degrade gracefully when credentials are unavailable.
    """

    def __init__(self) -> None:
        self._cfg = CONFIG.get("api_keys", {})
        self._yt_creds_path = self._cfg.get("google_credentials_path", "")
        self._ig_token = self._cfg.get("instagram_access_token",
                                       CONFIG.get("instagram", {}).get("access_token", ""))
        self._ig_user_id = self._cfg.get("instagram_user_id",
                                         CONFIG.get("instagram", {}).get("user_id", ""))

    # ── YouTube Analytics ──────────────────────────────────────────────────────

    def get_youtube_metrics(self, video_id: str) -> PostMetrics:
        """
        Fetch YouTube video analytics via YouTube Data API v3 + Analytics API.
        Requires google-api-python-client + valid credentials JSON.
        """
        base = PostMetrics(platform="youtube", post_id=video_id)
        if not self._yt_creds_path or not Path(self._yt_creds_path).exists():
            base.error = "google_credentials_path not configured"
            logger.debug("[VECTOR][analytics] YouTube creds not found, returning empty metrics")
            return base
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(self._yt_creds_path)
            youtube = build("youtube", "v3", credentials=creds)

            resp = youtube.videos().list(
                part="statistics,contentDetails",
                id=video_id,
            ).execute()

            items = resp.get("items", [])
            if not items:
                base.error = f"Video {video_id} not found"
                return base

            stats = items[0].get("statistics", {})
            details = items[0].get("contentDetails", {})

            base.views = int(stats.get("viewCount", 0))
            base.likes = int(stats.get("likeCount", 0))
            base.comments = int(stats.get("commentCount", 0))
            base.raw = {"statistics": stats, "contentDetails": details}

            # Engagement rate = (likes + comments) / views * 100
            if base.views:
                base.engagement_rate = round(
                    (base.likes + base.comments) / base.views * 100, 2
                )

            # Fetch watch time via YouTube Analytics API
            try:
                ya = build("youtubeAnalytics", "v2", credentials=creds)
                today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
                ar = ya.reports().query(
                    ids="channel==MINE",
                    startDate="2020-01-01",
                    endDate=today,
                    metrics="estimatedMinutesWatched",
                    filters=f"video=={video_id}",
                ).execute()
                rows = ar.get("rows", [])
                if rows:
                    base.watch_time_minutes = float(rows[0][0])
            except Exception as e:
                logger.debug("[VECTOR][analytics] watch_time fetch failed: {}", e)

            logger.info("[VECTOR][analytics] YouTube {} — {} views, {} likes",
                        video_id, base.views, base.likes)
            return base

        except Exception as e:
            base.error = str(e)
            logger.warning("[VECTOR][analytics] YouTube fetch failed for {}: {}", video_id, e)
            return base

    # ── Instagram Insights ─────────────────────────────────────────────────────

    def get_instagram_metrics(self, media_id: str) -> PostMetrics:
        """
        Fetch Instagram post insights via Graph API.
        Requires INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_USER_ID (Business/Creator account).
        """
        base = PostMetrics(platform="instagram", post_id=media_id)
        if not self._ig_token:
            base.error = "instagram_access_token not configured"
            logger.debug("[VECTOR][analytics] Instagram token not found, returning empty metrics")
            return base
        if not _HTTPX_AVAILABLE:
            base.error = "httpx not installed"
            return base
        try:
            # Fetch basic media stats
            url = f"https://graph.facebook.com/v21.0/{media_id}/insights"
            params = {
                "metric": "impressions,reach,likes,comments,shares,saved",
                "access_token": self._ig_token,
            }
            resp = httpx.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                base.error = f"API returned {resp.status_code}: {resp.text[:100]}"
                return base

            data = resp.json().get("data", [])
            metrics_map = {item["name"]: item.get("values", [{}])[-1].get("value", 0)
                           for item in data}

            base.impressions = int(metrics_map.get("impressions", 0))
            base.reach = int(metrics_map.get("reach", 0))
            base.likes = int(metrics_map.get("likes", 0))
            base.comments = int(metrics_map.get("comments", 0))
            base.shares = int(metrics_map.get("shares", 0))
            base.raw = metrics_map

            if base.reach:
                base.engagement_rate = round(
                    (base.likes + base.comments + base.shares) / base.reach * 100, 2
                )

            logger.info("[VECTOR][analytics] Instagram {} — {} reach, {} likes",
                        media_id, base.reach, base.likes)
            return base

        except Exception as e:
            base.error = str(e)
            logger.warning("[VECTOR][analytics] Instagram fetch failed for {}: {}", media_id, e)
            return base

    # ── Batch retrieval ────────────────────────────────────────────────────────

    def get_batch_metrics(self, posts: list[PostRef]) -> list[PostMetrics]:
        """Fetch metrics for a batch of posts across platforms."""
        results: list[PostMetrics] = []
        for post in posts:
            p = post.platform.lower()
            if p == "youtube":
                results.append(self.get_youtube_metrics(post.post_id))
            elif p in ("instagram", "ig"):
                results.append(self.get_instagram_metrics(post.post_id))
            else:
                results.append(PostMetrics(
                    platform=p,
                    post_id=post.post_id,
                    error=f"Platform {p} analytics not yet implemented",
                ))
        logger.info("[VECTOR][analytics] batch complete — {}/{} platforms supported",
                    sum(1 for r in results if not r.error.startswith("Platform")), len(results))
        return results

    def summary(self, metrics_list: list[PostMetrics]) -> dict[str, Any]:
        """Aggregate summary across a batch of PostMetrics."""
        successful = [m for m in metrics_list if not m.error]
        return {
            "total_posts": len(metrics_list),
            "successful": len(successful),
            "failed": len(metrics_list) - len(successful),
            "total_views": sum(m.views for m in successful),
            "total_likes": sum(m.likes for m in successful),
            "total_comments": sum(m.comments for m in successful),
            "total_shares": sum(m.shares for m in successful),
            "avg_engagement_rate": (
                sum(m.engagement_rate for m in successful) / len(successful)
                if successful else 0.0
            ),
            "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
        }

if __name__ == "__main__":
    r = AnalyticsRetriever()
    # No creds → graceful empty metrics (no crash)
    m = r.get_youtube_metrics("dQw4w9WgXcQ")
    assert m.platform == "youtube"
    assert m.error != "" or m.views >= 0
    m2 = r.get_instagram_metrics("17854360229135492")
    assert m2.platform == "instagram"
    batch = r.get_batch_metrics([
        PostRef("youtube", "vid1"),
        PostRef("instagram", "post1"),
        PostRef("tiktok", "tok1"),
    ])
    assert len(batch) == 3
    s = r.summary(batch)
    assert "total_posts" in s and s["total_posts"] == 3
    print("OK analytics_retriever.py — graceful degradation verified")
