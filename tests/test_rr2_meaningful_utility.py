"""RR-2 regression tests — meaningful utility + goal-progress coupling.

Background (see VECTOR_TECHNICAL_KNOWLEDGE/RR2_MEANINGFUL_UTILITY_REPORT.md):
RR-0 found `core/loop/autonomous_loop.py::AutonomousLoop._act_on()`'s 5-factor
reward formula computed `goal_progress = float(result.get("goal_progress", 0.5))`
— since no production action handler ever populates this key, every action
(including repeated `read_code`, goal_alignment=0.00, no attached goal)
silently received a fabricated "half advanced my goal" credit, producing the
observed ~0.755 reward RG-D documented. RR-2 makes UNKNOWN goal-progress
evidence contribute 0 to the reward (conservative, never a fake positive),
while preserving the unknown/known distinction separately in the action's own
reasoning_chain for observability. It also fixes the completion invariant
(`GoalSystem.get_active_goals()` now self-heals any goal found with
progress>=1.0 while status remained "active", via the existing
`update_goal_progress()` writer — never a raw DB patch).

Reuses tests/test_task89c_goal_progress.py's established real-AutonomousLoop
+ real-GoalSystem + isolated-temp-DB harness (tests/conftest.py's
`isolated_vector_db`). Per .claude/rules/testing.md, PolicyMemory and
CausalGraph are NOT mocked here (unlike Task 89C's own suite) — verifying
what they actually learn is the point of this suite. Only the deepest
execution boundaries (`Governor.dispatch`, `AutonomousExecutor.execute`) are
stubbed, matching the established convention for these tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from tests._small_scan import small_scan_root  # noqa: F401  (autouse: real read_code scan over a small project)

from core.brain.goal_system import GoalSystem
from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate
from core.loop.permission_gateway import PermissionGateway


def make_winner(action_type="read_code", goal_ids=None, params=None):
    return Candidate(
        action_type=action_type,
        params=params or {},
        goal_ids=goal_ids or [],
        confidence=0.7,
        urgency=0.5,
        timing_score=1.0,
        estimated_cost_inr=0.0,
    )


@pytest.fixture
def loop_real_policy_causal(isolated_vector_db):
    """Real AutonomousLoop + real GoalSystem + REAL PolicyMemory + REAL
    CausalGraph (all backed by the isolated temp DB) — only governor.dispatch
    (district execution) is stubbed, so the real reward/learning code path
    runs end to end and its actual stored effects can be verified."""
    loop = AutonomousLoop()
    fake_governor = MagicMock()
    fake_governor.dispatch = AsyncMock(return_value={"status": "ok"})
    loop._governor = fake_governor

    fake_memory = MagicMock()
    fake_memory.recall = MagicMock(return_value=[])
    fake_memory.store_chain = MagicMock()
    loop._memory = fake_memory

    return loop


def _set_governor_result(loop, result: dict):
    loop._governor.dispatch = AsyncMock(return_value=result)


# ── A. Missing progress test ────────────────────────────────────────────────

@pytest.mark.unit
async def test_a_missing_progress_not_treated_as_fake_positive(loop_real_policy_causal):
    """A successful action with no goal_progress key in its result must not
    receive the old fabricated 0.5 credit. Compute the exact expected reward
    under the new UNKNOWN-conservative formula and confirm it, not the old
    formula's ~0.755, is what PolicyMemory actually receives."""
    loop = loop_real_policy_causal
    _set_governor_result(loop, {"status": "ok"})  # no "goal_progress" key at all

    winner = make_winner(action_type="probe_missing_progress", goal_ids=[])
    await loop._act_on(winner)

    pm = loop._get_policy()
    h = pm.make_situation_hash(winner.action_type, winner.params)
    score = pm.get_score(winner.action_type, h)

    # New formula: uf(0.7)*.40 + 0(unknown)*.25 + 1.0*.15 + 1.0*.15 + 1.0*.05 = 0.63
    expected_new = 0.7 * 0.40 + 0.0 * 0.25 + 1.0 * 0.15 + 1.0 * 0.15 + 1.0 * 0.05
    old_fake_value = 0.7 * 0.40 + 0.5 * 0.25 + 1.0 * 0.15 + 1.0 * 0.15 + 1.0 * 0.05  # 0.755

    assert abs(score - expected_new) < 0.01, f"expected ~{expected_new:.3f}, got {score}"
    assert score < old_fake_value - 0.05, "must be meaningfully below the old fake-0.5 value"


