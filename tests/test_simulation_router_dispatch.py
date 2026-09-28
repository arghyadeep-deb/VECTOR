"""Regression test for the 2026-09-24 external review's Phase 1 finding:
core/api/routers/simulation.py imported a nonexistent module
(vector_social_sim_agent), so every /simulation/* call 500'd. Fixing the
import alone exposed a second, real bug underneath: SocialSimAgent.run()
only read params["action"] (which the router never sets), so every
endpoint except /ontology silently ran build_ontology() regardless of what
was requested -- and /interview and /report used the wrong action-name
strings entirely ("interview_agent"/"generate_report" vs the agent's real
"agent_interview"/"simulation_report").
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.intelligence.social_sim_agent import SocialSimAgent


@pytest.mark.asyncio
@pytest.mark.parametrize("task_type,real_method", [
    ("build_ontology", "build_ontology"),
    ("build_graph", "build_graph"),
    ("generate_personas", "generate_personas"),
    ("simulation_report", "simulation_report"),
    ("agent_interview", "agent_interview"),
    ("run_simulation", "run_simulation"),
])
async def test_task_type_reaches_the_correct_method(task_type, real_method):
    agent = SocialSimAgent.__new__(SocialSimAgent)
    with patch.object(SocialSimAgent, real_method, new=AsyncMock(return_value={"status": "ok"})) as mocked:
        result = await agent.run({"type": task_type, "params": {}})
    mocked.assert_awaited_once()
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_router_ontology_call_shape_reaches_build_ontology():
    from core.api.routers import simulation as sim_router

    fake_agent = AsyncMock()
    fake_agent.run = AsyncMock(return_value={"status": "ok"})
    with patch.object(sim_router, "_get_sim_agent", return_value=fake_agent):
        from core.api.routers.simulation import OntologyRequest, build_ontology
        await build_ontology(OntologyRequest(document="test doc"))
    dispatched = fake_agent.run.await_args.args[0]
    assert dispatched["type"] == "build_ontology"


@pytest.mark.asyncio
async def test_router_interview_uses_the_real_agent_action_name():
    from core.api.routers import simulation as sim_router
    from core.api.routers.simulation import InterviewRequest, interview_agent

    fake_agent = AsyncMock()
    fake_agent.run = AsyncMock(return_value={"status": "ok"})
    with patch.object(sim_router, "_get_sim_agent", return_value=fake_agent):
        await interview_agent(InterviewRequest(user_id="u1", prompt="hi"))
    dispatched = fake_agent.run.await_args.args[0]
    assert dispatched["type"] == "agent_interview", (
        f"router must use the agent's real action name, got {dispatched['type']!r}"
    )


@pytest.mark.asyncio
async def test_router_report_uses_the_real_agent_action_name():
    from core.api.routers import simulation as sim_router
    from core.api.routers.simulation import ReportRequest, generate_report

    fake_agent = AsyncMock()
    fake_agent.run = AsyncMock(return_value={"status": "ok"})
    with patch.object(sim_router, "_get_sim_agent", return_value=fake_agent):
        await generate_report(ReportRequest(trace_db_path="x.db"))
    dispatched = fake_agent.run.await_args.args[0]
    assert dispatched["type"] == "simulation_report", (
        f"router must use the agent's real action name, got {dispatched['type']!r}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
