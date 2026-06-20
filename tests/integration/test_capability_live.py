"""Live, credential/network-gated proofs for absorbed capabilities.

Per plans/wire-absorbed-repos-autonomy.md: "A capability is not done until
its live proof exists." These tests hit the real network/sandbox — they are
NOT mocked, and are marked `live` so CI can choose to skip them. When run,
each test's pass/fail is the actual evidence behind the verdict recorded in
docs/capability_proofs/<repo>.md.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.mark.live
def test_scraper_fetch_returns_real_content():
    """Regression test for the bug found in Phase 0: VectorScraper.fetch()
    returned status 200 with completely empty content/html because it read
    resp.text (always empty for scrapling's Response) instead of
    resp.html_content (has the real fetched markup)."""
    from core.scraper.vector_scraper import VectorScraper

    async def _run():
        scraper = VectorScraper()
        result = await scraper.fetch("https://example.com")
        return result

    result = asyncio.run(_run())
    assert result.status_code == 200
    assert result.error is None
    assert len(result.content) > 100, "content must be real fetched markup, not empty"
    assert "Example Domain" in result.content
    assert len(result.html) > 100
