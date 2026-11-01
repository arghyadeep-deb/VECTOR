"""VECTOR Bluesky Channel Adapter — AT Protocol decentralized social."""
from __future__ import annotations
from loguru import logger

class BlueskyAdapter:
    """
    Bluesky (AT Protocol) adapter for VECTOR.
    Requires: pip install atproto
    Env: BLUESKY_HANDLE, BLUESKY_PASSWORD
    """
    def __init__(self):
        import os
        self.handle = os.environ.get("BLUESKY_HANDLE","")
        self.password = os.environ.get("BLUESKY_PASSWORD","")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from atproto import Client
                c = Client()
                c.login(self.handle, self.password)
                self._client = c
            except ImportError:
                raise ImportError("Run: pip install atproto")
        return self._client

    async def post(self, text: str) -> dict:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._get_client().send_post(text=text[:300]))
        logger.info("[VECTOR][bluesky] posted: {}", text[:50])
        return {"uri": result.uri, "cid": result.cid}

    async def get_timeline(self, limit: int = 20) -> list[dict]:
        import asyncio
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, lambda: self._get_client().get_timeline(limit=limit))
        return [{"text": p.post.record.text, "author": p.post.author.handle}
                for p in feed.feed]

    async def search_posts(self, query: str, limit: int = 20) -> list[dict]:
        import asyncio
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: self._get_client().app.bsky.feed.search_posts({"q":query,"limit":limit}))
        return [{"text": p.record.text, "author": p.author.handle} for p in results.posts]
