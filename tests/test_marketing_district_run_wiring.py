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

FIXED 2026-09-30 (Phase 3 codebase audit): all 7 marketing-district classes
below now have a hindi_coach.py-style query/content fallback — after every
structured task_type/action branch fails to match, each extracts
params["query"]/params["content"]/task["query"]/task["prompt"] and routes to
whichever real capability the free text actually asks for (and has the
required args for), never guessing a missing required field like url/product/
site_id. Agents with only one real capability (AmazonAdsAgent,
AttributionAgent, SGTMAgent) route any on-topic query straight to it. The
tests below now assert the FIXED behavior: the "unhandled type"/"supported"
stub shape must never appear when a real query was supplied, even if the
underlying capability itself then fails for an unrelated reason (e.g. no LLM
provider reachable in this environment) — that distinction is what
"supported" not in result checks for, since only the stub return includes it.
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

    FIXED: AmazonAdsAgent.run() now has a hindi_coach.py-style query/content
    fallback — this single-capability agent routes any on-topic query
    straight to audit(). "supported" not in result is the robust signal
    that the real capability was reached (only the unhandled-type stub
    includes that key) regardless of whether the LLM call itself succeeds.
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
    # 2026-09-30 (Codex third independent review, same cycle): the real
    # capability this routes to (audit()) makes an unmocked live LLM call --
    # "supported" not in result is the actual robust signal per this test's
    # own docstring; asserting status=="ok" too makes this fail on
    # unrelated provider unavailability, not the routing behavior under test.
    assert result["status"] in ("ok", "error")
    assert "supported" not in result
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

    FIXED: AttributionAgent.run() now has the same fallback — see module
    docstring.
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
    # 2026-09-30 (Codex third independent review, same cycle): see
    # AmazonAdsAgent's identical fix above for the full reasoning.
    assert result["status"] in ("ok", "error")
    assert "supported" not in result
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

    FIXED: GoogleAdsAgent.run() now has the same fallback — see module
    docstring. No "metrics"/"product"/"url" is supplied, so it must route to
    audit_account (the only real capability that needs nothing extra).
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
    # 2026-09-30 (Codex third independent review, same cycle): see
    # AmazonAdsAgent's identical fix above for the full reasoning. "audit"
    # in result is only checked on the "ok" branch, since it's absent on error.
    assert result["status"] in ("ok", "error")
    if result["status"] == "ok":
        assert "audit" in result
    assert "supported" not in result
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

    FIXED: MetaAdsAgent.run() now has the same fallback — see module
    docstring. No "metrics" is supplied despite the "fatigued" keyword, so it
    must fall through to audit_account rather than crash on a missing arg.
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
    # 2026-09-30 (Codex third independent review, same cycle): see
    # AmazonAdsAgent's identical fix above for the full reasoning.
    assert result["status"] in ("ok", "error")
    assert "supported" not in result
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

    FIXED: SEOAgent.run() now has the same fallback — see module docstring.
    No "url" is supplied despite the "broken link" keyword, so it must fall
    through to full_audit (the only capability that needs no required args).
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
    assert isinstance(result, dict)
    assert "supported" not in result
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

    FIXED: SEOPortfolioAgent.run() now has the same fallback — see module
    docstring. No keyword matches onboard/drop/improve/weekly, so it must
    fall through to run_portfolio_review (needs no args).
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
    assert result["status"] == "ok"
    assert "supported" not in result
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

    FIXED: SGTMAgent.run() now has the same fallback — see module docstring.
    This single-capability agent routes any on-topic query straight to
    health_check().
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
    assert result["status"] == "ok"
    assert "supported" not in result
    assert "agent" not in result


# ---------------------------------------------------------------------------
# SELF_DEV_P5_MARKETING specialists (districts/marketing/marketing_specialists.py)
# Real agents, real PermissionConfig, real manifest file. No mocks.
# ---------------------------------------------------------------------------

import yaml

from core.config import PermissionConfig
from districts.marketing.marketing_specialists import (
    SPECIALIST_CLASSES,
    PaidMediaPPCStrategist,
    PaidMediaSearchQueryAnalyst,
    PaidMediaTrackingSpecialist,
    TwitterEngager,
    CrossBorderEcommerce,
)

_MANIFEST = Path(__file__).parent.parent / "config" / "agent_manifest.yaml"


def _marketing_manifest_entries() -> dict[str, dict]:
    data = yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))
    return {e["class"]: e for e in data["districts"]["marketing"]}


def test_specialist_count_and_unique_ids():
    assert len(SPECIALIST_CLASSES) == 29
    assert len({c.profile.agent_id for c in SPECIALIST_CLASSES}) == 29
    assert len({a for c in SPECIALIST_CLASSES for a in (c.profile.primary_action, c.profile.audit_action)}) == 58


def test_every_specialist_is_registered_with_matching_capabilities():
    entries = _marketing_manifest_entries()
    for cls in SPECIALIST_CLASSES:
        path = f"{cls.__module__}.{cls.__name__}"
        assert path in entries, f"{cls.__name__} missing from agent_manifest.yaml marketing district"
        assert entries[path]["capabilities"] == [cls.profile.primary_action, cls.profile.audit_action]


