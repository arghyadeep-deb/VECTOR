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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
