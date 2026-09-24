"""
S3-1 — Verified plan-step progress bridge regression tests.

Background: core/loop/autonomous_loop.py::AutonomousLoop._act_on_plan_step()
now bridges a plan step's REPORTED, VERIFIED outcome into its linked goal's
progress (see the "Bridge only verified, partial plan progress into the
linked goal" comment right after the causal_graph write in that method). The
bridge fires only when ALL of the following hold on the dict returned by
PlanRunner.execute_step():
  - plan.goal_id is set
  - result["status"] == "completed"
  - result["verification_passed"] is True
  - result["plan_progress"] is a real number with 0.0 < plan_progress < 1.0
    (1.0 is deliberately excluded so this path can never trigger
    GoalSystem's own automatic completion transition)
It then sets the goal's progress to max(current_progress, plan_progress) —
never regresses it, and never re-writes when the new value does not exceed
the current one.

This suite proves that bridge fires ONLY on genuinely verified partial
progress, and that the pre-existing Task 89C anti-fabrication control
(ordinary action success alone never moves goal progress) still holds
alongside it.

Per this project's testing convention (.claude/rules/testing.md: use a real
test DB, not mocks, for SQLite-backed state) this suite uses a REAL
AutonomousLoop + REAL GoalSystem + REAL PlanStore/Plan/PlanStep, backed by
tests/conftest.py's `isolated_vector_db` fixture and a temp-file PlanStore
path. The ONE component that is stubbed is `core.runtime.plans.PlanRunner`
itself — PlanRunner.execute_step() is where the real permission-gated
executor dispatch happens (network/LLM/district execution), and this task's
scope is exclusively the bridge logic in _act_on_plan_step() that consumes
PlanRunner's RETURNED result dict, not PlanRunner's own internals (those
belong to core/runtime/plans.py, which is out of scope for this task per its
FORBIDDEN SCOPE list). The stub is swapped in via monkeypatch on the module
attribute `core.runtime.plans.PlanRunner`, which _act_on_plan_step() imports
locally at call time (`from core.runtime.plans import PlanRunner`) — no
production code is modified to make this possible.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, AsyncMock

import pytest

from core.brain.goal_system import GoalSystem
from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate
from core.runtime.plans import Plan, PlanStep, PlanStore


def make_plan_step_winner(plan_id: str, step_id: str, action_type: str, goal_ids: list[str]) -> Candidate:
    """Mirrors AutonomousLoop._get_plan_candidates()'s real Candidate shape
    for a plan step: source="plan:{plan_id}:{step_id}", GREEN-tier action
    type ("research_topic") so it never hits the RedTeamAgent adversarial
    review path in _run_soft_safety_checks()."""
    return Candidate(
        action_type=action_type,
        params={"_plan_id": plan_id, "_step_id": step_id},
        goal_ids=goal_ids,
        confidence=0.6,
        urgency=0.55,
        timing_score=1.0,
        estimated_cost_inr=0.0,
        source=f"plan:{plan_id}:{step_id}",
    )


class _StubPlanRunner:
    """Deterministic stand-in for core.runtime.plans.PlanRunner. Returns a
    pre-registered result dict per step_id instead of actually executing
    anything (no permission gateway, no district dispatch, no LLM, no
    network) — exercises _act_on_plan_step()'s bridge logic against a fully
    controlled result shape."""

    # Populated by each test before calling loop._act_on(); keyed by step_id.
    results: dict[str, dict] = {}

    def __init__(self, store=None):
        self.store = store

    async def execute_step(self, plan, step):
        return _StubPlanRunner.results[step.id]


def make_two_step_plan(goal_id: str, plan_id: str = "plan-s3-1") -> Plan:
    from core.runtime.plans import _now
    step1 = PlanStep(id="step-1", action_type="research_topic", params={})
    step2 = PlanStep(id="step-2", action_type="research_topic", params={}, depends_on=["step-1"])
    return Plan(
        id=plan_id,
        goal_id=goal_id,
        objective="S3-1 bridge test plan",
        status="active",
        steps=[step1, step2],
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.fixture
def loop_with_stub_plan_runner(isolated_vector_db, tmp_path, monkeypatch):
    """Real AutonomousLoop + real GoalSystem (isolated temp DB) + real
    PlanStore (isolated temp JSON file). Only PlanRunner (the deepest
    execution boundary — permission-gated district dispatch) is stubbed, and
    the three soft pre-execution safety checks are left REAL (Counterfactual/
    ThreatDetector/RedTeam) — mirroring test_task89c_goal_progress.py's and
    test_rr2_meaningful_utility.py's established convention of stubbing only
    the deepest execution boundary, not the bridge logic under test."""
    loop = AutonomousLoop()
    loop._plan_store = PlanStore(path=tmp_path / "plans.json")

    _StubPlanRunner.results = {}
    monkeypatch.setattr("core.runtime.plans.PlanRunner", _StubPlanRunner)

    return loop


@pytest.mark.unit
async def test_verified_partial_plan_progress_moves_goal_progress(loop_with_stub_plan_runner):
    """A verified first step of a two-step plan, reporting plan_progress=0.5,
    moves the linked goal's progress from 0.0 -> 0.5."""
    loop = loop_with_stub_plan_runner
    gs = loop._get_goals()
    goal_id = "g_daily_commit"
    before = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    assert before["progress"] == 0.0

    plan = make_two_step_plan(goal_id)
    loop._plan_store.add(plan)

    _StubPlanRunner.results["step-1"] = {
        "status": "completed",
        "verification_passed": True,
        "plan_progress": 0.5,
        "plan_status": "active",
    }
    winner = make_plan_step_winner(plan.id, "step-1", "research_topic", [goal_id])
    await loop._act_on(winner)

    after = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    print(f"[behavioral evidence] goal progress: {before['progress']} -> {after['progress']}")
    assert after["progress"] == 0.5
    assert after["status"] == "active"


