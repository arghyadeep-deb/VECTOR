"""VECTOR Mastodon Channel Adapter — federated microblogging."""
from __future__ import annotations
from loguru import logger

class MastodonAdapter:
    """
    Mastodon channel adapter for VECTOR.
    Requires: pip install Mastodon.py
    Env: MASTODON_ACCESS_TOKEN, MASTODON_API_BASE_URL
    """
    def __init__(self):
        import os
        self.token = os.environ.get("MASTODON_ACCESS_TOKEN","")
        self.base_url = os.environ.get("MASTODON_API_BASE_URL","https://mastodon.social")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from mastodon import Mastodon
                self._client = Mastodon(access_token=self.token, api_base_url=self.base_url)
            except ImportError:
                raise ImportError("Run: pip install Mastodon.py")
        return self._client

    async def post(self, content: str, visibility: str = "public") -> dict:
        import asyncio
        loop = asyncio.get_event_loop()
        def _post():
            return self._get_client().status_post(content[:500], visibility=visibility)
        result = await loop.run_in_executor(None, _post)
        logger.info("[VECTOR][mastodon] posted toot id={}", result.get("id"))
        return dict(result)

    async def timeline(self, limit: int = 20) -> list[dict]:
        import asyncio
        loop = asyncio.get_event_loop()
        statuses = await loop.run_in_executor(None, lambda: self._get_client().timeline_home(limit=limit))
        return [{"id": s["id"], "content": s["content"], "author": s["account"]["username"]} for s in statuses]

    async def search(self, query: str) -> list[dict]:
        import asyncio
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: self._get_client().search(query))
        return [{"id": s["id"], "content": s["content"]} for s in results.get("statuses", [])]
