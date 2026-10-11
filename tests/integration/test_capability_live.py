"""Live, credential/network-gated proofs for absorbed capabilities.

Per plans/wire-absorbed-repos-autonomy.md: "A capability is not done until
its live proof exists." These tests hit the real network/sandbox — they are
NOT mocked, and are marked `live` so CI can choose to skip them. When run,
each test's pass/fail is the actual evidence behind the verdict recorded in
docs/capability_proofs/<repo>.md.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import pathlib
import re

import pytest

live_only = pytest.mark.skipif(
    os.environ.get("VECTOR_LIVE_TESTS") != "1",
    reason="Live network/model proofs require VECTOR_LIVE_TESTS=1 and owner-provided services",
)


def test_no_foreign_user_agent():
    """core/research_engine/ was absorbed from "local-deep-research" and
    rebranded, but provenance strings survived in several User-Agent
    headers (and one dead Reddit link) — meaning VECTOR's research hands
    announce the original third-party project name to GitHub/NASA
    ADS/OpenAlex/Zenodo/etc. on every live web request. This must be
    caught before the researcher/collector hands are scheduled to run
    autonomously (plans/wire-absorbed-repos-autonomy.md Task 2.0).

    Catches ALL casing/separator variants, not just the literal
    "Local-Deep-Research" hyphenated form — the first audit pass missed
    several hits (e.g. "LocalDeepResearch" PascalCase with no hyphen,
    used as a literal User-Agent value in 6 search engine files) by only
    grepping one casing style.
    """
    root = pathlib.Path("core/research_engine")
    pattern = re.compile(r"local[-_ ]?deep[-_ ]?research", re.IGNORECASE)
    bad = [
        p
        for p in root.rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not bad, f"foreign provenance strings survive in: {bad}"


@pytest.mark.live
@live_only
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
@live_only
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
    # "LIVE" must mean the LLM actually designed this experiment, not that
    # it silently fell back to the static rule-based template forever.
    # vector-reasoning is confirmed installed (`ollama list`); this fails
    # loudly if a future change makes the LLM path stop being reachable.
    assert report.experiment.design_source == "llm", (
        f"expected an LLM-designed experiment, got design_source="
        f"{report.experiment.design_source!r} — the model call silently "
        f"degraded to the rule-based fallback. Check `ollama list` for "
        f"vector-reasoning and Ollama server health before trusting LIVE."
    )


def test_vector_provider_model_sync_call_survives_worker_thread_with_no_loop():
    """Regression test for the bug found in Phase 0.5c / investment capability:
    VectorProviderModel._sync_call() called asyncio.get_event_loop() but ran
    inside a ThreadPoolExecutor worker thread (via finagent_agent.py's
    loop.run_in_executor(None, _run)). Worker threads never get an event loop
    set automatically on Python 3.10+, so this raised:
        RuntimeError: There is no current event loop in thread '...'
    and _sync_call's except-clause swallowed it into a fake placeholder
    response: "[VECTOR provider_client error: There is no current event loop
    in thread '...']" — masquerading as real (degraded) analysis content.

    This test reproduces the exact failure shape (call _sync_call from inside
    a brand-new worker thread that has never touched asyncio) WITHOUT a real
    network/Ollama round trip — ProviderClient.chat() is stubbed to return
    instantly so this stays a fast, deterministic unit test. It still
    exercises the exact code path that crashed: _sync_call's own
    asyncio.get_event_loop()/loop.run_until_complete() machinery, executed
    inside a brand-new worker thread, awaiting a real coroutine. The
    end-to-end real-LLM proof lives in
    test_finagent_investor_analysis_does_not_hit_event_loop_error below.
    """
    from districts.investment.vector_finagent.agents.finagent_core.registries.vector_model import (
        VectorProviderModel,
    )

    class _FakeResult:
        content = "pong"

    class _FakeProviderClient:
        async def chat(self, *args, **kwargs):
            return _FakeResult()

    # _sync_call does `from core.inference.provider_client import
    # ProviderClient` freshly on every call, so monkeypatching the real
    # module's class attribute (rather than the name inside vector_model)
    # is what actually takes effect.
    import core.inference.provider_client as provider_client_module
    original_provider_client = provider_client_module.ProviderClient
    provider_client_module.ProviderClient = _FakeProviderClient
    try:
        model = VectorProviderModel(id="vector-focus")
        messages = [{"role": "user", "content": "ping"}]

        def _call_in_fresh_thread() -> str:
            # Run in a brand-new worker thread (mirrors loop.run_in_executor's
            # ThreadPoolExecutor workers, which never have
            # asyncio.set_event_loop() called on them) to reproduce the exact
            # thread-local conditions that triggered "There is no current
            # event loop in thread '...'".
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(model._sync_call, messages)
                return future.result(timeout=10)

        content = _call_in_fresh_thread()
    finally:
        provider_client_module.ProviderClient = original_provider_client

    assert "no current event loop" not in content, (
        f"event-loop bug regressed — _sync_call still crashes in worker "
        f"threads: {content!r}"
    )
    assert "There is no current event loop in thread" not in content
    assert content == "pong", f"expected the stubbed response, got: {content!r}"


@pytest.mark.live
@live_only
def test_finagent_investor_analysis_does_not_hit_event_loop_error():
    """Live end-to-end regression test: FinAgentAgent.investor_analysis()
    dispatches CoreAgent.run_stock_analysis() via loop.run_in_executor(),
    which (by default, VECTOR-native provider) routes through
    VectorProviderModel._sync_call(). Before the fix this always degraded to
    the placeholder "[VECTOR provider_client error: There is no current
    event loop in thread '...']" regardless of ticker/persona. After the fix,
    any remaining error (e.g. missing API key, Ollama unavailable) is a
    legitimate, different failure — this test only asserts the specific
    event-loop crash is gone."""
    from districts.investment.finagent_agent import FinAgentAgent

    async def _run():
        agent = FinAgentAgent()
        return await agent.run(
            {"params": {"action": "investor_analysis", "ticker": "AAPL", "persona": "buffett"}}
        )

    result = asyncio.run(_run())
    response_text = str(result.get("result", {}).get("response", result))
    assert "no current event loop" not in response_text, (
        f"event-loop bug regressed in live investor_analysis call: {result!r}"
    )


@pytest.mark.live
@live_only
def test_web_scout_reaches_vector_scraper_and_returns_real_data():
    """Phase 2 scraper sub-task: 'scraper -> NO standalone hand; add a live
    test proving web_scout/collector reach vector_scraper and return real
    scraped data (it's infrastructure, correct as-is).' WebScout.fetch_page()
    routes through core.scraper.vector_scraper.get_scraper().smart_fetch(),
    which itself calls fetch()/fetch_stealth() — both already fixed in Task
    0.5a (resp.text -> resp.html_content). This proves the full integration
    path end-to-end, not just vector_scraper in isolation."""
    from districts.research.web_scout import WebScout

    async def _run():
        scout = WebScout()
        return await scout.fetch_page("https://example.com")

    content = asyncio.run(_run())
    assert content, "web_scout.fetch_page() returned empty content"
    assert len(content) > 50
    assert "Example Domain" in content


# ── FL-012: live provider acceptance (owner decision 2026-10-12) ────────────
# Real free-tier keys now exist in .env (Groq, Cerebras, Gemini, Mistral,
# DeepSeek, Cohere, NVIDIA, OpenRouter, GitHub Models, Cloudflare, Ollama
# Cloud, ZAI) -- these prove the real auto-route and the documented
# cloud-exhaustion -> Ollama fallback actually work end-to-end, not just in
# a mocked unit test.

_CLOUD_KEY_ENV_VARS = (
    "GROQ_API_KEY", "CEREBRAS_API_KEY", "GEMINI_API_KEY", "MISTRAL_API_KEY",
    "DEEPSEEK_API_KEY", "COHERE_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY",
    "GITHUB_TOKEN", "CLOUDFLARE_API_KEY", "OLLAMA_CLOUD_API_KEY", "ZAI_API_KEY",
    "OPENCODE_API_KEY", "LLM7_API_KEY",
)


@pytest.mark.live
@live_only
def test_provider_client_auto_route_reaches_a_real_provider():
    """Auto-routed (no explicit provider=) call must reach some real
    provider -- cloud or Ollama -- and return real, non-empty content."""
    from core.inference.provider_client import ProviderClient

    async def _run():
        client = ProviderClient()
        return await client.complete("Reply with exactly the word: pong", tier="simple")

    result = asyncio.run(_run())
    assert result.content.strip(), "auto-routed call returned empty content"
    assert result.provider, "result did not record which provider served it"


@pytest.mark.live
@live_only
def test_provider_client_falls_back_to_ollama_when_every_cloud_key_is_invalid(monkeypatch):
    """Simulates the documented 'cloud budget exhausted -> automatic
    ollama-only' path (core/inference/route_policy.py) by invalidating every
    real cloud key this session has, then confirming the auto-routed call
    still succeeds and is actually served by the local Ollama fallback, not
    silently empty/crashed."""
    from core.inference import key_pool
    from core.inference.provider_client import ProviderClient

    for var in _CLOUD_KEY_ENV_VARS:
        monkeypatch.setenv(var, "invalid-test-key-does-not-work")
    key_pool.reset_pools()

    async def _run():
        client = ProviderClient()
        return await client.complete("Reply with exactly the word: pong", tier="simple")

    try:
        result = asyncio.run(_run())
    finally:
        key_pool.reset_pools()

    assert result.content.strip(), "ollama-fallback call returned empty content"
    assert result.provider == "ollama", (
        f"expected fallback to terminate on ollama, got provider={result.provider!r}"
    )
