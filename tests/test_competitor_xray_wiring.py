"""
Wires districts/marketing/competitor_xray.py (the Competitor X-Ray evidence-
tiered brief schema, built but never connected to anything — confirmed via
grep before this session) into CompetitorIntelAgent, which already does the
real LLM-based competitor research. The new build_xray_brief() method
converts the agent's existing free-form LLM findings into the structured,
evidence-tiered, threat-ranked brief schema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_build_xray_brief_converts_profile_into_structured_brief(monkeypatch):
    from districts.marketing.competitor_intel_agent import CompetitorIntelAgent

    agent = CompetitorIntelAgent()
    monkeypatch.setattr(agent, "profile_competitor", lambda competitor, context="": {
        "name": competitor,
        "strengths": ["strong brand", "large user base"],
        "weaknesses": ["slow onboarding"],
        "threat_level": "high",
    })

    brief = agent.build_xray_brief("competitor.com")
    assert brief["normalized_target"] == "https://competitor.com"
    assert brief["target_type"] == "url"
    assert len(brief["icp"]) == 0  # icp not derivable from strengths/weaknesses alone
    assert any("strong brand" in c["claim"] for c in brief["funnel"] + brief["monetization"])
    assert brief["threat_score"] > 50  # "high" threat_level should score high


def test_build_xray_brief_low_threat_scores_low(monkeypatch):
    from districts.marketing.competitor_intel_agent import CompetitorIntelAgent

    agent = CompetitorIntelAgent()
    monkeypatch.setattr(agent, "profile_competitor", lambda competitor, context="": {
        "name": competitor, "strengths": [], "weaknesses": ["everything"], "threat_level": "low",
    })

    brief = agent.build_xray_brief("tinycompetitor")
    assert brief["threat_score"] < 50


def test_run_routes_xray_task_type(monkeypatch):
    from districts.marketing.competitor_intel_agent import CompetitorIntelAgent
    import asyncio

    agent = CompetitorIntelAgent()
    monkeypatch.setattr(agent, "profile_competitor", lambda competitor, context="": {
        "name": competitor, "strengths": ["x"], "weaknesses": ["y"], "threat_level": "medium",
    })

    result = asyncio.run(agent.run({"type": "xray_brief", "params": {"competitor": "rival.com"}}))
    assert "data" in result
    assert result["data"]["target_type"] == "url"
    assert "threat_score" in result["data"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