def test_every_specialist_action_is_tiered_green_and_not_elsewhere():
    perms = PermissionConfig()
    for cls in SPECIALIST_CLASSES:
        for action in (cls.profile.primary_action, cls.profile.audit_action):
            assert action in perms.green, f"{action} not classified GREEN"
            assert action not in perms.yellow and action not in perms.red


@pytest.mark.asyncio
async def test_every_specialist_is_a_real_agent_and_routes_both_actions():
    for cls in SPECIALIST_CLASSES:
        agent = cls()
        assert agent.health_points == 500
        assert agent.district == "marketing"
        brief = await agent.run({"type": cls.profile.primary_action, "evidence": {}})
        assert brief["status"] == "ok"
        assert brief["report"]["status"] == "needs_human"
        assert "verification" not in brief
        check = await agent.run({"type": cls.profile.audit_action, "evidence": {}})
        assert check["status"] == "ok"
        assert check["verification"]["verified"] is False
        assert "stub" not in check
        bad = await agent.run({"type": "totally_bogus_type"})
        assert bad["status"] == "error" and "supported_tasks" in bad


@pytest.mark.asyncio
async def test_complete_evidence_makes_brief_ready_and_earns_hp():
    agent = TwitterEngager()
    evidence = {f: "supplied" for f in agent.profile.evidence_fields}
    hp_before = agent.health_points
    result = await agent.run({"type": "twitter_engagement_brief", "evidence": evidence})
    assert result["report"]["status"] == "ready"
    assert agent.health_points > hp_before


@pytest.mark.asyncio
async def test_production_shape_params_evidence_is_read():
    agent = TwitterEngager()
    result = await agent.run({"type": "twitter_post_check", "params": {"evidence": {"draft": {"post": "hello"}}}})
    assert result["verification"]["verified"] is True
    assert result["verification"]["passed"] is True


@pytest.mark.asyncio
async def test_twitter_check_recomputes_length_not_model_opinion():
    agent = TwitterEngager()
    ok = await agent.run({"type": "twitter_post_check", "evidence": {"draft": {"post": "x" * 280}}})
    over = await agent.run({"type": "twitter_post_check", "evidence": {"draft": {"post": "x" * 281}}})
    assert ok["verification"]["passed"] is True
    assert over["verification"]["passed"] is False
    assert over["verification"]["verified_by"] == "deterministic_recomputation"


@pytest.mark.asyncio
async def test_search_query_analyst_finds_wasted_spend_from_real_rows():
    agent = PaidMediaSearchQueryAnalyst()
    rows = [
        {"query": "free crm", "clicks": 40, "cost": 80.0, "conversions": 0},
        {"query": "crm software pricing", "clicks": 30, "cost": 120.0, "conversions": 6},
        {"query": "crm jobs", "clicks": 3, "cost": 4.0, "conversions": 0},
    ]
    result = await agent.run({"type": "search_query_waste_check", "evidence": {"search_terms": rows}})
    check = result["verification"]["checks"][0]
    assert check["wasted_cost"] == 80.0  # "crm jobs" is under the waste threshold, "free crm" is not
    assert check["total_cost"] == 204.0
    assert [c["query"] for c in check["negative_keyword_candidates"]] == ["free crm"]
    assert check["passed"] is False and check["limit_source"] == "default"


@pytest.mark.asyncio
async def test_ppc_check_uses_supplied_targets():
    agent = PaidMediaPPCStrategist()
    evidence = {
        "target_cpa": 50.0,
        "target_roas": 3.0,
        "campaigns": [
            {"name": "brand", "spend": 100.0, "conversions": 4, "conversion_value": 500.0},
            {"name": "generic", "spend": 300.0, "conversions": 3, "conversion_value": 450.0},
            {"name": "idle", "spend": 0, "conversions": 0},
        ],
    }
    checks = (await agent.run({"type": "ppc_budget_check", "evidence": evidence}))["verification"]["checks"]
    by_key = {(c["check"], c["campaign"]): c["passed"] for c in checks}
    assert by_key[("cpa_within_target", "brand")] is True
    assert by_key[("roas_meets_target", "brand")] is True
    assert by_key[("cpa_within_target", "generic")] is False  # 300 / 3 = 100 > 50
    assert by_key[("roas_meets_target", "generic")] is False  # 450 / 300 = 1.5 < 3
    assert not any(c["campaign"] == "idle" for c in checks)


@pytest.mark.asyncio
async def test_tracking_check_flags_missing_events_and_undeduplicated_dual_source():
    agent = PaidMediaTrackingSpecialist()
    evidence = {
        "required_events": ["purchase", "lead"],
        "tracked_events": [
            {"name": "purchase", "source": "pixel", "has_event_id": True},
            {"name": "purchase", "source": "server", "has_event_id": False},
        ],
    }
    checks = {c["check"]: c for c in (await agent.run({"type": "tracking_event_check", "evidence": evidence}))["verification"]["checks"]}
    assert checks["required_events_present"]["missing"] == ["lead"]
    assert checks["dual_source_events_deduplicated"]["events_flagged"] == ["purchase"]


