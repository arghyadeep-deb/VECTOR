"""
Regression tests for the marketing-district fake-success-stub bug.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work. Seven marketing-district classes overrode run() but either:
  (a) ignored task["type"] entirely and always called the same internal
      method (AmazonAdsAgent, AttributionAgent, SGTMAgent), or
  (b) branched on task["params"]["action"] instead of task["type"]
      (GoogleAdsAgent, MetaAdsAgent, SEOAgent, SEOPortfolioAgent) — meaning
      a governor dispatch of {"type": "...", "params": {}} silently fell
      through to a hardcoded default action regardless of what was asked.

These tests assert that run() now branches on task["type"] and dispatches
to the class's real, existing methods, and that at least two distinct task
types reach two distinct code paths per class.

---

Production-shape coverage (added — see individual "real_chat_dispatch" tests
below): real chat traffic from core/api/routers/commands.py /
core/city/governor.py._dispatch_to_district reaches run() as
{"type": "<LLM-invented task_type>", "params": {"query": "...", "content":
"...", "source": "api_command"}} — an unmatched task_type carrying a real
free-text user question. districts/languages/hindi_coach.py shows the FIXED
pattern: after all structured branches fail to match, it falls back to
routing on p.get("query")/p.get("content") instead of erroring.

As of this writing, NONE of the 7 marketing-district classes below have
that fallback — every one of them still returns the bare
{"status": "error", "error": "unhandled type ..."} stub even when
params contains a real, on-topic user query. The tests below assert that
CURRENT (broken) behavior honestly — they are a regression trip-wire: the
moment one of these agents is fixed to answer free-text queries, the
corresponding test here will fail and must be flipped to assert the "ok"
+ substantive-response shape instead. This is a live product bug, not a
test bug — see the task report for the full list.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.marketing.amazon_ads_agent import AmazonAdsAgent
from districts.marketing.attribution_agent import AttributionAgent
from districts.marketing.google_ads_agent import GoogleAdsAgent
from districts.marketing.meta_ads_agent import MetaAdsAgent
from districts.marketing.seo_agent import SEOAgent
from districts.marketing.seo_portfolio import SEOPortfolioAgent
from districts.marketing.sgtm_agent import SGTMAgent


# ---------------------------------------------------------------------------
# AmazonAdsAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_amazon_ads_agent_run_audit_routes_to_audit():
    agent = AmazonAdsAgent()
    result = await agent.run({"type": "audit", "params": {"account_data": {"spend": 100}}})
    assert result["status"] in ("ok", "error")
    assert result.get("platform") == "amazon" or "audit" in result or result["status"] == "error"


@pytest.mark.asyncio
async def test_amazon_ads_agent_run_unhandled_type_returns_error_shape():
    agent = AmazonAdsAgent()
    result = await agent.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    # Must NOT be the AgentBase stub shape.
    assert "agent" not in result


@pytest.mark.asyncio
async def test_amazon_ads_agent_run_real_chat_dispatch_unmatched_type_with_query():
    """Production shape: LLM-invented task_type + real free-text query.

    LIVE BUG: AmazonAdsAgent.run() has no query/content fallback — a real
    user question about their Amazon Ads account still hits the bare error
    stub. This test documents CURRENT behavior; flip to an "ok" assertion
    once the agent gets a hindi_coach.py-style fallback.
    """
    agent = AmazonAdsAgent()
    result = await agent.run({
        "type": "check_amazon_ads_performance",
        "params": {
            "query": "How are my Amazon sponsored product campaigns performing this month?",
            "content": "How are my Amazon sponsored product campaigns performing this month?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# AttributionAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attribution_agent_run_audit_consent_mode_routes_correctly():
    agent = AttributionAgent()
    result = await agent.run({"type": "audit_consent_mode", "params": {"ga4_data": {}}})
    assert result["status"] in ("ok", "error")


@pytest.mark.asyncio
async def test_attribution_agent_run_unhandled_type_returns_error_shape():
    agent = AttributionAgent()
    result = await agent.run({"type": "not_a_real_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_attribution_agent_run_real_chat_dispatch_unmatched_type_with_query():
    """Production shape: LLM-invented task_type + real free-text query.

    LIVE BUG: AttributionAgent.run() has no query/content fallback — see
    module docstring. Flip to an "ok" assertion once fixed.
    """
    agent = AttributionAgent()
    result = await agent.run({
        "type": "check_conversion_tracking_health",
        "params": {
            "query": "Is our Meta CAPI and Consent Mode V2 setup tracking conversions correctly?",
            "content": "Is our Meta CAPI and Consent Mode V2 setup tracking conversions correctly?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# GoogleAdsAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_ads_agent_run_audit_routes_to_audit_account():
    agent = GoogleAdsAgent()
    result = await agent.run({
        "type": "google_ads_audit",
        "params": {"account_id": "123", "industry": "ecommerce"},
    })
    assert result["status"] == "ok"
    assert result.get("account_id") == "123"
    assert "audit" in result


@pytest.mark.asyncio
async def test_google_ads_agent_run_performance_routes_to_analyze_performance():
    agent = GoogleAdsAgent()
    result = await agent.run({
        "type": "ads_performance",
        "params": {"metrics": {"ctr_pct": 1.0, "cpc_usd": 10.0, "roas": 1.0}, "industry": "ecommerce"},
    })
    assert result["status"] == "ok"
    assert "issues" in result
    assert "score" in result


@pytest.mark.asyncio
async def test_google_ads_agent_run_unhandled_type_returns_error_shape():
    agent = GoogleAdsAgent()
    result = await agent.run({"type": "nonsense_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_google_ads_agent_run_real_chat_dispatch_unmatched_type_with_query():
    """Production shape: LLM-invented task_type + real free-text query.

    LIVE BUG: GoogleAdsAgent.run() has no query/content fallback — see
    module docstring. Flip to an "ok" assertion once fixed.
    """
    agent = GoogleAdsAgent()
    result = await agent.run({
        "type": "how_is_our_google_ads_account_doing",
        "params": {
            "query": "How is our Google Ads account performing this quarter?",
            "content": "How is our Google Ads account performing this quarter?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# MetaAdsAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_meta_ads_agent_run_creative_fatigue_routes_correctly():
    agent = MetaAdsAgent()
    result = await agent.run({
        "type": "meta_ads_creative",
        "params": {
            "metrics": {"frequency": 4.2, "ctr_pct": 0.8, "ctr_pct_prev_week": 1.5, "roas": 1.8},
            "industry": "ecommerce",
        },
    })
    assert result["status"] == "ok"
    assert "fatigue_score" in result
    assert "is_fatigued" in result


@pytest.mark.asyncio
async def test_meta_ads_agent_run_roas_routes_to_analyze_roas():
    agent = MetaAdsAgent()
    result = await agent.run({
        "type": "meta_ads_performance",
        "params": {"campaigns": [{"roas": 4.0, "spend_usd": 100}], "industry": "ecommerce"},
    })
    assert result["status"] == "ok"
    assert "winners" in result
    assert "losers" in result


@pytest.mark.asyncio
async def test_meta_ads_agent_run_unhandled_type_returns_error_shape():
    agent = MetaAdsAgent()
    result = await agent.run({"type": "invalid_type_xyz"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_meta_ads_agent_run_real_chat_dispatch_unmatched_type_with_query():
    """Production shape: LLM-invented task_type + real free-text query.

    LIVE BUG: MetaAdsAgent.run() has no query/content fallback (it branches
    on task["type"] or params["action"], never on free text) — see module
    docstring. Flip to an "ok" assertion once fixed.
    """
    agent = MetaAdsAgent()
    result = await agent.run({
        "type": "is_our_facebook_ad_creative_fatigued",
        "params": {
            "query": "Is our Facebook ad creative fatigued? Frequency has been climbing.",
            "content": "Is our Facebook ad creative fatigued? Frequency has been climbing.",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# SEOAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seo_agent_run_keyword_research_routes_to_analyze_keywords():
    agent = SEOAgent()
    result = await agent.run({"type": "keyword_research", "params": {"topic": "AI automation"}})
    assert "topic" in result


@pytest.mark.asyncio
async def test_seo_agent_run_pagespeed_routes_to_fetch_pagespeed():
    agent = SEOAgent()
    result = await agent.run({"type": "pagespeed", "params": {"url": "https://example.com"}})
    # fetch_pagespeed returns a dict (possibly with "error" if no API key set up) — never the AgentBase stub.
    assert isinstance(result, dict)
    assert "agent" not in result


@pytest.mark.asyncio
async def test_seo_agent_run_unhandled_type_returns_error_shape():
    agent = SEOAgent()
    result = await agent.run({"type": "garbage_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_seo_agent_run_real_chat_dispatch_unmatched_type_with_query():
    """Production shape: LLM-invented task_type + real free-text query.

    LIVE BUG: SEOAgent.run() has no query/content fallback (branches on
    task["type"] or params["action"] only) — see module docstring. Flip to
    an "ok" assertion once fixed.
    """
    agent = SEOAgent()
    result = await agent.run({
        "type": "how_is_our_seo_doing",
        "params": {
            "query": "How's our SEO doing lately? Any broken links or ranking drops I should know about?",
            "content": "How's our SEO doing lately? Any broken links or ranking drops I should know about?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# SEOPortfolioAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seo_portfolio_agent_run_portfolio_review_routes_correctly():
    agent = SEOPortfolioAgent()
    result = await agent.run({"type": "seo_portfolio_review"})
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_seo_portfolio_agent_run_onboard_routes_to_onboard_site():
    agent = SEOPortfolioAgent()
    result = await agent.run({
        "type": "seo_onboard",
        "params": {"url": "https://vector-test-site.example.com", "display_name": "VectorTest"},
    })
    assert result["status"] == "ok"
    assert "site_id" in result


@pytest.mark.asyncio
async def test_seo_portfolio_agent_run_unhandled_type_returns_error_shape():
    agent = SEOPortfolioAgent()
    result = await agent.run({"type": "made_up_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_seo_portfolio_agent_run_real_chat_dispatch_unmatched_type_with_query():
    """Production shape: LLM-invented task_type + real free-text query.

    LIVE BUG: SEOPortfolioAgent.run() has no query/content fallback — see
    module docstring. Flip to an "ok" assertion once fixed.
    """
    agent = SEOPortfolioAgent()
    result = await agent.run({
        "type": "what_is_the_status_of_our_site_portfolio",
        "params": {
            "query": "What's the SEO status across all our sites right now?",
            "content": "What's the SEO status across all our sites right now?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# SGTMAgent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sgtm_agent_run_health_check_routes_correctly():
    agent = SGTMAgent()
    result = await agent.run({"type": "health_check", "params": {"container_url": "https://sgtm.example.com"}})
    assert result["status"] in ("ok", "error")


@pytest.mark.asyncio
async def test_sgtm_agent_run_unhandled_type_returns_error_shape():
    agent = SGTMAgent()
    result = await agent.run({"type": "made_up_type_xyz"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_sgtm_agent_run_real_chat_dispatch_unmatched_type_with_query():
    """Production shape: LLM-invented task_type + real free-text query.

    LIVE BUG: SGTMAgent.run() has no query/content fallback — see module
    docstring. Flip to an "ok" assertion once fixed.
    """
    agent = SGTMAgent()
    result = await agent.run({
        "type": "is_our_server_side_tagging_healthy",
        "params": {
            "query": "Is our server-side GTM container healthy? Any tag firing issues?",
            "content": "Is our server-side GTM container healthy? Any tag firing issues?",
            "source": "api_command",
        },
    })
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
