"""Regression tests for the Phase 3 whole-repo audit's core/browser/ misc slice
(2026-10-01): PlaywrightMCPClient.navigate() had no SSRF check at all, unlike
its sibling core/browser/page_extract.py which enforces one on every fetch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.browser.playwright_mcp_client import PlaywrightMCPClient


@pytest.mark.asyncio
async def test_navigate_blocks_private_address():
    client = PlaywrightMCPClient()
    with pytest.raises(ValueError, match="SSRF guard"):
        await client.navigate("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
async def test_navigate_blocks_localhost():
    client = PlaywrightMCPClient()
    with pytest.raises(ValueError, match="SSRF guard"):
        await client.navigate("http://127.0.0.1:8080/admin")


@pytest.mark.asyncio
async def test_navigate_allows_public_url_through_to_call_tool(monkeypatch):
    client = PlaywrightMCPClient()
    calls = []

    async def fake_is_available(self):
        return True

    async def fake_call_tool(self, tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        return {"ok": True}

    monkeypatch.setattr(PlaywrightMCPClient, "is_available", fake_is_available)
    monkeypatch.setattr(PlaywrightMCPClient, "call_tool", fake_call_tool)

    await client.navigate("https://example.com/page")
    assert calls == [("browser_navigate", {"url": "https://example.com/page"})]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
