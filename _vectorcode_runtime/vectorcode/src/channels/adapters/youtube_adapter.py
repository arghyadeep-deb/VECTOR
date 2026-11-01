"""VECTOR YouTube Channel Adapter — search, comments, video info via YouTube Data API."""
from __future__ import annotations
from loguru import logger

class YouTubeAdapter:
    """
    YouTube adapter for VECTOR.
    Env: YOUTUBE_API_KEY, YOUTUBE_ACCESS_TOKEN
    """
    _BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        import os
        self.api_key = os.environ.get("YOUTUBE_API_KEY","")
        self.token = os.environ.get("YOUTUBE_ACCESS_TOKEN","")

    async def search(self, query: str, max_results: int = 10) -> list[dict]:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self._BASE}/search", params={
                "key": self.api_key, "q": query, "part": "snippet",
                "type": "video", "maxResults": max_results,
            })
            r.raise_for_status()
            items = r.json().get("items", [])
            return [{"title": i["snippet"]["title"],
                     "video_id": i["id"]["videoId"],
                     "url": f"https://youtube.com/watch?v={i['id']['videoId']}",
                     "channel": i["snippet"]["channelTitle"]}
                    for i in items]

    async def get_video_info(self, video_id: str) -> dict:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self._BASE}/videos", params={
                "key": self.api_key, "id": video_id,
                "part": "snippet,statistics,contentDetails",
            })
            r.raise_for_status()
            items = r.json().get("items", [])
            return items[0] if items else {}

    async def post_comment(self, video_id: str, comment: str) -> dict:
        import httpx
        payload = {
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {"snippet": {"textOriginal": comment[:10000]}}
            }
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._BASE}/commentThreads?part=snippet",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}",
                         "Content-Type": "application/json"},
            )
            r.raise_for_status()
            logger.info("[VECTOR][youtube] commented on {}", video_id)
            return r.json()

    async def get_channel_stats(self, channel_id: str) -> dict:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self._BASE}/channels", params={
                "key": self.api_key, "id": channel_id,
                "part": "snippet,statistics",
            })
            r.raise_for_status()
            items = r.json().get("items", [])
            return items[0] if items else {}
