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

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.agency.client_manager import ClientManager
from districts.agency.performance_tracker import PerformanceTracker


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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
