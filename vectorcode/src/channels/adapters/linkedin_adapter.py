"""VECTOR LinkedIn Channel Adapter — professional networking posts and DMs."""
from __future__ import annotations
from loguru import logger

class LinkedInAdapter:
    """
    LinkedIn adapter for VECTOR via official API.
    Requires: pip install requests
    Env: LINKEDIN_ACCESS_TOKEN
    Uses OAuth2 access token from core/engine/oauth/
    """
    _BASE = "https://api.linkedin.com/v2"

    def __init__(self):
        import os
        self.token = os.environ.get("LINKEDIN_ACCESS_TOKEN","")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    async def get_profile(self) -> dict:
        import asyncio, httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self._BASE}/me", headers=self._headers())
            r.raise_for_status()
            return r.json()

    async def post_text(self, text: str, visibility: str = "PUBLIC") -> dict:
        """Post a text update to LinkedIn feed."""
        import asyncio, httpx
        profile = await self.get_profile()
        urn = f"urn:li:person:{profile.get('id','')}"
        payload = {
            "author": urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text[:3000]},
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{self._BASE}/ugcPosts", json=payload, headers=self._headers())
            r.raise_for_status()
            logger.info("[VECTOR][linkedin] posted status={}", r.status_code)
            return r.json()

    async def get_feed(self, count: int = 20) -> list[dict]:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self._BASE}/shares?q=owners&owners=urn:li:person:me&count={count}",
                headers=self._headers()
            )
            r.raise_for_status()
            data = r.json()
            return data.get("elements", [])
