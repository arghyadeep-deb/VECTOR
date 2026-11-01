"""
VECTOR Stealth Browser Client
Python HTTP client for the anti-detection stealth browser server.

Wraps all REST endpoints of the Node.js server in async Python methods.
The server runs as a subprocess managed by server_manager.py.

Usage:
    async with StealthBrowserClient() as client:
        await client.ensure_server()
        content = await client.scrape_page("https://linkedin.com/in/someone")
        logger.info(content["snapshot"])


    # Or search with anti-detection:
        result = await client.search("AI startups 2026", engine="google")
"""
from __future__ import annotations

import asyncio
import base64
import sys
from typing import Optional

import httpx

from core.config import CONFIG
from core.stealth_browser.macros import macro_url
from loguru import logger

_DEFAULT_PORT    = 9377
_DEFAULT_TIMEOUT = 30.0
_USER_AGENT      = "VECTOR/1.0"


class StealthBrowserClient:
    """
    Python client for VECTOR's anti-detection browser server.
    Handles tab lifecycle, navigation, snapshots, and search.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        cfg = CONFIG.get("stealth_browser", {})
        port = cfg.get("port", _DEFAULT_PORT)
        self._base = (base_url or f"http://127.0.0.1:{port}").rstrip("/")
        self._api_key = api_key or cfg.get("api_key", "")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "User-Agent": _USER_AGENT}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    # â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def is_healthy(self) -> bool:
        try:
            c = await self._ensure_client()
            r = await c.get(f"{self._base}/health", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    async def ensure_server(self) -> bool:
        """Start the server if not already running."""
        if await self.is_healthy():
            return True
        from core.stealth_browser.server_manager import StealthBrowserServer
        return await StealthBrowserServer().ensure_running()

    # â”€â”€ Tab lifecycle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def create_tab(
        self,
        url: str = "about:blank",
        user_id: str = "vector",
        group_id: str | None = None,
    ) -> dict:
        """Create a new browser tab. Returns {tabId, url, ...}."""
        c = await self._ensure_client()
        body: dict = {"url": url, "userId": user_id}
        if group_id:
            body["groupId"] = group_id
        r = await c.post(f"{self._base}/tabs", json=body, headers=self._headers())
        r.raise_for_status()
        return r.json()

    async def list_tabs(self, user_id: str = "vector") -> list[dict]:
        c = await self._ensure_client()
        r = await c.get(f"{self._base}/tabs", params={"userId": user_id}, headers=self._headers())
        r.raise_for_status()
        return r.json()

    async def close_tab(self, tab_id: str) -> None:
        c = await self._ensure_client()
        r = await c.delete(f"{self._base}/tabs/{tab_id}", headers=self._headers())
        r.raise_for_status()

    async def close_all_tabs(self, user_id: str = "vector") -> None:
        c = await self._ensure_client()
        r = await c.delete(f"{self._base}/sessions/{user_id}", headers=self._headers())
        r.raise_for_status()

    # â”€â”€ Navigation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def navigate(self, tab_id: str, url: str) -> dict:
        """Navigate to URL or server macro (e.g. @google_search:AI news)."""
        c = await self._ensure_client()
        r = await c.post(
            f"{self._base}/tabs/{tab_id}/navigate",
            json={"url": url},
            headers=self._headers(),
            timeout=self._timeout,
        )
        r.raise_for_status()
        return r.json()

    async def go_back(self, tab_id: str) -> dict:
        c = await self._ensure_client()
        r = await c.post(f"{self._base}/tabs/{tab_id}/back", headers=self._headers())
        r.raise_for_status()
        return r.json()

    async def go_forward(self, tab_id: str) -> dict:
        c = await self._ensure_client()
        r = await c.post(f"{self._base}/tabs/{tab_id}/forward", headers=self._headers())
        r.raise_for_status()
        return r.json()

    async def refresh(self, tab_id: str) -> dict:
        c = await self._ensure_client()
        r = await c.post(f"{self._base}/tabs/{tab_id}/refresh", headers=self._headers())
        r.raise_for_status()
        return r.json()

    # â”€â”€ Content â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def snapshot(self, tab_id: str, offset: int = 0) -> str:
        """
        Get token-efficient accessibility tree snapshot.
        Returns YAML text with stable element refs (e1, e2, ...).
        ~100 tokens vs ~1000 tokens for raw HTML.
        """
        c = await self._ensure_client()
        params = {"offset": offset} if offset else {}
        r = await c.get(
            f"{self._base}/tabs/{tab_id}/snapshot",
            params=params,
            headers=self._headers(),
            timeout=self._timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("snapshot") or data.get("content") or str(data)

    async def get_links(self, tab_id: str) -> list[dict]:
        """Get all links on current page as [{text, href}, ...]."""
        c = await self._ensure_client()
        r = await c.get(f"{self._base}/tabs/{tab_id}/links", headers=self._headers())
        r.raise_for_status()
        return r.json()

    async def get_images(self, tab_id: str, inline: bool = False) -> list[dict]:
        c = await self._ensure_client()
        r = await c.get(
            f"{self._base}/tabs/{tab_id}/images",
            params={"inline": "true" if inline else "false"},
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    async def screenshot(self, tab_id: str) -> bytes:
        """Take a PNG screenshot of the current page."""
        c = await self._ensure_client()
        r = await c.get(f"{self._base}/tabs/{tab_id}/screenshot", headers=self._headers())
        r.raise_for_status()
        data = r.json()
        b64 = data.get("screenshot") or data.get("data") or ""
        return base64.b64decode(b64) if b64 else b""

    # â”€â”€ Interaction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def click(
        self,
        tab_id: str,
        ref: str | None = None,
        selector: str | None = None,
    ) -> dict:
        """Click an element by ref (e1, e2) or CSS selector."""
        c = await self._ensure_client()
        body: dict = {}
        if ref:
            body["ref"] = ref
        if selector:
            body["selector"] = selector
        r = await c.post(f"{self._base}/tabs/{tab_id}/click", json=body, headers=self._headers())
        r.raise_for_status()
        return r.json()

    async def type_text(self, tab_id: str, text: str, ref: str | None = None) -> dict:
        """Type text into focused element or element by ref."""
        c = await self._ensure_client()
        body: dict = {"text": text}
        if ref:
            body["ref"] = ref
        r = await c.post(f"{self._base}/tabs/{tab_id}/type", json=body, headers=self._headers())
        r.raise_for_status()
        return r.json()

    async def press_key(self, tab_id: str, key: str) -> dict:
        """Press a keyboard key (Enter, Tab, Escape, etc.)."""
        c = await self._ensure_client()
        r = await c.post(
            f"{self._base}/tabs/{tab_id}/press",
            json={"key": key},
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    async def scroll(self, tab_id: str, direction: str = "down", amount: int = 3) -> dict:
        c = await self._ensure_client()
        r = await c.post(
            f"{self._base}/tabs/{tab_id}/scroll",
            json={"direction": direction, "amount": amount},
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    async def wait(self, tab_id: str, selector: str | None = None, ms: int = 1000) -> dict:
        c = await self._ensure_client()
        body: dict = {"ms": ms}
        if selector:
            body["selector"] = selector
        r = await c.post(f"{self._base}/tabs/{tab_id}/wait", json=body, headers=self._headers())
        r.raise_for_status()
        return r.json()

    # â”€â”€ YouTube â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def youtube_transcript(self, url: str) -> dict:
        """Extract YouTube transcript via yt-dlp + browser fallback."""
        c = await self._ensure_client()
        r = await c.post(
            f"{self._base}/youtube/transcript",
            json={"url": url},
            headers=self._headers(),
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()

    # â”€â”€ High-level helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def scrape_page(
        self,
        url: str,
        user_id: str = "vector",
        wait_ms: int = 1500,
        close_after: bool = True,
    ) -> dict:
        """
        Full scrape cycle: create tab → navigate → wait → snapshot → links → close.
        Returns {url, snapshot, links, tab_id}.
        """
        tab = await self.create_tab("about:blank", user_id=user_id)
        tab_id = tab.get("tabId") or tab.get("id") or tab.get("tab_id", "")
        try:
            await self.navigate(tab_id, url)
            if wait_ms:
                await asyncio.sleep(wait_ms / 1000)
            snap = await self.snapshot(tab_id)
            links = await self.get_links(tab_id)
            logger.info("[VECTOR][stealth] scraped {} — snapshot={} chars links={}", url[:60], len(snap), len(links))
            return {"url": url, "snapshot": snap, "links": links, "tab_id": tab_id}
        finally:
            if close_after and tab_id:
                try:
                    await self.close_tab(tab_id)
                except Exception as e:
                    logger.warning("[VECTOR][stealth] failed to close tab {}: {}", tab_id, e)

    async def search(
        self,
        query: str,
        engine: str = "google",
        user_id: str = "vector",
        wait_ms: int = 2000,
    ) -> dict:
        """
        Search using a macro engine with anti-detection.
        Returns {query, engine, snapshot, links}.
        """
        url = macro_url(engine, query, use_server_macro=True)
        result = await self.scrape_page(url, user_id=user_id, wait_ms=wait_ms)
        result["query"]  = query
        result["engine"] = engine
        return result


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        client = StealthBrowserClient()
        healthy = await client.is_healthy()
        await client.close()
        print(f"OK client.py — base_url={client._base}")
        print(f"  server healthy: {healthy}")
        if not healthy:
            print(f"  (start server: cd core/stealth_browser/server && node server.js)")

    asyncio.run(_smoke())