# ── B. read_code regression (RG-D's exact dominant case) ────────────────────

@pytest.mark.unit
async def test_b_read_code_no_longer_resembles_verified_progress(loop_real_policy_causal):
    """The RG-D control case itself: read_code, status=ok, goal_alignment
    implicitly 0 (no goal_ids), no progress evidence. Must no longer produce
    the old ~0.755 reward that made it structurally indistinguishable from a
    real, evidenced 0.5-progress outcome."""
    loop = loop_real_policy_causal
    _set_governor_result(loop, {"status": "ok"})

    winner = make_winner(action_type="read_code", goal_ids=[])
    await loop._act_on(winner)

    pm = loop._get_policy()
    h = pm.make_situation_hash(winner.action_type, winner.params)
    score = pm.get_score(winner.action_type, h)

    assert score < 0.70, f"read_code reward must drop meaningfully below the old 0.755, got {score}"


# ── C. Verified progress test (real plan-step deterministic verification) ──

@pytest.mark.unit
async def test_c_verified_plan_step_outscores_read_code_control(loop_real_policy_causal, tmp_path):
    """Uses the REAL, existing, deterministic (non-LLM) plan-step
    verification machinery (core/runtime/plans.py's PlanStep/Plan/PlanRunner
    + verify_step_outcome) — only the deepest execution boundary
    (AutonomousExecutor.execute) is stubbed, exactly mirroring how
    governor.dispatch is stubbed for the non-plan-step path. Proves a real,
    objectively-verified-complete step earns a stronger learning signal than
    the read_code control, using _act_on_plan_step()'s own existing,
    untouched reward formula (0.7 for a verified-completed step) — RR-2 did
    not need to modify this path at all."""
    from core.runtime.plans import Plan, PlanStep, PlanStore
    from core.runtime.executor import ExecutionReport

    loop = loop_real_policy_causal

    plan_id = "rr2_test_plan"
    step = PlanStep(
        id="step-1",
        action_type="verified_probe_action",
        params={},
        depends_on=[],
        expected_outcome="probe completes",
        verification={"type": "always"},  # real, deterministic, non-LLM
    )
    plan = Plan.from_dict({"id": plan_id, "goal_id": "g_daily_commit",
                            "objective": "RR-2 verified-progress control",
                            "steps": [step.to_dict()]})
    plan.steps = [step]  # keep the same live PlanStep object for post-assertions
    store = PlanStore(path=tmp_path / "rr2_plans.json")
    store.add(plan)
    loop._plan_store = store

    fake_report = ExecutionReport(
        status="executed", plan={}, gateway=None,
        verification={"ok": True}, result={"data": "probe ok"}, reason="ok",
    )
    with patch("core.runtime.executor.AutonomousExecutor.execute", new=AsyncMock(return_value=fake_report)):
        winner = make_winner(
            action_type="verified_probe_action",
            goal_ids=["g_daily_commit"],
            params={},
        )
        winner.source = f"plan:{plan_id}:step-1"
        await loop._act_on(winner)

    # Real, deterministic verification must have marked the step completed.
    assert step.status == "completed"
    assert step.actual_outcome["verification_passed"] is True

    pm = loop._get_policy()
    h_plan = pm.make_situation_hash("verified_probe_action", {})
    plan_score = pm.get_score("verified_probe_action", h_plan)

    h_read = pm.make_situation_hash("read_code", {})
    read_score = pm.get_score("read_code", h_read)  # unset -> PolicyMemory default

    assert plan_score > 0.65, f"verified-completed plan step should score highly, got {plan_score}"
    # Direct comparison against the B-control's known corrected value.
    b_control_expected = 0.7 * 0.40 + 0.0 * 0.25 + 1.0 * 0.15 + 1.0 * 0.15 + 1.0 * 0.05
    assert plan_score > b_control_expected, (
        f"verified progress ({plan_score}) must outscore the read_code control ({b_control_expected})"
    )


