"""
Regression test for the skills-district fake-success-stub bug.

AgentBase.run() (core/city/agent_base.py) defines a generic fallback that
returns {"status": "ok", "agent": self.name, "task": task} without doing any
real work. GapAnalyst overrode run() with a broken hasattr() guard checking
for a method name that doesn't exist on the class at all (a typo/placeholder
that always evaluates False), so run() always fell through to the AgentBase
stub shape regardless of task content:
  - GapAnalyst.run() checked hasattr(self, "analyse_gaps") — the real
    method is analyze_gaps() (American spelling); "analyse_gaps" never
    exists, so the branch was always dead code.

This test asserts that run() now branches on task["type"] and dispatches
to the class's real, existing methods, and that an unrecognized type
returns the standard error shape instead of silently falling through.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.skills.gap_analyst import GapAnalyst


@pytest.mark.asyncio
async def test_gap_analyst_run_analyze_gaps_routes_correctly():
    agent = GapAnalyst()
    result = await agent.run({
        "type": "analyze_gaps",
        "params": {
            "required_skills": ["Python", "Docker", "Kubernetes"],
            "current_skills": ["Python", "Git"],
        },
    })
    assert result["status"] == "ok"
    assert "critical_gaps" in result
    assert "gap_analysis" in result


@pytest.mark.asyncio
async def test_gap_analyst_run_prioritize_gaps_routes_correctly():
    agent = GapAnalyst()
    result = await agent.run({
        "type": "prioritize_gaps",
        "params": {"gaps": [{"skill": "Docker", "severity": "critical"}]},
    })
    assert result["status"] == "ok"
    assert "prioritized_gaps" in result


@pytest.mark.asyncio
async def test_gap_analyst_run_suggest_learning_path_routes_correctly():
    agent = GapAnalyst()
    result = await agent.run({
        "type": "suggest_learning_path",
        "params": {"skill_gap": {"skill": "Kubernetes", "severity": "major"}},
    })
    assert result["status"] == "ok"
    assert "learning_path" in result


@pytest.mark.asyncio
async def test_gap_analyst_run_unhandled_type_returns_error_shape():
    agent = GapAnalyst()
    result = await agent.run({"type": "totally_bogus_type"})
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result
    assert "agent" not in result


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
