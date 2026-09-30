"""Regression tests for the Phase 3 QA/health/finance deep audit."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_budget_fetch_failure_does_not_report_within_budget(monkeypatch):
    from districts.finance.budget_analyst import BudgetAnalyst

    agent = BudgetAnalyst()
    monkeypatch.setattr(agent, "_fetch_category_spend", lambda days=30: None)

    result = await agent.run({"type": "budget"})

    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_sleep_fetch_failure_is_not_recorded_as_no_sleep(monkeypatch):
    from districts.health.sleep_tracker import SleepTracker

    agent = SleepTracker()
    monkeypatch.setattr(agent, "_infer_sleep_periods", lambda days=1: None)
    stored = []
    monkeypatch.setattr(agent._memory, "store", lambda **kwargs: stored.append(kwargs))

    result = await agent.run({"type": "sleep"})

    assert result["status"] == "error"
    assert stored == []


@pytest.mark.asyncio
async def test_missing_ear_sensor_is_degraded_not_healthy(monkeypatch):
    from districts.health.fatigue_monitor import FatigueMonitor

    agent = FatigueMonitor()
    monkeypatch.setattr(agent, "_get_ear_from_world_state", lambda: None)

    result = await agent.run({"type": "check_fatigue"})

    assert result["status"] == "ok"
    assert result["assessment_status"] == "degraded"
    assert result["ear_available"] is False


@pytest.mark.asyncio
async def test_biometrics_all_sources_failed_is_unavailable(monkeypatch):
    from districts.health.biometrics_aggregator import BiometricsAggregator

    agent = BiometricsAggregator()

    async def unavailable():
        return None

    monkeypatch.setattr(agent, "_pull_apple_health", unavailable)
    result = await agent.run({"sources": ["apple_health"], "obsidian": False})

    assert result["status"] == "ok"
    assert result["assessment_status"] == "unavailable"
    assert result["records"] == 0


def test_test_parser_does_not_pass_empty_output():
    from districts.qa.test_results_analyzer import TestResultsAnalyzer

    parsed = TestResultsAnalyzer()._parse_output("")

    assert parsed["total"] == 0
    assert parsed["all_passed"] is False


@pytest.mark.asyncio
async def test_test_execution_errors_are_critical(monkeypatch):
    from districts.qa.test_results_analyzer import TestResultsAnalyzer

    agent = TestResultsAnalyzer()
    monkeypatch.setattr(
        agent,
        "run_and_capture",
        lambda script: {"error": "timeout", "passed": 0, "failed": 0, "total": 0},
    )
    monkeypatch.setattr(agent, "get_historical_trend", lambda limit=5: [])

    async def no_llm(*args, **kwargs):
        return "unavailable"

    monkeypatch.setattr(agent, "generate_insights", no_llm)
    monkeypatch.setattr(agent._get_memory(), "store", lambda **kwargs: None)
    monkeypatch.setattr(agent._get_obsidian(), "write_note", lambda *args, **kwargs: None)

    result = await agent.run({})

    assert result["status"] == "ok"
    assert result["verdict"] == "CRITICAL"
    assert result["suite_errors"] == ["timeout", "timeout"]


def test_upi_routine_log_omits_amount(monkeypatch):
    from districts.finance.upi_parser import UPIParser

    agent = UPIParser()
    monkeypatch.setattr(agent._memory, "store", lambda **kwargs: None)
    monkeypatch.setattr(agent._memory, "remember", lambda **kwargs: None)
    messages = []
    monkeypatch.setattr("districts.finance.upi_parser.logger.info", lambda message, *args: messages.append((message, args)))

    result = agent.ingest("Rs.9876.54 debited to Zomato on 30-09-2026")

    assert result is not None
    rendered = " ".join([messages[-1][0], *(str(arg) for arg in messages[-1][1])])
    assert "9876" not in rendered


def test_health_exception_logs_are_contextual():
    """Regression guard against the recurring generic silent-swallow placeholder."""
    from pathlib import Path

    for relative in (
        "districts/health/fatigue_monitor.py",
        "districts/health/trend_analyzer.py",
    ):
        source = Path(relative).read_text(encoding="utf-8")
        assert "[VECTOR] silent swallow" not in source


def test_fpa_forecast_advances_real_calendar_months(monkeypatch):
    from districts.finance import fpa_analyst

    class January31(fpa_analyst.datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 31)

    monkeypatch.setattr(fpa_analyst.datetime, "datetime", January31)
    forecast = fpa_analyst.FPAAnalyst().rolling_forecast([100.0], 3, 0.0)

    assert [row["month"] for row in forecast["forecast"]] == [
        "2026-02",
        "2026-03",
        "2026-04",
    ]
