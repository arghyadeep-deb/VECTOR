"""Browser automation tool — Playwright-based web interaction."""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT = True
except ImportError:
    _PLAYWRIGHT = False


class BrowserTool:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self._browser = None
        self._context = None
        self._page = None

    async def start(self):
        if not _PLAYWRIGHT:
            logger.warning("playwright not installed. Run: pip install playwright && playwright install")
            return
        p = await async_playwright().start()
        self._browser = await p.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

    async def navigate(self, url: str) -> str:
        if not self._page: return "Browser not started"
        await self._page.goto(url, wait_until="networkidle")
        return await self._page.title()

    async def screenshot(self, path: Optional[str] = None) -> str:
        if not self._page: return "Browser not started"
        path = path or "/tmp/vector_screenshot.png"
        await self._page.screenshot(path=path, full_page=True)
        return path

    async def get_text(self) -> str:
        if not self._page: return ""
        return await self._page.inner_text("body")

    async def click(self, selector: str):
        if self._page: await self._page.click(selector)

    async def fill(self, selector: str, value: str):
        if self._page: await self._page.fill(selector, value)

    async def evaluate(self, js: str) -> str:
        if not self._page: return ""
        result = await self._page.evaluate(js)
        return str(result)

    async def close(self):
        if self._browser: await self._browser.close()
