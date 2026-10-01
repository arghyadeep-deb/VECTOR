"""Audit phase 3 — districts/startups: failed/empty LLM output must fail closed,
never be reported as a real scan/verdict/model."""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest


def _mk(cls_path, cls_name):
    import importlib
    with patch("core.memory.episodic.EpisodicMemory", return_value=MagicMock()), \
         patch("core.memory.obsidian_sync.ObsidianSync", return_value=MagicMock()):
        agent = getattr(importlib.import_module(cls_path), cls_name)()
    agent.memory = MagicMock()
    agent.obsidian = MagicMock()
    return agent


def scanner():
    return _mk("districts.startups.market_scanner", "MarketScanner")


def validator():
    return _mk("districts.startups.idea_validator", "IdeaValidator")


def spy():
    return _mk("districts.startups.competitor_spy", "CompetitorSpy")


def modeler():
    return _mk("districts.startups.revenue_modeler", "RevenueModeler")


BAD = ["", "sorry, I cannot help with that"]


@pytest.mark.parametrize("bad", BAD)
class TestFailClosed:
    def test_scan_market(self, bad):
        a = scanner()
        with patch.object(a, "_call_ollama", return_value=bad):
            r = a.scan_market("AI SaaS")
        assert r["status"] == "error" and "opportunities_count" not in r
        assert a.scan_history == []
        a.memory.store.assert_not_called()

    def test_analyze_trends(self, bad):
        a = scanner()
        with patch.object(a, "_call_ollama", return_value=bad):
            r = a.analyze_trends("x")
        assert r["status"] == "error" and "trend_score" not in r

    def test_identify_gaps(self, bad):
        a = scanner()
        with patch.object(a, "_call_ollama", return_value=bad):
            r = a.identify_gaps("x")
        assert r["status"] == "error" and "gaps" not in r

    def test_validate_idea_not_admitted(self, bad):
        a = validator()
        with patch.object(a, "_call_ollama", return_value=bad):
            r = a.validate_idea({"name": "foo"})
        assert r["status"] == "error" and r["verdict"] == "UNVERIFIED"
        assert a.validated_ideas == {}
        a.memory.store.assert_not_called()

    def test_market_size_and_competition(self, bad):
        a = validator()
        with patch.object(a, "_call_ollama", return_value=bad):
            assert a.analyze_market_size({"name": "foo"})["status"] == "error"
            r = a.assess_competition({"name": "foo"})
        assert r["status"] == "error" and "competitive_intensity" not in r

    def test_competitor_analysis_and_tracking(self, bad):
        a = spy()
        with patch.object(a, "_call_ollama", return_value=bad):
            assert a.analyze_competitor("Acme")["status"] == "error"
            assert a.track_movements("Acme")["status"] == "error"
        assert a.competitor_profiles == {} and a.movement_history == {}

    def test_revenue_unit_econ_runway(self, bad):
        a = modeler()
        with patch.object(a, "_call_ollama", return_value=bad):
            assert a.model_revenue({"name": "foo"})["status"] == "error"
            r = a.calculate_unit_economics({})
            assert r["status"] == "error" and "unit_economics" not in r
            r = a.project_runway({}, {})
        assert r["status"] == "error" and "risk_level" not in r
        assert a.models == {}


def test_competitive_report_empty_llm_is_error():
    a = spy()
    a.competitor_profiles["Acme"] = {"overall_strength": "strong"}
    with patch.object(a, "_call_ollama", return_value=""):
        r = a.generate_competitive_report()
    assert r["status"] == "error" and "full_report" not in r


def test_revenue_gate_missing_score_fails_closed():
    a = validator()
    scores = {"viability": 9, "edge": 9, "timing": 9}  # no revenue_velocity
    with patch.object(a, "_call_ollama", return_value=json.dumps({"scores": scores, "overall_score": 9})), \
         patch("core.brain.blueprint_doctrine.get_regime", return_value="NORMAL"):
        r = a.validate_idea({"name": "foo"})
    assert r["verdict"] == "WEAK"


def test_non_numeric_llm_scores_do_not_crash():
    a = validator()
    out = {"scores": {"revenue_velocity": "9", "viability": "high"}, "overall_score": "8.5"}
    with patch.object(a, "_call_ollama", return_value=json.dumps(out)), \
         patch("core.brain.blueprint_doctrine.get_regime", return_value="NORMAL"):
        r = a.validate_idea({"name": "foo"})
    assert r["verdict"] == "STRONG"


def test_unit_economics_string_numbers_do_not_crash():
    a = modeler()
    out = {"ltv_cac_ratio": "4", "cac_payback_months": "6"}
    with patch.object(a, "_call_ollama", return_value=json.dumps(out)):
        r = a.calculate_unit_economics({})
    assert r["unit_economics"]["health_verdict"] == "GOOD"


def test_runway_missing_months_is_unknown_not_12():
    a = modeler()
    with patch.object(a, "_call_ollama", return_value=json.dumps({"burn_rate": 1})):
        r = a.project_runway({}, {"fixed": []})
    assert r["runway_months"] is None and r["risk_level"] == "UNKNOWN"


@pytest.mark.parametrize("maker", [scanner, validator, spy, modeler])
def test_run_free_text_llm_failure_is_error(maker):
    a = maker()
    with patch.object(a, "_call_ollama", return_value=""):
        r = asyncio.run(a.run({"params": {"query": "what is hot?"}}))
    assert r["status"] == "error"


def test_run_scan_failure_status_not_ok():
    a = scanner()
    with patch.object(a, "_call_ollama", return_value=""):
        r = asyncio.run(a.run({"params": {"niche": "x"}}))
    assert r["status"] == "error"


def test_run_accepts_string_idea_from_venture_pipeline():
    a = validator()
    out = {"scores": {"revenue_velocity": 8, "viability": 8}, "overall_score": 8}
    with patch.object(a, "_call_ollama", return_value=json.dumps(out)), \
         patch("core.brain.blueprint_doctrine.get_regime", return_value="NORMAL"):
        r = asyncio.run(a.run({"params": {"idea": "invoice bot", "description": "d"}}))
    assert r["status"] == "ok" and r["idea_name"] == "invoice bot"
    m = modeler()
    with patch.object(m, "_call_ollama", return_value=json.dumps({"revenue_streams": [], "projections": {}})):
        r = asyncio.run(m.run({"params": {"idea": "invoice bot"}}))
    assert r["status"] == "ok" and r["startup_idea"] == "invoice bot"