@pytest.mark.unit
async def test_reprocessing_same_progress_does_not_double_count(loop_with_stub_plan_runner):
    """Re-running/re-processing the same already-accounted-for progress does
    not double-count or re-advance the goal's progress."""
    loop = loop_with_stub_plan_runner
    gs = loop._get_goals()
    goal_id = "g_daily_commit"

    plan = make_two_step_plan(goal_id)
    loop._plan_store.add(plan)

    verified_result = {
        "status": "completed",
        "verification_passed": True,
        "plan_progress": 0.5,
        "plan_status": "active",
    }
    _StubPlanRunner.results["step-1"] = verified_result
    winner = make_plan_step_winner(plan.id, "step-1", "research_topic", [goal_id])
    await loop._act_on(winner)

    first = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    assert first["progress"] == 0.5
    first_last_updated = first.get("last_updated")

    # Re-process the identical, non-increasing update.
    _StubPlanRunner.results["step-1"] = dict(verified_result)
    winner2 = make_plan_step_winner(plan.id, "step-1", "research_topic", [goal_id])
    await loop._act_on(winner2)

    second = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    print(
        f"[behavioral evidence] repeated identical update: progress stayed "
        f"{first['progress']} -> {second['progress']}"
    )
    assert second["progress"] == 0.5
    assert second.get("last_updated") == first_last_updated, (
        "goal must not be re-written when the new progress does not exceed current progress"
    )


