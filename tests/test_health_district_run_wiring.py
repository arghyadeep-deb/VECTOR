"""
Regression tests for the health-district run() wiring.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work.

  - BiometricsAggregator.run() already does real work — it reads flat
    "sources"/"obsidian" keys directly off the task dict (not via
    task["params"]) and pulls real data sources, persisting results. This is
    a single-purpose agent (one operation: aggregate biometrics), so there is
    no task["type"] to branch on — confirmed correct as-is, not a stub bug.
  - HealthAdvisor had no run() of its own at all (only a separate handle()
    method used a different event-dispatch convention), so it always fell
    through to the AgentBase stub. Added a real run() that branches on
    task["type"] and routes to generate_recommendations()/health_check().

These tests lock in both behaviors.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.health.biometrics_aggregator import BiometricsAggregator
from districts.health.health_advisor import HealthAdvisor


# ---------------------------------------------------------------------------
# BiometricsAggregator (already correct — regression guard only)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_biometrics_aggregator_run_does_real_work_with_no_sources():
    agent = BiometricsAggregator()
    # No real apple_health/oura/strava creds in test env — all sources
    # legitimately fail to pull, but run() must have actually attempted them
    # (not just returned the bare AgentBase stub shape).
    result = await agent.run({"sources": ["apple_health"], "obsidian": False})
    assert result["status"] == "ok"
    assert result["sources_attempted"] == ["apple_health"]
    assert "sources_succeeded" in result
    assert "agent" not in result  # not the bare AgentBase stub shape


@pytest.mark.asyncio
async def test_biometrics_aggregator_run_defaults_to_all_sources():
    agent = BiometricsAggregator()
    result = await agent.run({"obsidian": False})
    assert result["status"] == "ok"
    assert set(result["sources_attempted"]) == {"apple_health", "oura", "strava"}


@pytest.mark.asyncio
async def test_biometrics_aggregator_real_chat_dispatch_shape_still_does_real_work():
    """Real production shape from governor._dispatch_to_district is
    task={"type": <classifier-invented string>, "params": {"query": ...,
    "content": ..., "source": "api_command"}}. BiometricsAggregator.run()
    doesn't branch on task["type"] at all (single-purpose agent, confirmed
    correct in the module docstring above) — it reads "sources"/"obsidian"
    off the TOP-LEVEL task dict, which this shape doesn't set, so it falls
    through to its documented defaults (all three sources, obsidian=True)
    and still performs the real pull attempt rather than returning the
    bare AgentBase stub. Locks in that this remains true for the actual
    real-world dispatch shape, not just the flat-dict shape the existing
    tests above use.
    """
    agent = BiometricsAggregator()
    task = {
        "type": "how_did_i_sleep_last_night",
        "params": {
            "query": "How did I sleep last night?",
            "content": "How did I sleep last night?",
            "source": "api_command",
        },
    }
    result = await agent.run(task)
    assert result["status"] == "ok"
    assert set(result["sources_attempted"]) == {"apple_health", "oura", "strava"}
    assert "sources_succeeded" in result
    assert "agent" not in result  # not the bare AgentBase stub shape


# ---------------------------------------------------------------------------
# HealthAdvisor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_advisor_run_routes_health_recommendations():
    agent = HealthAdvisor()
    result = await agent.run({
        "type": "health_recommendations",
        "params": {"metrics": {"sleep_hours": 4.5}, "trends": {}},
    })
    assert result["status"] == "ok"
    assert "recommendations" in result
    assert any(r["type"] == "SLEEP_HYGIENE" for r in result["recommendations"])


@pytest.mark.asyncio
async def test_health_advisor_run_routes_health_check():
    agent = HealthAdvisor()
    result = await agent.run({"type": "health_check", "params": {}})
    assert result["status"] == "ok"
    assert "monitors" in result
    assert "agent" in result  # health_check()'s own "agent" key, not the stub


@pytest.mark.asyncio
async def test_health_advisor_run_unhandled_type_returns_error_shape():
    agent = HealthAdvisor()
    result = await agent.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
