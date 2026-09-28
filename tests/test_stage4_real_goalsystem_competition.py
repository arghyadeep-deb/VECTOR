"""V1 Stage 4 (long-horizon autonomy), the strict version the 2026-09-27 reconstruction asked for.

tests/test_stage4_long_horizon_termination.py proves a multi-step plan terminates, but it (a) MOCKS the goal system to an empty
one, so no ambient candidate ever competes with the plan's, and (b) injects the failure as an impossible verification criterion.
This test removes both shortcuts:

  * the goal system is the REAL GoalSystem, seeded with the real pre-seeded goals in an isolated DB, so real goal-derived
    candidates compete with the plan's steps in every tick;
  * the failure is a REAL tool failure: GitBot really runs git against a directory that is not a repository and returns
    nothing; the gateway/executor must recognise that as a failure (no evidence of success), and the declared fallback must
    then complete the step;
  * nothing is pre-seeded in PolicyMemory, no step is hand-driven, and verification is not weakened;
  * the plan is goal-linked, the way every production plan is (GoalSystem._decompose_to_plan sets goal_id).

What it found (2026-09-27): with the real goal system a ready plan step scored 0.715 against an ambient goal candidate at
0.72-0.76 and lost tick after tick, so the plan never advanced (40 ticks, zero steps run). Fixed by anti-starvation aging of
ready plan steps (AutonomousLoop._get_plan_candidates / _age_plan_candidates).

Plan:  s1 -> s2 ; s1 -> s3 (real git failure -> fallback) ; s2 + s3 -> s4.
"""
from __future__ import annotations

import sys
import tempfile
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

MAX_TICKS = 40


def _plan(not_a_repo: str, goal_id: str = "") -> Plan:
    return Plan(
        id="plan-stage4-real",
        goal_id=goal_id,
        objective="Stage 4 (strict): fork/merge plan with a real tool failure, competing with real goal candidates",
        status="active",
        steps=[
            PlanStep(id="s1", action_type="git_status", params={}, verification={"type": "status_check"}),
            PlanStep(id="s2", action_type="recent_commits", params={}, depends_on=["s1"],
                     verification={"type": "status_check"}),
            PlanStep(
                id="s3", action_type="git_status", params={"repo": not_a_repo}, depends_on=["s1"],
                verification={"type": "status_check"},
                fallback=PlanStepFallback(action_type="recent_commits", verification={"type": "status_check"}),
            ),
            PlanStep(id="s4", action_type="git_status", params={}, depends_on=["s2", "s3"],
                     verification={"type": "status_check"}),
        ],
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("goal_linked", [True, False], ids=["goal-linked", "goal-less"])
async def test_plan_terminates_with_real_goal_candidates_and_a_real_tool_failure(
    isolated_vector_db, isolated_agent_registry, tmp_path, monkeypatch, goal_linked,  # noqa: F811
):
    monkeypatch.setattr("core.sensing.stuck_detector.get_active_session", lambda: None, raising=False)
    engine = build_isolated_engine(str(tmp_path / "epistemic.db"))

    # Spy on the REAL evaluate(): record what actually competed in each tick (nothing is replaced).
    competed: list[list[str]] = []
    real_evaluate = engine.evaluate

    async def spy(cands, *a, **k):
        competed.append([c.source for c in cands])
        return await real_evaluate(cands, *a, **k)

    monkeypatch.setattr(engine, "evaluate", spy)

    loop = AutonomousLoop()
    loop._decision_engine = engine
    loop._plan_store = PlanStore(path=tmp_path / "plans.json")
    ctx = MagicMock()
    ctx.get_world_state.return_value = {}
    monkeypatch.setattr(loop, "_get_context", lambda: ctx)
    # NOTE: _get_goals is NOT patched -- the real GoalSystem, real seeded goals.

    goals = loop._get_goals()
    assert goals.generate_immediate_actions(), "precondition: the real goal system must produce competing candidates"
    goal_progress_before = {g["id"]: g.get("progress", 0.0) for g in goals.get_active_goals()}

    not_a_repo = tempfile.mkdtemp(prefix="stage4_not_a_repo_")
    linked = next(g for g in goals.get_active_goals() if g["horizon"] in ("MID", "LONG"))["id"] if goal_linked else ""
    plan = _plan(not_a_repo, goal_id=linked)
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
    diag = {sid: (s.status, s.action_type, (s.reason or "")[:70]) for sid, s in steps.items()}
    assert final.status == "completed", f"plan did not terminate: {final.status} after {ticks} ticks: {diag}"
    assert all(s.status == "completed" for s in final.steps), diag

    # the failure was real and was recognised as one, not verified: the fallback replaced s3 exactly once
    events = [e.type for e in final.events]
    assert "fallback_activated" in events, events
    assert final.replan_count == 1, final.replan_count
    assert steps["s3"].action_type == "recent_commits", steps["s3"].action_type

    # competition was real: goal-derived candidates were on the table in the ticks that ran the plan
    assert any(any(src and not src.startswith("plan:") for src in srcs) for srcs in competed), competed[:3]
    assert any(any(src and src.startswith("plan:") for src in srcs) for srcs in competed)

    # progress comes only from verified steps: only the plan's own goal moved, upward, never to completion by this bridge
    after = {g["id"]: g.get("progress", 0.0) for g in goals.get_active_goals()}
    moved = {gid for gid, p in after.items() if p != goal_progress_before.get(gid)}
    assert moved <= ({linked} if linked else set()), f"progress moved on goals the plan does not serve: {moved}"
    if linked:
        assert goal_progress_before[linked] <= after[linked] < 1.0
        assert all(g["status"] == "active" for g in goals.get_active_goals() if g["id"] == linked)
    assert ticks < MAX_TICKS, f"needed {ticks} ticks (budget {MAX_TICKS}); competition delayed termination"


# ── the aging mechanism itself ──────────────────────────────────────────────

def test_a_step_that_keeps_losing_gains_priority_and_a_winner_starts_over():
    from core.loop.decision_engine import Candidate

    loop = AutonomousLoop.__new__(AutonomousLoop)
    step, other = "plan:p:s1", "plan:p:s2"
    cands = [Candidate(action_type="a", params={}, source=step), Candidate(action_type="b", params={}, source=other),
             Candidate(action_type="c", params={}, source="think_loop")]

    class D:  # a decision whose winner is the ambient candidate
        winner = cands[2]

    loop._age_plan_candidates(cands, D)
    loop._age_plan_candidates(cands, D)
    assert loop._plan_step_waits == {step: 2, other: 2}

    class W:  # now s1 wins
        winner = cands[0]

    loop._age_plan_candidates(cands, W)
    assert loop._plan_step_waits == {step: 0, other: 3}
    loop._age_plan_candidates([cands[2]], D)     # a step that is no longer ready is forgotten
    assert loop._plan_step_waits == {}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
