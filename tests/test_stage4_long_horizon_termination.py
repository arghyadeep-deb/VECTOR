"""V1 Stage 4 (long-horizon autonomy): a multi-step plan must run to a truthful termination.

The 2026-09-22 Stage 4 report ended PARTIAL: every sub-claim had live evidence except "termination", and it named two
carried findings -- (1) an empty GoalSystem starved plan candidates, (2) a fallback inherited an unsatisfiable
verification and forced a second replan. Both were fixed on 2026-09-24 (tests/test_think_tick_plan_candidates_without_goals.py,
tests/test_plan_fallback_verification.py) but the end-to-end run was never repeated. This is that run, as a regression test.

It drives the REAL AutonomousLoop._think_tick() -> DecisionEngine -> _act_on_plan_step() -> PlanRunner -> AutonomousExecutor ->
PermissionGateway -> Governor -> GitBot chain (read-only GREEN git actions, real subprocesses) against an isolated DB, an
isolated PlanStore and a two-agent registry. Nothing is stubbed below the loop. The goal system is empty on purpose.

Plan (fork/merge DAG):  s1 -> s2 ; s1 -> s3 (fails verification, falls back) ; s2 + s3 -> s4
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.autonomous_loop import AutonomousLoop
from core.runtime.plans import Plan, PlanStep, PlanStepFallback, PlanStore, _now
from tests.test_r13_production_learning_validation import (  # reuse the proven isolation fixtures
    build_isolated_engine,
    isolated_agent_registry,  # noqa: F401  (pytest fixture)
)

MAX_TICKS = 25


def _plan() -> Plan:
    return Plan(
        id="plan-stage4-term",
        goal_id="",
        objective="Stage 4: long-horizon fork/merge plan runs to a truthful termination",
        status="active",
        steps=[
            PlanStep(id="s1", action_type="git_status", params={}, verification={"type": "status_check"}),
            PlanStep(id="s2", action_type="recent_commits", params={}, depends_on=["s1"],
                     verification={"type": "status_check"}),
            PlanStep(
                id="s3", action_type="git_status", params={}, depends_on=["s1"],
                # impossible on purpose: a real, honest verification failure (the action itself succeeds)
                verification={"type": "confidence_threshold", "min_confidence": 2.0},
                fallback=PlanStepFallback(action_type="recent_commits", verification={"type": "status_check"}),
            ),
            PlanStep(id="s4", action_type="git_status", params={}, depends_on=["s2", "s3"],
                     verification={"type": "status_check"}),
        ],
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.mark.asyncio
async def test_fork_merge_plan_runs_to_truthful_termination(
    isolated_vector_db, isolated_agent_registry, tmp_path, monkeypatch,  # noqa: F811
):
    monkeypatch.setattr("core.sensing.stuck_detector.get_active_session", lambda: None, raising=False)
    engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
    loop = AutonomousLoop()
    loop._decision_engine = engine
    loop._plan_store = PlanStore(path=tmp_path / "plans.json")

    ctx = MagicMock()
    ctx.get_world_state.return_value = {}
    goals = MagicMock()
    goals.generate_immediate_actions.return_value = []  # empty GoalSystem: the Stage 4 finding-1 condition
    monkeypatch.setattr(loop, "_get_context", lambda: ctx)
    monkeypatch.setattr(loop, "_get_goals", lambda: goals)

    plan = _plan()
    loop._plan_store.add(plan)

    ticks = 0
    while ticks < MAX_TICKS:
        current = loop._plan_store.get(plan.id)
        if current.status not in ("active", "in_progress", "running"):
            break
        ticks += 1
        loop._tick_count = ticks
        await loop._think_tick()

    final = loop._plan_store.get(plan.id)
    steps = {s.id: s for s in final.steps}
    assert final.status == "completed", f"plan did not terminate: status={final.status} after {ticks} ticks: " + str(
        {sid: (s.status, s.reason[:60]) for sid, s in steps.items()})
    assert all(s.status == "completed" for s in final.steps), {sid: s.status for sid, s in steps.items()}
    # the honest-failure path really happened: s3's verification failed, the declared fallback replaced it in place
    # and passed its own criteria, and it took exactly one replan (no cascade onto the fallback)
    assert final.replan_count == 1, final.replan_count
    assert steps["s3"].action_type == "recent_commits", steps["s3"].action_type
    events = [e.type for e in final.events]
    assert "fallback_activated" in events, events
    assert ticks < MAX_TICKS, f"needed {ticks} ticks (budget {MAX_TICKS}) -- termination is not comfortably reached"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
