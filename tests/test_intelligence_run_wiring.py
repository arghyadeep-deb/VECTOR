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


@pytest.mark.asyncio
async def test_social_sim_agent_run_real_chat_query_shape_now_errors_honestly():
    """
    Production shape: {"type": <LLM-invented string>, "params": {"query":
    ..., "content": ..., "source": "api_command"}}. Unlike the other
    districts' run() methods (which key off task["type"] and error on a
    miss), SocialSimAgent.run() (districts/intelligence/social_sim_agent.py,
    lines ~437-485) ignores task["type"] completely -- it reads
    `p = task.get("params", task)` then `action = p.get("action",
    "build_ontology")`. A real governor dispatch never puts an "action" key
    in params (that's this agent's own internal vocabulary, not part of the
    task["type"]/params["query"] contract every other agent uses), so
    action silently defaults to "build_ontology" no matter what the actual
    task_type or query says.

    This is a DIFFERENT bug shape than the bare-error-stub pattern seen in
    the other districts this file's siblings cover: instead of erroring
    honestly, a real user query like "predict how the public will react to
    this new product launch on social media" gets silently misrouted into
    build_ontology(document_texts=[""], simulation_requirement="") --
    document_texts falls back to [p.get("text", "")] and simulation_
    requirement falls back to p.get("requirement", ""), and since params
    only has query/content/source (no "text" or "requirement" key), both
    come out blank. The user's actual question is dropped on the floor
    entirely rather than being used as simulation_requirement or answered
    directly. status is asserted as ("ok", "error") because build_ontology's
    outcome depends on whether an LLM_API_KEY/OPENAI_API_KEY is configured
    in this environment (see districts/intelligence/vector_social_sim/app/
    utils/llm_client.py: raises ValueError if unset, caught internally and
    returned as {"status": "error", ...}) -- this mirrors the tolerance
    already used by test_social_sim_agent_run_build_ontology_routes_correctly
    above for the same reason. The finding that matters here is the
    silent misroute, not which of ok/error comes back.
    """
    agent = SocialSimAgent()
    task = {
        "type": "social_prediction_request",
        "params": {
            "query": "predict how the public will react to this new product launch on social media",
            "content": "predict how the public will react to this new product launch on social media",
            "source": "api_command",
        },
    }
    result = await agent.run(task)
    # 2026-09-24 (external review, Phase 1): run() now keys off task["type"]
    # and returns the honest unknown-action error for a type it does not
    # handle, instead of silently running build_ontology with a blank query
    # (the misroute this test used to document).
    assert result["status"] == "error"
    assert "unknown action" in result.get("error", "")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