@pytest.mark.asyncio
async def test_cross_border_margin_is_recomputed_from_landed_cost():
    agent = CrossBorderEcommerce()
    evidence = {"min_margin_pct": 20.0, "products": [{"sku": "A1", "price": 100.0, "cogs": 40.0, "shipping": 15.0, "duties": 10.0, "platform_fee_pct": 5.0}]}
    check = (await agent.run({"type": "cross_border_margin_check", "evidence": evidence}))["verification"]["checks"][0]
    assert check["actual"] == 30.0  # (100 - 65 - 5) / 100
    assert check["passed"] is True and check["limit_source"] == "evidence"


# ---------------------------------------------------------------------------
# Review finding (ERROR, core/city/governor.py:427): none of the 58 new
# marketing capability names had an exact DISTRICT_TASK_MAP entry, so
# Governor dispatch misrouted them via substring fallback (e.g.
# search_query_waste_check -> research, video_metadata_check -> learning,
# ppc_budget_check -> governance, paid_social_metrics_check ->
# data_analytics, kuaishou_content_check -> intelligence).
# ---------------------------------------------------------------------------

from core.city.governor import DISTRICT_TASK_MAP


def test_all_58_marketing_specialist_capabilities_have_exact_governor_routes():
    capabilities = {a for c in SPECIALIST_CLASSES for a in (c.profile.primary_action, c.profile.audit_action)}
    assert len(capabilities) == 58
    for action in capabilities:
        assert DISTRICT_TASK_MAP.get(action) == "marketing", (
            f"{action} has no exact 'marketing' route in DISTRICT_TASK_MAP"
        )


def test_previously_misrouted_capabilities_now_route_to_marketing():
    misrouted_examples = {
        "search_query_waste_check": "research",
        "video_metadata_check": "learning",
        "ppc_budget_check": "governance",
        "paid_social_metrics_check": "data_analytics",
        "kuaishou_content_check": "intelligence",
    }
    for action, wrong_district in misrouted_examples.items():
        assert DISTRICT_TASK_MAP[action] == "marketing"
        assert DISTRICT_TASK_MAP[action] != wrong_district


# ---------------------------------------------------------------------------
# Review finding (ERROR, districts/marketing/_skill_loader.py:48): SkillMixin
# used by AICitationStrategist (the real match for ai-citation-strategist /
# agentic-search-optimizer) called vectorcode_llm.chat() without
# session_hydration_prompt() first, violating RULE 1. session_hydration
# itself is never mocked below — only the external LLM call is, per
# .claude/rules/testing.md.
# ---------------------------------------------------------------------------

from districts.marketing.ai_citation_strategist import AICitationStrategist


def test_skill_mixin_chat_hydrates_session_before_llm_call(monkeypatch):
    captured = {}

    def fake_chat(model, messages, timeout=25.0, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr("core.inference.vectorcode_llm.chat", fake_chat)
    agent = AICitationStrategist()
    result = agent._chat("competitor gap analysis for VECTOR")

    assert result == "ok"
    system_messages = [m["content"] for m in captured["messages"] if m["role"] == "system"]
    assert system_messages, "no system message sent to the LLM"
    assert "[SESSION CONTEXT" in system_messages[0]  # real ContextEngine().session_hydration_prompt() output


# ---------------------------------------------------------------------------
# Review finding (ERROR, closed by Claude 2026-09-29): task_completion --
# AICitationStrategist.check_agentic_task_completion(), the real match this
# report claims for the 'agentic-search-optimizer' persona -- was a real,
# agent-declared capability with NO core/config.py tier entry at all, so
# Governor._is_known_task_type() let it dispatch with zero PermissionGateway
# involvement. Same class of gap T9-fix-1 closed for email_agent.py.
# ---------------------------------------------------------------------------

def test_task_completion_has_a_real_tier():
    from core.loop.permission_gateway import PermissionGateway

    assert PermissionGateway()._classify("task_completion") == "GREEN"


@pytest.mark.asyncio
async def test_task_completion_dispatches_via_governor(monkeypatch):
    from core.city.governor import Governor
    from core.city.agent_registry import AgentRegistry
    import core.city.agent_registry as registry_mod

    registry = AgentRegistry()
    agent = AICitationStrategist()
    registry.register(agent)
    old_registry = registry_mod._registry_singleton
    monkeypatch.setattr(registry_mod, "_registry_singleton", registry)
    try:
        gov = Governor()
        gov._registry = registry
        gov._get_registry = lambda: registry
        result = await gov.dispatch({
            "type": "task_completion", "district": "marketing",
            "params": {"task_description": "check the current inbox count"},
        })
        assert result.get("status") != "blocked", result
    finally:
        monkeypatch.setattr(registry_mod, "_registry_singleton", old_registry)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
