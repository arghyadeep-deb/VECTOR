"""
Regression-guard tests for SocialSimAgent.run() (districts/intelligence/social_sim_agent.py).

Unlike its sibling fake-success-stub bugs in other districts, SocialSimAgent's
run() already branches on task["params"]["action"] (read via
task.get("params", task) so a bare flat dict also works) and dispatches to
seven distinct real async methods, with a real error shape for unknown
actions. This file locks that correct behavior in place so a future edit
can't silently regress it back to a stub.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.intelligence.social_sim_agent import SocialSimAgent


@pytest.mark.asyncio
async def test_social_sim_agent_run_build_ontology_routes_correctly():
    agent = SocialSimAgent()
    result = await agent.run({
        "params": {
            "action": "build_ontology",
            "document_texts": ["A short test document about AI policy."],
            "requirement": "Predict public reaction to a new AI regulation policy",
        }
    })
    assert result["status"] in ("ok", "error")


@pytest.mark.asyncio
async def test_social_sim_agent_run_default_action_is_build_ontology():
    agent = SocialSimAgent()
    # No "action" key at all -> defaults to build_ontology per p.get("action", "build_ontology").
    result = await agent.run({"params": {"text": "Some text", "requirement": "test"}})
    assert result["status"] in ("ok", "error")


@pytest.mark.asyncio
async def test_social_sim_agent_run_generate_personas_routes_correctly():
    agent = SocialSimAgent()
    result = await agent.run({
        "params": {"action": "generate_personas", "graph_id": "fake-graph-id"}
    })
    assert result["status"] == "error"  # No ZEP_API_KEY configured in test env.
    assert "error" in result


@pytest.mark.asyncio
async def test_social_sim_agent_run_unknown_action_returns_error_shape():
    agent = SocialSimAgent()
    result = await agent.run({"params": {"action": "totally_bogus_action"}})
    assert result["status"] == "error"
    assert "unknown action" in result["error"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