@pytest.mark.unit
async def test_verification_failed_step_does_not_move_progress(loop_with_stub_plan_runner):
    """A step that executes but FAILS verification (verification_passed=False)
    must not move the linked goal's progress. Mirrors the real result shape
    PlanRunner.execute_step() actually returns for this case (core/runtime/
    plans.py: `elif report_status == "executed" and not passed: step.status =
    "failed"`) — an executed-but-failed-verification step is reported as
    status="failed", never "completed"."""
    loop = loop_with_stub_plan_runner
    gs = loop._get_goals()
    goal_id = "g_daily_commit"
    before = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    assert before["progress"] == 0.0

    plan = make_two_step_plan(goal_id)
    loop._plan_store.add(plan)

    _StubPlanRunner.results["step-1"] = {
        "status": "failed",
        "verification_passed": False,
        "plan_progress": 0.0,
        "plan_status": "active",
    }
    winner = make_plan_step_winner(plan.id, "step-1", "research_topic", [goal_id])
    await loop._act_on(winner)

    after = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    print(
        f"[behavioral evidence] verification_passed=False leaves progress at "
        f"prior value: {before['progress']} -> {after['progress']}"
    )
    assert after["progress"] == before["progress"] == 0.0


@pytest.mark.unit
async def test_plan_progress_1_0_does_not_auto_complete_goal(loop_with_stub_plan_runner):
    """A step reporting plan_progress == 1.0 does not auto-complete the goal
    through this bridge. 2026-09-23 fix: 1.0 is no longer excluded outright
    (that gave single-step plans zero contribution, ever); it's capped at
    PLAN_PROGRESS_GOAL_CAP (0.99) instead, so only GoalSystem's own explicit
    callers can still trigger the completed-status transition."""
    loop = loop_with_stub_plan_runner
    gs = loop._get_goals()
    goal_id = "g_daily_commit"
    before = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    assert before["progress"] == 0.0
    assert before["status"] == "active"

    plan = make_two_step_plan(goal_id)
    loop._plan_store.add(plan)

    _StubPlanRunner.results["step-1"] = {
        "status": "completed",
        "verification_passed": True,
        "plan_progress": 1.0,
        "plan_status": "completed",
    }
    winner = make_plan_step_winner(plan.id, "step-1", "research_topic", [goal_id])
    await loop._act_on(winner)

    after = next(
        (g for g in gs._goals if g["id"] == goal_id),
        None,
    )
    print(
        f"[behavioral evidence] plan_progress=1.0 does not flip goal status: "
        f"progress={after['progress']} status={after['status']}"
    )
    assert after["progress"] == 0.99
    assert after["status"] == "active"


@pytest.mark.unit
async def test_ordinary_action_success_still_does_not_move_goal_progress(loop_with_stub_plan_runner):
    """Task 89C control, re-proven alongside the new bridge: an ordinary
    successful _act_on() call with {"status": "ok"} — no plan, no
    verification field at all — still must not move ANY goal's progress
    (not just the one goal_id attached to this action; a regression that
    mutates an unrelated goal must also fail this test)."""
    loop = loop_with_stub_plan_runner
    gs = loop._get_goals()
    goal_id = "g_daily_commit"
    before_all = {g["id"]: g["progress"] for g in gs.get_active_goals()}
    assert before_all[goal_id] == 0.0

    fake_governor = MagicMock()
    fake_governor.dispatch = AsyncMock(return_value={"status": "ok"})
    loop._governor = fake_governor

    winner = Candidate(
        action_type="test_action_ordinary",
        params={},
        goal_ids=[goal_id],
        confidence=0.6,
        urgency=0.5,
        timing_score=1.0,
        estimated_cost_inr=0.0,
        # source deliberately does NOT start with "plan:" — this is the
        # ordinary native-action path, not the plan-step bridge.
    )
    await loop._act_on(winner)

    after_all = {g["id"]: g["progress"] for g in gs.get_active_goals()}
    print(
        f"[behavioral evidence] Task 89C control — ordinary status='ok' "
        f"action leaves ALL goals' progress unchanged: {before_all} -> {after_all}"
    )
    assert after_all == before_all, (
        "an ordinary successful action must not mutate ANY goal's progress, "
        "not just the one it declared goal_ids for"
    )
    after = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    assert after["progress"] == 0.0
    assert after["status"] == "active"


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "-s"],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    print("[OK] test_stage3_goal_progress" if result.returncode == 0 else "[FAILED] test_stage3_goal_progress")
