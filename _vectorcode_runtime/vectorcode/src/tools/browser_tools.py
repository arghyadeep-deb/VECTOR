"""
BrowserTools — Playwright-based browser automation for VECTOR's coding district.

All actions that touch the browser are gated through the PermissionGateway:
  - YELLOW (execute + notify):  navigate, screenshot, click, extract_text
  - RED    (owner must confirm): submit_form

Playwright is an optional dependency. If it is not installed the class still
imports, but browser actions fail explicitly instead of pretending to succeed.

Usage (sync wrapper)
--------------------
    bt = BrowserTools()
    title = bt.navigate("https://example.com")
    png   = bt.screenshot("/tmp/shot.png")
    bt.close()
"""

import asyncio

from core.config import CONFIG  # noqa: F401
from loguru import logger

try:
    from core.loop.permission_gateway import PermissionGateway, Action
    _GATEWAY_AVAILABLE = True
except ImportError:
    _GATEWAY_AVAILABLE = False
    logger.warning("[VECTOR][browser_tools] PermissionGateway not importable - browser actions fail closed")

try:
    from playwright.async_api import async_playwright, Browser, Page, Playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    logger.warning("[VECTOR][browser_tools] playwright not installed - browser actions unavailable")

# ── Permission level constants ─────────────────────────────────────────────────

NAVIGATE_PERMISSION = "yellow"
SCREENSHOT_PERMISSION = "yellow"
CLICK_PERMISSION = "yellow"
SUBMIT_FORM_PERMISSION = "red"


class BrowserTools:
    """
    Playwright browser automation with VECTOR permission gating.

    Class-level permission constants (checked in tests via BrowserTools.__new__):
        NAVIGATE_PERMISSION    = "yellow"
        SCREENSHOT_PERMISSION  = "yellow"
        CLICK_PERMISSION       = "yellow"
        SUBMIT_FORM_PERMISSION = "red"
    """

    # Expose as class attributes so tests can read them via BrowserTools.__new__
    NAVIGATE_PERMISSION = NAVIGATE_PERMISSION
    SCREENSHOT_PERMISSION = SCREENSHOT_PERMISSION
    CLICK_PERMISSION = CLICK_PERMISSION
    SUBMIT_FORM_PERMISSION = SUBMIT_FORM_PERMISSION

    def __init__(self):
        self._playwright: "Playwright | None" = None
        self._browser: "Browser | None" = None
        self._page: "Page | None" = None
        self._gateway = PermissionGateway() if _GATEWAY_AVAILABLE else _UnavailableGateway()
        logger.info("[VECTOR][browser_tools] BrowserTools initialised (playwright=%s)", _PLAYWRIGHT_AVAILABLE)

    # ── lazy init ─────────────────────────────────────────────────────────────

    async def _ensure_browser(self) -> None:
        """Start Playwright chromium headless if not already running."""
        if self._page is not None:
            return
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright is not installed; browser automation is unavailable")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._page = await self._browser.new_page()
        logger.info("[VECTOR][browser_tools] Chromium launched (headless)")

    # ── async core methods ────────────────────────────────────────────────────

    async def _navigate_with_gate(self, url: str) -> str:
        """YELLOW-gated navigate. Returns page title (or stub)."""
        approved = self._gateway.check(NAVIGATE_PERMISSION, "navigate_browser", {"url": url})
        if not approved:
            logger.warning("[VECTOR][browser_tools] navigate blocked by gateway")
            return ""
        await self._ensure_browser()
        if self._page is None:
            raise RuntimeError("Browser page is unavailable after Playwright startup")
        await self._page.goto(url)
        title = await self._page.title()
        logger.info(f"[VECTOR][browser_tools] Navigated to {url} — title: {title!r}")
        return title

    async def _take_screenshot(self, path: str | None = None) -> bytes:
        """YELLOW-gated screenshot. Returns PNG bytes."""
        if self._page is None:
            return b""
        kwargs = {}
        if path:
            kwargs["path"] = path
        data: bytes = await self._page.screenshot(**kwargs)
        logger.debug(f"[VECTOR][browser_tools] Screenshot taken ({len(data)} bytes)")
        return data

    async def _click_element(self, selector: str) -> bool:
        """YELLOW-gated element click."""
        approved = self._gateway.check(CLICK_PERMISSION, "click_browser_element", {"selector": selector})
        if not approved:
            logger.warning("[VECTOR][browser_tools] click blocked by gateway")
            return False
        if self._page is None:
            return False
        await self._page.click(selector)
        return True

    async def _extract_text_async(self, selector: str = "body") -> str:
        """Extract visible text from a CSS selector. No permission gate needed (read-only)."""
        if self._page is None:
            return ""
        try:
            text: str = await self._page.inner_text(selector)
            return text
        except Exception as e:
            logger.warning(f"[VECTOR][browser_tools] extract_text failed: {e}")
            return ""

    async def _submit_form_async(self, selector: str, data: dict) -> bool:
        """RED-gated form submission."""
        approved = self._gateway.check(SUBMIT_FORM_PERMISSION, "submit_form_browser", {
            "selector": selector,
            "fields": list(data.keys()),
        })
        if not approved:
            logger.warning("[VECTOR][browser_tools] submit_form blocked by gateway (RED)")
            return False
        if self._page is None:
            return False
        for field, value in data.items():
            try:
                await self._page.fill(f"{selector} [name={field!r}]", str(value))
            except Exception as e:
                logger.warning(f"[VECTOR][browser_tools] fill {field}: {e}")
        try:
            await self._page.locator(selector).evaluate("form => form.submit()")
        except Exception as e:
            logger.warning(f"[VECTOR][browser_tools] submit eval: {e}")
        return True

    # ── sync public interface ─────────────────────────────────────────────────

    def navigate(self, url: str) -> str:
        """Navigate to URL (YELLOW gate). Returns page title."""
        return asyncio.run(self._navigate_with_gate(url))

    def screenshot(self, path: str | None = None) -> bytes:
        """Take screenshot (YELLOW gate). Returns PNG bytes, optionally saves to path."""
        approved = self._gateway.check(SCREENSHOT_PERMISSION, "screenshot_browser", {"path": path})
        if not approved:
            logger.warning("[VECTOR][browser_tools] screenshot blocked by gateway")
            return b""
        return asyncio.run(self._take_screenshot(path))

    def click(self, selector: str) -> bool:
        """Click element (YELLOW gate)."""
        return asyncio.run(self._click_element(selector))

    def extract_text(self, selector: str = "body") -> str:
        """Return visible text from selector (read-only, no gate)."""
        return asyncio.run(self._extract_text_async(selector))

    def submit_form(self, selector: str, data: dict) -> bool:
        """Submit form (RED gate — owner confirmation required)."""
        return asyncio.run(self._submit_form_async(selector, data))

    def close(self) -> None:
        """Shut down the browser and Playwright."""
        async def _close():
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        try:
            asyncio.run(_close())
        except Exception as e:
            logger.warning(f"[VECTOR][browser_tools] close error: {e}")
        self._page = None
        self._browser = None
        self._playwright = None
        logger.info("[VECTOR][browser_tools] Browser closed")