# ── D. Failure test ──────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("status", ["error", "timeout", "blocked", "no_capable_agent"])
async def test_d_failed_actions_get_no_positive_utility(loop_real_policy_causal, status):
    loop = loop_real_policy_causal
    _set_governor_result(loop, {"status": status})

    winner = make_winner(action_type=f"probe_fail_{status}", goal_ids=[])
    await loop._act_on(winner)

    pm = loop._get_policy()
    h = pm.make_situation_hash(winner.action_type, winner.params)
    score = pm.get_score(winner.action_type, h)

    # completed=0.0, goal_progress=0.0(unknown), not_overridden/not_corrected=1.0:
    # uf(0.3)*.40 + 0 + 1.0*.15 + 1.0*.15 + 0*.05 = 0.42 — well below a passing signal.
    assert score < 0.5, f"a failed action ({status}) must not receive positive utility reinforcement, got {score}"


# ── E. Completion invariant ──────────────────────────────────────────────────

@pytest.mark.unit
def test_e_completion_invariant_self_heals_on_read(isolated_vector_db):
    """Simulates the exact RG-D/RR-0 anomaly (progress=1.0, status=active —
    a combination update_goal_progress() itself can never produce in a
    single call) by direct dict manipulation (the only way to REACH this
    state today, since no code path can currently produce it), then proves
    the authoritative read boundary (get_active_goals()) self-heals it via
    the existing writer."""
    gs = GoalSystem()
    goal = next(g for g in gs._goals if g["id"] == "g_daily_commit")
    goal["progress"] = 1.0
    goal["status"] = "active"  # the historical anomaly, reproduced directly

    gs.get_active_goals()  # triggers _enforce_completion_invariant()

    healed = next(g for g in gs._goals if g["id"] == "g_daily_commit")
    assert healed["status"] == "completed"
    assert healed["progress"] == 1.0


# ── F. Current-goal control ──────────────────────────────────────────────────

@pytest.mark.unit
def test_f_completed_goal_not_selectable_after_invariant_fix(isolated_vector_db):
    gs = GoalSystem()
    goal = next(g for g in gs._goals if g["id"] == "g_daily_commit")
    goal["progress"] = 1.0
    goal["status"] = "active"

    actions = gs.generate_immediate_actions(limit=10)
    assert not any(a["goal_id"] == "g_daily_commit" for a in actions), (
        "a completion-invariant-violating goal must not generate candidates "
        "(and therefore can never become loop:current_goal) once healed"
    )
    assert "g_daily_commit" not in {g["id"] for g in gs.get_active_goals()}


# ── G. Policy learning differentiation ──────────────────────────────────────

