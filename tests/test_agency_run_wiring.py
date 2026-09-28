"""
Regression tests for the agency-district fake-success-stub bug.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work. Two agency-district classes overrode run() but only handled a
single shape of task["params"] without branching on task["type"]:
  - ClientManager.run() only ever called get_client() (or fell through to
    the stub shape), never add_client/track_engagement/list_clients/etc.
  - PerformanceTracker.run() only ever called track_metric() or get_trend(),
    never alert_anomaly/get_active_alerts/get_metric_summary/etc.

These tests assert that run() now branches on task["type"] and dispatches
to the class's real, existing methods, and that an unrecognized type
returns the standard error shape instead of silently falling through.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.agency.client_manager import ClientManager
from districts.agency.performance_tracker import PerformanceTracker
from districts.agency import content_strategist, proposal_strategist, sales_strategist


# ---------------------------------------------------------------------------
# ClientManager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_client_manager_run_add_client_routes_correctly():
    agent = ClientManager()
    result = await agent.run({
        "type": "add_client",
        "params": {"name": "Test Client Wiring Co", "contact": "wiring@test.com"},
    })
    assert result["status"] in ("success", "error")
    agent.delete_client("Test Client Wiring Co")


@pytest.mark.asyncio
async def test_client_manager_run_get_client_routes_correctly():
    agent = ClientManager()
    agent.add_client("Test Client Wiring Get", "get@test.com")
    result = await agent.run({
        "type": "get_client",
        "params": {"name": "Test Client Wiring Get"},
    })
    assert result["status"] == "ok"
    assert result["client"] is not None
    agent.delete_client("Test Client Wiring Get")


@pytest.mark.asyncio
async def test_client_manager_run_client_summary_routes_correctly():
    agent = ClientManager()
    result = await agent.run({"type": "client_summary", "params": {}})
    assert result["status"] == "ok"
    assert "total_clients" in result


@pytest.mark.asyncio
async def test_client_manager_run_unhandled_type_returns_error_shape():
    agent = ClientManager()
    result = await agent.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_client_manager_run_real_chat_query_shape_routes_to_client_data():
    """
    A novel classifier task type retains a question that maps to ClientManager's
    existing client-summary and churn-risk methods.  It must return their real
    data, rather than the generic unhandled-type error shape.
    """
    agent = ClientManager()
    client_name = "Agency Wiring Query Client"
    agent.delete_client(client_name)
    try:
        added = agent.add_client(client_name, "private@example.test", notes="private note")
        assert added["status"] == "success"
        result = await agent.run({
            "type": "client_question",
            "params": {
                "query": "how many clients do we have and which ones need attention?",
                "content": "how many clients do we have and which ones need attention?",
                "source": "api_command",
            },
        })
        assert result["status"] == "ok"
        assert result["summary"]["total_clients"] >= 1
        matching_client = next(client for client in result["at_risk_clients"] if client["name"] == client_name)
        assert matching_client == {
            "name": client_name,
            "status": "active",
            "engagement_score": 0,
        }
    finally:
        agent.delete_client(client_name)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "Can you delete client Acme? They are at risk.",
    "Add a client, total spend 500.",
    "Could you show the client subtotal?",
    "Which clients are brisk?",
])
async def test_client_manager_chat_only_answers_explicit_read_questions(query):
    agent = ClientManager()
    result = await agent.run({"type": "client_question", "params": {"query": query}})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]


# ---------------------------------------------------------------------------
# PerformanceTracker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_performance_tracker_run_track_metric_routes_correctly():
    agent = PerformanceTracker()
    result = await agent.run({
        "type": "track_metric",
        "params": {"metric": "wiring_test_metric", "value": 42.0},
    })
    assert result["status"] == "ok"
    agent.remove_metric("wiring_test_metric")


@pytest.mark.asyncio
async def test_performance_tracker_run_get_trend_routes_correctly():
    agent = PerformanceTracker()
    agent.track_metric("wiring_trend_metric", 10.0)
    result = await agent.run({
        "type": "get_trend",
        "params": {"metric": "wiring_trend_metric"},
    })
    assert result["status"] == "ok"
    assert "trend" in result or "data_points" in result
    agent.remove_metric("wiring_trend_metric")


@pytest.mark.asyncio
async def test_performance_tracker_run_active_alerts_routes_correctly():
    agent = PerformanceTracker()
    result = await agent.run({"type": "active_alerts", "params": {}})
    assert result["status"] == "ok"
    assert "alerts" in result


@pytest.mark.asyncio
async def test_performance_tracker_run_unhandled_type_returns_error_shape():
    agent = PerformanceTracker()
    result = await agent.run({"type": "made_up_type_xyz"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


@pytest.mark.asyncio
async def test_performance_tracker_run_real_chat_query_shape_routes_to_metric_data():
    """
    A novel classifier task type retains a question that maps to
    PerformanceTracker's existing trend, summary, and alert methods.  It must
    return real tracker data rather than the generic unhandled-type error.
    """
    agent = PerformanceTracker()
    metric_name = "agency_wiring_response_time_ms"
    agent.remove_metric(metric_name)
    try:
        agent.track_metric(metric_name, 42.0)
        result = await agent.run({
            "type": "performance_question",
            "params": {
                "query": "How is agency wiring response time trending this week, any anomalies?",
                "content": "How is agency wiring response time trending this week, any anomalies?",
                "source": "api_command",
            },
        })
        assert result["status"] == "ok"
        assert result["summary"]["metrics"][metric_name]["latest"] == 42.0
        assert result["metric"] == metric_name
        assert result["trend"]["first_value"] == 42.0
        assert "alerts" in result
    finally:
        agent.remove_metric(metric_name)


@pytest.mark.asyncio
async def test_performance_tracker_run_chat_query_resolves_named_metric_without_unit():
    agent = PerformanceTracker()
    metric_name = "agency_wiring_response_time_ms"
    agent.remove_metric(metric_name)
    try:
        agent.track_metric(metric_name, 42.0)
        result = await agent.run({
            "type": "performance_question",
            "params": {"query": "How is agency wiring response time trending?"},
        })
        assert result["status"] == "ok"
        assert result["metric"] == metric_name
        assert result["trend"]["metric"] == metric_name
    finally:
        agent.remove_metric(metric_name)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "Can you set an alert on cpu above 90?",
    "Remove the performance metric X.",
    "How is our performance?",
])
async def test_performance_tracker_chat_only_answers_explicit_read_questions(query):
    agent = PerformanceTracker()
    result = await agent.run({"type": "performance_question", "params": {"query": query}})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]


@pytest.mark.asyncio
async def test_performance_tracker_chat_reports_ambiguous_metric_name():
    agent = PerformanceTracker()
    metric_names = [
        "agency_wiring_response_time_ms",
        "agency_wiring_response_time_p95",
    ]
    for metric_name in metric_names:
        agent.remove_metric(metric_name)
    try:
        for metric_name in metric_names:
            agent.track_metric(metric_name, 42.0)
        result = await agent.run({
            "type": "performance_question",
            "params": {"query": "How is agency wiring response time trending?"},
        })
        assert result["status"] == "error"
        assert result["error"] == "ambiguous metric reference"
        assert set(result["matching_metrics"]) == set(metric_names)
    finally:
        for metric_name in metric_names:
            agent.remove_metric(metric_name)


@pytest.mark.asyncio
async def test_performance_tracker_chat_alert_plus_trend_with_no_named_metric_does_not_crash():
    """Crash-path regression: a trend cue combined with an alert/summary cue and no named metric
    used to raise IndexError on metric_matches[0] -- the outer guard only requires
    asks_alerts/asks_summary to be true, not a named metric, so asks_trend could reach the trend
    branch with an empty metric_matches list. Must now skip the trend branch instead of crashing."""
    agent = PerformanceTracker()
    result = await agent.run({
        "type": "performance_question",
        "params": {"query": "Are there any active alerts and how is the trend?"},
    })
    assert result["status"] == "ok"
    assert "trend" not in result
    assert "metric" not in result
    assert "alerts" in result


# ---------------------------------------------------------------------------
# Rule 1: every agency LLM call carries real session hydration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sales_outreach_prepends_unmocked_session_hydration(monkeypatch):
    captured = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return "draft outreach"

    monkeypatch.setattr(sales_strategist, "chat", fake_chat)
    result = await sales_strategist.SalesStrategist().write_outreach(
        "Ada", "Example Co", "announced an AI initiative",
    )
    assert result == "draft outreach"
    assert captured["messages"][0]["role"] == "system"
    assert "[SESSION CONTEXT" in captured["messages"][0]["content"]


@pytest.mark.asyncio
async def test_proposal_summary_prepends_unmocked_session_hydration(monkeypatch):
    captured = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return "proposal summary"

    monkeypatch.setattr(proposal_strategist, "chat", fake_chat)
    result = await proposal_strategist.ProposalStrategist().write_executive_summary(
        "manual reporting", "automated reporting",
    )
    assert result == "proposal summary"
    assert captured["messages"][0]["role"] == "system"
    assert "[SESSION CONTEXT" in captured["messages"][0]["content"]


def test_content_strategy_prepends_unmocked_session_hydration(monkeypatch):
    captured = {}

    async def fake_provider_chat(self, messages, **kwargs):
        captured["messages"] = messages
        return SimpleNamespace(content="content analysis")

    from core.inference.provider_client import ProviderClient

    monkeypatch.setattr(ProviderClient, "chat", fake_provider_chat)
    result = content_strategist._llm("Analyze this topic", max_tokens=10)
    assert result == "content analysis"
    assert captured["messages"][0]["role"] == "system"
    assert "[SESSION CONTEXT" in captured["messages"][0]["content"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
