"""
Playwright MCP Client — async bridge to the playwright-mcp sidecar.
Run sidecar: npx @playwright/mcp@latest --headless --port 8931
"""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import asyncio
import json
import httpx
from core.config import CONFIG

PLAYWRIGHT_MCP_URL = "http://127.0.0.1:8931"


class PlaywrightMCPClient:
    """Async client for playwright-mcp sidecar (62 browser tools)."""

    def __init__(self, base_url: str = PLAYWRIGHT_MCP_URL):
        self._base_url = base_url
        self._available: bool | None = None

    async def is_available(self) -> bool:
        """Check if playwright-mcp sidecar is running."""
        if self._available is not None:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r = await client.get(f"{self._base_url}/")
                self._available = r.status_code < 500
        except Exception:
            self._available = False
        return self._available

    async def call_tool(self, tool_name: str, **kwargs) -> dict:
        """Call any playwright-mcp tool by name."""
        if not await self.is_available():
            raise RuntimeError(
                "playwright-mcp sidecar not running. "
                "Start with: npx @playwright/mcp@latest --headless --port 8931"
            )
        async with httpx.AsyncClient(timeout=30) as client:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": kwargs},
                "id": 1,
            }
            r = await client.post(f"{self._base_url}/", json=payload)
            result = r.json()
            if "error" in result:
                raise RuntimeError(f"playwright-mcp error: {result['error']}")
            return result.get("result", {})

    async def navigate(self, url: str) -> dict:
        """Navigate the sidecar's real browser to `url`.

        core/browser/page_extract.py (same package) enforces an SSRF check on
        every fetch; this client had none, and its only real caller
        (districts/research/web_scout.py) checks is_safe_url() on its other
        fetch paths but not this one -- a search-result URL could point to a
        private/metadata address and this would navigate a real browser
        there ungated. Checked here so every caller is covered, not just the
        one that happened to remember.
        """
        from core.security.ssrf_guard import is_safe_url

        if not is_safe_url(url):
            raise ValueError(f"navigate blocked by SSRF guard: {url!r}")
        return await self.call_tool("browser_navigate", url=url)

    async def snapshot(self) -> str:
        result = await self.call_tool("browser_snapshot")
        return str(result)

    async def click(self, element: str) -> dict:
        return await self.call_tool("browser_click", element=element)

    async def screenshot(self) -> bytes | None:
        result = await self.call_tool("browser_take_screenshot")
        img = result.get("content", [{}])[0] if result else {}
        data = img.get("data", "")
        if data:
            import base64
            return base64.b64decode(data)
        return None

    async def scrape_page(self, url: str) -> str:
        """Navigate to URL and return accessibility snapshot (structured content)."""
        await self.navigate(url)
        return await self.snapshot()


if __name__ == "__main__":
    async def test():
        client = PlaywrightMCPClient()
        available = await client.is_available()
        print(f"playwright-mcp available: {available}")
        print("✅ playwright_mcp_client OK")
    asyncio.run(test())
