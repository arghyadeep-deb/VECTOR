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


@pytest.mark.live
def test_research_engine_full_cycle_produces_real_statistics():
    """Regression test for two bugs found in Phase 0:
    (1) EpisodicMemory.search() doesn't exist (real method is .recall());
    (2) the sandboxed default experiment used logger.info("STAT:...") for
    output, but the sandbox's restricted __builtins__ never defines `logger`
    and SandboxExecutor._extract_stats() only ever reads stdout — so every
    experiment raised NameError and silently produced 0 data points."""
    from core.research_engine.auto_research_agent import AutoResearchAgent

    agent = AutoResearchAgent()
    report = agent.run_full_cycle("test")

    assert report.experiment is not None
    assert report.analysis is not None
    # Real computed stats, not "Insufficient data points (0)".
    stats = report.analysis.statistical_tests
    assert stats, "experiment must produce at least one statistical test result"
    assert "p_value" in stats[0]