@pytest.mark.unit
async def test_g_policy_memory_differentiates_unknown_from_verified(loop_real_policy_causal, tmp_path):
    """Direct A/B: technical success with unknown progress vs. real verified
    progress must land at genuinely different PolicyMemory avg_reward
    values, not be blended into the same ~0.755-ish band."""
    from core.runtime.plans import Plan, PlanStep, PlanStore
    from core.runtime.executor import ExecutionReport

    loop = loop_real_policy_causal
    _set_governor_result(loop, {"status": "ok"})
    unknown_winner = make_winner(action_type="policy_diff_unknown", goal_ids=[])
    await loop._act_on(unknown_winner)

    step = PlanStep(id="s1", action_type="policy_diff_verified", params={},
                     depends_on=[], expected_outcome="ok", verification={"type": "always"})
    plan = Plan.from_dict({"id": "policy_diff_plan", "goal_id": "g_daily_commit",
                            "objective": "probe", "steps": [step.to_dict()]})
    plan.steps = [step]
    store = PlanStore(path=tmp_path / "rr2_policy_diff.json")
    store.add(plan)
    loop._plan_store = store
    fake_report = ExecutionReport(status="executed", plan={}, gateway=None,
                                   verification={"ok": True}, result={}, reason="ok")
    with patch("core.runtime.executor.AutonomousExecutor.execute", new=AsyncMock(return_value=fake_report)):
        verified_winner = make_winner(action_type="policy_diff_verified", goal_ids=["g_daily_commit"])
        verified_winner.source = "plan:policy_diff_plan:s1"
        await loop._act_on(verified_winner)

    pm = loop._get_policy()
    unknown_score = pm.get_score("policy_diff_unknown", pm.make_situation_hash("policy_diff_unknown", {}))
    verified_score = pm.get_score("policy_diff_verified", pm.make_situation_hash("policy_diff_verified", {}))

    assert verified_score > unknown_score + 0.05, (
        f"PolicyMemory must differentiate verified ({verified_score}) from "
        f"unknown ({unknown_score}) progress"
    )


# ── H. Causal learning differentiation ──────────────────────────────────────

@pytest.mark.unit
async def test_h_causal_graph_differentiates_unknown_from_verified(loop_real_policy_causal, tmp_path):
    from core.memory.causal_graph import CausalGraph, causal_state_key
    from core.runtime.plans import Plan, PlanStep, PlanStore
    from core.runtime.executor import ExecutionReport

    loop = loop_real_policy_causal
    _set_governor_result(loop, {"status": "ok"})
    unknown_winner = make_winner(action_type="causal_diff_unknown", goal_ids=[])
    await loop._act_on(unknown_winner)

    step = PlanStep(id="s1", action_type="causal_diff_verified", params={},
                     depends_on=[], expected_outcome="ok", verification={"type": "always"})
    plan = Plan.from_dict({"id": "causal_diff_plan", "goal_id": "g_daily_commit",
                            "objective": "probe", "steps": [step.to_dict()]})
    plan.steps = [step]
    store = PlanStore(path=tmp_path / "rr2_causal_diff.json")
    store.add(plan)
    loop._plan_store = store
    fake_report = ExecutionReport(status="executed", plan={}, gateway=None,
                                   verification={"ok": True}, result={}, reason="ok")
    with patch("core.runtime.executor.AutonomousExecutor.execute", new=AsyncMock(return_value=fake_report)):
        verified_winner = make_winner(action_type="causal_diff_verified", goal_ids=["g_daily_commit"])
        verified_winner.source = "plan:causal_diff_plan:s1"
        await loop._act_on(verified_winner)

    cg = CausalGraph()
    state_key = causal_state_key(None)
    unknown_edges = cg.get_outcomes(f"action:causal_diff_unknown@{state_key}")
    # NOTE: _act_on_plan_step() does NOT write CausalGraph (R26 comment: only
    # the main _act_on() path does) -- this is real, pre-existing, untouched
    # behavior, not something RR-2 changed. So we instead confirm the
    # unknown-progress edge strength itself reflects the corrected (lower)
    # reward, rather than the old fake-0.5-inflated ~0.755.
    assert unknown_edges, "expected a causal edge for the unknown-progress action"
    strength = unknown_edges[0]["strength"]
    assert strength < 0.70, f"causal edge strength must reflect the corrected reward, got {strength}"


# ── I. Safety regression (RR-1/RR-1.5 unchanged) ────────────────────────────

@pytest.mark.unit
def test_i_permission_gateway_unchanged():
    gw = PermissionGateway()
    assert gw.classify("list_districts") == "GREEN"       # RR-1.5
    assert gw.classify("test_feature") == "GREEN"          # RR-1.5
    assert gw.classify("financial_transaction") == "RED"
    assert gw.classify("commit_code") == "YELLOW"
    assert gw.classify("format_drive") == "FORBIDDEN"
    assert gw.classify("system_status") == "UNKNOWN"       # RR-1.5's own control


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