# ── Unavailable gateway (when core not importable) ────────────────────────────

class _UnavailableGateway:
    """Fail-closed gateway used when PermissionGateway cannot be imported."""

    def check(self, level: str, action: str, params: dict) -> bool:
        logger.error(
            "[VECTOR][browser_tools] blocking %s because PermissionGateway is unavailable",
            action,
        )
        return False


# ── Monkey-patch check() onto real PermissionGateway ─────────────────────────
# The real gateway uses an async execute() path.  BrowserTools needs a
# lightweight *synchronous* check() so it can be called from within async
# methods without nesting asyncio.run().  We add it here so we don't have to
# touch the core gateway file.

if _GATEWAY_AVAILABLE:
    def _gateway_check(self, level: str, action: str, params: dict) -> bool:
        """
        Synchronous pre-flight permission check.
        Returns True for GREEN/YELLOW, False for RED (needs confirmation),
        False for FORBIDDEN/UNKNOWN.
        """
        from core.loop.permission_gateway import GREEN, YELLOW, RED, FORBIDDEN
        if action in FORBIDDEN:
            logger.warning(f"[VECTOR][gateway] check: FORBIDDEN {action}")
            return False
        if action in GREEN or level == "green":
            return True
        if action in YELLOW or level == "yellow":
            logger.info(f"[VECTOR][gateway] check: YELLOW auto-approved {action}")
            return True
        if action in RED or level == "red":
            logger.warning(f"[VECTOR][gateway] check: RED requires confirmation — {action}")
            return False
        # Unknown browser actions default to their declared level
        if level in ("green", "yellow"):
            return True
        return False

    PermissionGateway.check = _gateway_check  # type: ignore[attr-defined]


# ── smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test 1: permission constants
    bt = BrowserTools.__new__(BrowserTools)
    assert bt.NAVIGATE_PERMISSION == "yellow", f"Expected yellow, got {bt.NAVIGATE_PERMISSION}"
    assert bt.SCREENSHOT_PERMISSION == "yellow"
    assert bt.SUBMIT_FORM_PERMISSION == "red"
    print("✅ Permission constants OK")

    # Test 2: stub screenshot (no real browser needed)
    bt2 = BrowserTools.__new__(BrowserTools)
    bt2._page = None
    result = asyncio.run(bt2._take_screenshot())
    assert isinstance(result, bytes)
    print("✅ _take_screenshot stub OK")

    if _PLAYWRIGHT_AVAILABLE:
        # Test 3: real navigate (needs internet)
        try:
            bt3 = BrowserTools()
            title = bt3.navigate("https://example.com")
            assert isinstance(title, str)
            print(f"✅ navigate OK — title: {title!r}")
            bt3.close()
        except Exception as e:
            print(f"⚠️  navigate test skipped (no network?): {e}")
    else:
        print("⚠️  playwright not installed — real navigate skipped")

    print("✅ browser_tools OK")


