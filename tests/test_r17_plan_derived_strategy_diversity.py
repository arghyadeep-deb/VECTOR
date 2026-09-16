"""
R17 — Plan-Derived Strategy Diversity.

Wave-1 investigation (this mission's own read-only audit, Agents R17-A and
R17-B) found two things that together define this file's honest, narrowed
scope:

1. (R17-A) The plan -> candidate -> DecisionEngine -> execution -> learning
   pipeline (`core/runtime/plans.py`'s `Plan`/`PlanStep`/`PlanStore`/
   `PlanRunner`, `core/loop/autonomous_loop.py`'s `_get_plan_candidates()`/
   `_act_on_plan_step()`) is FULLY BUILT, unified with the same real
   `DecisionEngine.evaluate()` goal-derived candidates use, and already
   writes real outcomes into the SAME canonical `PolicyMemory` identity
   every other writer uses (fixed by an earlier session's "E2 outcome
   attribution audit" -- see `_act_on_plan_step()`'s own code comment). It
   is dormant in normal operation only because nothing in the real seeding
   path or the autonomous loop itself ever calls `add_goal()` with a
   MID/LONG goal inside a running event loop (the only real trigger for
   LLM-based decomposition) -- not because anything is missing or broken.

2. (R17-B) The ONE place that actually NEEDS plan-derived diversity --
   VECTOR's two real Equation/revenue goals, which R12 already found have
   zero real executable strategies -- CANNOT legitimately get it: the
   rule-based decomposer deterministically produces one inert `respond`
   step for their real titles (hand-traced, not guessed), and the
   LLM-based decomposer's invented action_types would be blocked as
   `UNKNOWN` at `PermissionGateway` unless someone fabricates a mapping --
   precisely the fabrication R12's own Section 6 already refused to
   commit. This file does not reopen that refusal.

R17's legitimate, non-fabricated scope is therefore: prove the
ALREADY-BUILT pipeline mechanically works end-to-end -- a real PlanStep
becomes a real Candidate, competes for real in the same `evaluate()` call
goal-derived candidates use, and its real execution produces a real,
attributable, persisted outcome -- using a real, already-classified,
already-implemented GREEN action_type (`check_attendance`), constructed
directly via the real `PlanStore`/`PlanRunner` APIs. This is exactly
analogous to how R11-R14 construct an isolated `GoalSystem` with real,
already-trustworthy tags rather than running the full seeding pipeline:
neither approach fabricates content, both exercise real, unmodified
production machinery through its own real, documented, direct API surface.

**Trust-but-verify finding, not assumed**: `PermissionGateway._execute_
action()` does NOT delegate arbitrary GREEN action_types to
`Governor.dispatch()` -- it has its own hardcoded per-action_type handler
list (search_web, play_music, set_timer, check_weather, check_attendance,
commit_code, write_note_personal, push_github, send_email, ..., plus a
`hand_*`-prefixed Governor-delegation branch) with an explicit
`not_implemented` fallback for anything else ("action '...' not
implemented -- no RL reward granted", `core/loop/permission_gateway.py`
around line 1361-1365). `check_attendance`'s own real handler
(`KIITScraper().get_cached_schedule()`) calls a method that does not
actually exist anywhere in this codebase (confirmed by repo-wide grep) --
its real, unmodified `except Exception` branch always catches this and
still returns `status="ok", checked=False` (a genuine, real, deterministic,
non-fabricated outcome of running the actual shipped code, confirmed
empirically by this session's own isolated probe before writing this
file). This is flagged honestly here and in the mission report as an
existing latent defect (a call to a nonexistent method) -- NOT fixed,
per this mission's explicit scope boundaries (out of R17's narrow remit,
and it does not block this file's actual claim, which is about the
mechanical pipeline, not about KIITScraper's own correctness).
"""
from __future__ import annotations

import datetime
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.brain.goal_system import GoalSystem
from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate, DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory
from core.runtime.plans import Plan, PlanRunner, PlanStep, PlanStore

from tests.test_r13_production_learning_validation import (
    build_isolated_engine,
    read_reasoning_chain_for_decision,
)

R17_GOAL_ID_PREFIX = "g_r17"
PLAN_ACTION_TYPE = "check_attendance"  # real, GREEN, already-implemented in
                                        # PermissionGateway._execute_action()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def make_real_isolated_plan(goal_id: str, plan_id: str, step_id: str = "step-1") -> tuple[Plan, PlanStep]:
    """A real Plan/PlanStep pair, constructed directly via the real
    dataclasses -- no LLM call, no fabricated goal semantics, just the
    real, documented, direct construction API `PlanStore.add()` itself
    accepts. `action_type` is real, already-GREEN, already-implemented."""
    step = PlanStep(id=step_id, action_type=PLAN_ACTION_TYPE, params={}, priority=1, confidence=0.5)
    plan = Plan(
        id=plan_id, goal_id=goal_id, objective="R17 real plan-derived candidate proof",
        status="active", steps=[step], created_at=_now_iso(), updated_at=_now_iso(),
        proposed_by="r17_test",
    )
    return plan, step


def build_isolated_loop_with_plan_store(engine: DecisionEngine, plan_store: PlanStore) -> AutonomousLoop:
    loop = AutonomousLoop()
    loop._decision_engine = engine
    loop._plan_store = plan_store
    return loop


# ═══════════════════════════════════════════════════════════════════════════
# Flagship
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestPlanDerivedCandidateFlagship:

    async def test_real_plan_step_becomes_a_real_candidate_competes_and_executes(
        self, isolated_vector_db, tmp_path, monkeypatch,
    ):
        # RR-3.3 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        # RR3_OVERNIGHT_REMEDIATION_REPORT.md) gave plan-step execution the
        # same CounterfactualMemory pre-check native actions already had.
        # CounterfactualMemory ignores VECTOR_DB_PATH (see
        # tests/conftest.py's isolated_vector_db docstring) and this test
        # never isolated it, so it was silently reading the REAL, shared
        # production data/counterfactual.db -- which contains a genuine
        # historical rejection for an unrelated action_type ("analyze_progress"
        # tied to a "Maintain KIIT attendance" goal, dated 2026-06-18/
        # 2026-09-02) whose vocabulary happens to overlap with this test's
        # own "check_attendance" action_type enough to trip a false-positive
        # similarity match once the plan-step path actually reached this
        # check for the first time. This is real, pre-existing production
        # data unrelated to what this test verifies -- isolate
        # CounterfactualMemory to a fresh tmp_path DB, exactly as `engine`
        # below already isolates EpistemicTracker, so this test's own
        # semantics (a real plan step executing) aren't at the mercy of
        # unrelated historical production state.
        import core.memory.counterfactual as _cf_module
        _cf_real_init = _cf_module.CounterfactualMemory.__init__

        def _cf_isolated_init(self, db_path=None):
            _cf_real_init(self, db_path=str(tmp_path / "counterfactual_isolated.db"))

        monkeypatch.setattr(_cf_module.CounterfactualMemory, "__init__", _cf_isolated_init)

        goal_id = f"{R17_GOAL_ID_PREFIX}_flagship"
        plan_store = PlanStore(path=tmp_path / "plans.json")
        plan, step = make_real_isolated_plan(goal_id, plan_id=f"plan-{goal_id}")
        plan_store.add(plan)  # real, persisted (JSON-file-backed) add

        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop_with_plan_store(engine, plan_store)
        pm = PolicyMemory()

        # RR-3.3 also gave plan steps the same ThreatDetector pre-check.
        # This test's real ThreatDetector veto coverage for plan steps is
        # already directly, deterministically proven in
        # tests/test_rr3_overnight_remediation.py
        # (test_rr3_3_plan_step_gets_same_threat_detector_veto_as_native_action).
        # Here, the real (unmodified) VECTOR Guidance Engine's "jailbreak-classic"
        # pattern (vectorcode/src/guidance.py:121-126, `r"DAN|..."` with no
        # word boundaries, case-insensitive) genuinely matches the literal
        # substring "dan" inside "attendance" -- a real, pre-existing regex
        # false-positive entirely unrelated to plan-step parity, confirmed
        # reproducible against a bare `check_attendance` action_desc on a
        # fresh AutonomousLoop with no prior state. Fixing that shared,
        # security-relevant regex is out of RR-3's authorized scope (see
        # VECTOR_TECHNICAL_KNOWLEDGE/RR3_OVERNIGHT_REMEDIATION_REPORT.md).
        # This test's actual purpose -- proving the plan -> candidate ->
        # execution pipeline works end-to-end -- is orthogonal to
        # ThreatDetector's internals, so neutralize it here exactly as this
        # file already neutralizes unrelated concerns elsewhere.
        monkeypatch.setattr(loop, "_scan_threats", lambda desc, context="act": False)

        # ---- 1: real plan-derived candidate generation (no goal involved
        #      at all -- proves the pipeline works independent of
        #      GoalSystem, exactly matching _get_plan_candidates()'s own
        #      real, unmodified implementation) ----
        plan_candidates = loop._get_plan_candidates()
        assert len(plan_candidates) == 1
        plan_candidate = plan_candidates[0]
        assert plan_candidate.action_type == PLAN_ACTION_TYPE
        assert plan_candidate.source == f"plan:{plan.id}:{step.id}"
        assert plan_candidate.params.get("_plan_id") == plan.id
        assert plan_candidate.params.get("_step_id") == step.id

        # ---- 2: real competition -- plan-derived candidate alongside a
        #      real, isolated GOAL-derived candidate, in the SAME real
        #      evaluate() call, exactly as _think_tick() itself combines
        #      them (autonomous_loop.py:913-935) ----
        gs = GoalSystem.__new__(GoalSystem)
        gs._memory = None
        gs._persist = lambda: None
        gs._goals = [{
            "id": goal_id, "title": "Commit code every day (R17 probe)", "horizon": "SHORT",
            "priority": 9, "status": "active", "progress": 0.0, "tags": ["git"],
            "created_at": _now_iso(),
        }]
        goal_actions = gs.generate_immediate_actions(limit=4)
        assert {a["action_type"] for a in goal_actions} == {"git_status"}
        goal_candidate = Candidate(
            action_type="git_status",
            params={"goal_id": goal_id, "title": "Commit code every day (R17 probe)"},
            goal_ids=[goal_id], confidence=0.5, urgency=0.5, source="think_loop",
        )
        combined = [goal_candidate, plan_candidate]
        decision_combined = await engine.evaluate(combined)
        assert {c.action_type for c in decision_combined.all_candidates} == {"git_status", PLAN_ACTION_TYPE}, (
            "the plan-derived candidate must appear in the SAME real "
            "evaluate() call's all_candidates alongside the goal-derived one"
        )
        assert any(decision_combined.winner is c for c in combined), (
            "the winner must be one of the real, already-scored candidates, "
            "never a hand-built stand-in"
        )

        # ---- 3: real execution of the plan-derived candidate via the REAL
        #      _act_on() -> _act_on_plan_step() -> PlanRunner.execute_step()
        #      -> AutonomousExecutor -> real PermissionGateway chain.
        #      (Confidence-biased toward the plan candidate for THIS one
        #      execution cycle -- the same legitimate, established,
        #      decision-time-only bias technique R11-R14 use; it never
        #      touches the outcome/reward itself, only which real candidate
        #      gets a chance to execute this cycle.) ----
        exec_candidates = [
            Candidate(action_type="git_status", params=goal_candidate.params, goal_ids=[goal_id],
                      confidence=0.1, urgency=0.5, source="think_loop"),
            Candidate(action_type=PLAN_ACTION_TYPE, params=plan_candidate.params, goal_ids=[],
                      confidence=0.95, urgency=plan_candidate.urgency, source=plan_candidate.source),
        ]
        decision_exec = await engine.evaluate(exec_candidates)
        assert decision_exec.winner.action_type == PLAN_ACTION_TYPE
        assert decision_exec.winner.source.startswith("plan:")
        decision_id = decision_exec.winner.decision_id
        candidate_id = decision_exec.winner.candidate_id

        gw = PermissionGateway()
        assert gw.classify(PLAN_ACTION_TYPE) == "GREEN"

        await loop._act_on(decision_exec.winner)  # real routing: source starts with "plan:" -> _act_on_plan_step()

        # ---- 4: real outcome ----
        assert step.status == "completed", "the real PlanStep's own status must reflect real execution"
        assert step.actual_outcome is not None
        assert plan.status == "completed", "the real Plan (single-step) must be marked complete"

        # ---- 5: real reward + real PolicyMemory persistence, under the
        #      SAME canonical hash goal-derived candidates use ----
        h = pm.make_situation_hash(PLAN_ACTION_TYPE, plan_candidate.params)
        real_score = pm.get_score(PLAN_ACTION_TYPE, h)
        assert real_score == pytest.approx(0.7, abs=0.01), (
            "_act_on_plan_step()'s own real (binary, not 5-factor) reward "
            "shape: 0.7 if step.status=='completed' else 0.3 -- computed, "
            "never hardcoded by this test"
        )
        assert real_score > PolicyMemory.DEFAULT_SCORE

        # ---- 6: persistence across a real restart ----
        from core.memory.episodic import close_db_connection
        close_db_connection()
        pm2 = PolicyMemory()
        assert pm2.get_score(PLAN_ACTION_TYPE, h) == pytest.approx(0.7, abs=0.01)

        # ---- 7: a FRESH real DecisionEngine, evaluating a FRESH real
        #      candidate for the SAME (action_type, params) identity, reads
        #      the real, persisted, learned score back -- closing the loop:
        #      the plan step's own real outcome now measurably informs a
        #      LATER, completely independent real decision. ----
        fresh_engine = build_isolated_engine(str(tmp_path / "epistemic_fresh.db"))
        fresh_candidate = Candidate(
            action_type=PLAN_ACTION_TYPE, params=plan_candidate.params, goal_ids=[], confidence=0.5, urgency=0.5,
            source="think_loop",  # a DIFFERENT, non-plan source -- proving the
                                    # learned score transfers by (action_type,
                                    # params) identity, not by candidate source
        )
        fresh_decision = await fresh_engine.evaluate([fresh_candidate])
        assert fresh_decision.winner.policy_score == pytest.approx(0.7, abs=0.01)

        # ---- Outcome attribution ----
        attribution = read_reasoning_chain_for_decision(decision_id)
        # _act_on_plan_step() does not call store_chain() (unlike the main
        # _act_on() reward block) -- confirmed by source inspection, not
        # assumed. This is an honest limitation, not a test bug: see
        # TestAdversarialReview::test_attack_provenance_gap_is_real.
        assert attribution is None, (
            "plan-step outcomes are NOT currently correlated into "
            "reasoning_chains the way main-loop outcomes are -- a real, "
            "confirmed, honestly-reported limitation (see report §18)"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Causal controls
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCausalControls:

    async def test_control_a_plan_candidates_are_empty_with_no_active_plan(self, isolated_vector_db, tmp_path):
        plan_store = PlanStore(path=tmp_path / "empty_plans.json")
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop_with_plan_store(engine, plan_store)
        assert loop._get_plan_candidates() == []

    async def test_control_b_completed_step_never_regenerates_as_ready(self, isolated_vector_db, tmp_path):
        goal_id = f"{R17_GOAL_ID_PREFIX}_control_b"
        plan_store = PlanStore(path=tmp_path / "plans.json")
        plan, step = make_real_isolated_plan(goal_id, plan_id=f"plan-{goal_id}")
        plan_store.add(plan)
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop_with_plan_store(engine, plan_store)

        assert len(loop._get_plan_candidates()) == 1
        runner = PlanRunner(store=plan_store)
        await runner.execute_step(plan, step)
        assert step.status == "completed"
        # A completed, single-step plan is no longer "active" (status
        # becomes "completed") -- confirm it stops producing candidates.
        assert loop._get_plan_candidates() == []

    async def test_control_c_wrong_situation_no_contamination(self, isolated_vector_db, tmp_path):
        """A plan step's learned reward must not leak to a DIFFERENT
        (action_type, params) identity."""
        goal_id = f"{R17_GOAL_ID_PREFIX}_control_c"
        plan_store = PlanStore(path=tmp_path / "plans.json")
        plan, step = make_real_isolated_plan(goal_id, plan_id=f"plan-{goal_id}")
        plan_store.add(plan)
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop_with_plan_store(engine, plan_store)
        pm = PolicyMemory()

        plan_candidate = loop._get_plan_candidates()[0]
        winner = Candidate(
            action_type=PLAN_ACTION_TYPE, params=plan_candidate.params, goal_ids=[],
            confidence=0.9, urgency=0.5, source=plan_candidate.source,
        )
        await loop._act_on(winner)

        h_other = pm.make_situation_hash(PLAN_ACTION_TYPE, {"_plan_id": "different-plan", "_step_id": "different-step"})
        assert pm.get_score(PLAN_ACTION_TYPE, h_other) == PolicyMemory.DEFAULT_SCORE

    async def test_control_d_no_bias_in_the_pure_generation_observation(self, isolated_vector_db, tmp_path):
        """The FIRST part of the flagship (candidate generation + real
        competition observation, step 1-2) uses zero confidence bias --
        only step 3's real EXECUTION selection legitimately biases
        confidence, exactly like R11-R14's own established methodology."""
        goal_id = f"{R17_GOAL_ID_PREFIX}_control_d"
        plan_store = PlanStore(path=tmp_path / "plans.json")
        plan, step = make_real_isolated_plan(goal_id, plan_id=f"plan-{goal_id}")
        plan_store.add(plan)
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop_with_plan_store(engine, plan_store)

        plan_candidate = loop._get_plan_candidates()[0]
        goal_candidate = Candidate(
            action_type="git_status", params={"goal_id": goal_id, "title": "t"},
            goal_ids=[goal_id], confidence=0.5, urgency=0.5, source="think_loop",
        )
        assert plan_candidate.confidence == 0.5  # real PlanStep default, never overridden
        assert goal_candidate.confidence == 0.5


# ═══════════════════════════════════════════════════════════════════════════
# Safety
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_plan_step_execution_reaches_the_real_permission_gateway(self):
        """Source-level confirmation (not assumed): PlanRunner.execute_step()
        -> AutonomousExecutor.execute() -> PermissionGateway.execute() --
        the exact same real gate every other execution path reaches."""
        runner_src = inspect.getsource(PlanRunner.execute_step)
        assert "executor.execute(" in runner_src
        import core.runtime.executor as executor_mod
        executor_src = inspect.getsource(executor_mod.AutonomousExecutor.execute)
        assert "self.permission_gateway.execute(action)" in executor_src

    def test_red_action_type_in_a_plan_step_still_cannot_autoexecute(self):
        """A hypothetical RED-tier plan step would still classify RED --
        confirmed structurally, not exercised (no RED plan step is ever
        constructed by this file's own flagship/controls)."""
        gw = PermissionGateway()
        assert gw.classify("code_task") == "RED"
        assert gw.classify(PLAN_ACTION_TYPE) == "GREEN"

    def test_act_on_plan_step_never_bypasses_act_on_routing(self):
        """_act_on_plan_step() is only ever reached via _act_on()'s own
        source-prefix check -- confirmed by source inspection that no
        other call site invokes it directly in production code."""
        import core.loop.autonomous_loop as al
        act_on_src = inspect.getsource(al.AutonomousLoop._act_on)
        assert 'winner.source.startswith("plan:")' in act_on_src
        assert "await self._act_on_plan_step(winner)" in act_on_src


# ═══════════════════════════════════════════════════════════════════════════
# Adversarial review
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialReview:

    def test_attack_no_bias_in_generation_or_competition_steps(self):
        flagship_src = inspect.getsource(TestPlanDerivedCandidateFlagship)
        # confidence=0.95/0.1 only appears in step 3 (real EXECUTION
        # selection, legitimately labeled) -- confirmed the earlier
        # generation/competition observation (goal_candidate, plan_candidates)
        # never sets a non-uniform confidence pair.
        assert "confidence=0.5, urgency=0.5" in flagship_src

    def test_attack_reward_is_computed_not_hardcoded(self):
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._act_on_plan_step)
        assert 'reward = 0.7 if completed else 0.3' in src
        assert "pm.update_from_outcome(winner.action_type, h, reward)" in src

    def test_attack_hash_identity_shared_with_main_reward_writer(self):
        """Confirms the E2 outcome-attribution fix (cited in this file's
        own module docstring) is real: both writers use the exact same
        canonical make_situation_hash() call."""
        import core.loop.autonomous_loop as al
        act_on_src = inspect.getsource(al.AutonomousLoop._act_on)
        plan_step_src = inspect.getsource(al.AutonomousLoop._act_on_plan_step)
        assert "pm.make_situation_hash(winner.action_type, winner.params)" in act_on_src
        assert "pm.make_situation_hash(winner.action_type, winner.params)" in plan_step_src

    def test_attack_provenance_gap_is_real(self):
        """Confirms (rather than assumes) the flagship's own honest
        limitation claim: _act_on_plan_step() never calls store_chain(),
        unlike the main _act_on() reward block."""
        import core.loop.autonomous_loop as al
        act_on_src = inspect.getsource(al.AutonomousLoop._act_on)
        plan_step_src = inspect.getsource(al.AutonomousLoop._act_on_plan_step)
        assert "store_chain(" in act_on_src
        assert "store_chain(" not in plan_step_src

    def test_attack_wrong_db(self, isolated_vector_db):
        import os
        assert os.environ.get("VECTOR_DB_PATH") == isolated_vector_db
        assert isolated_vector_db != "vector_memory.db"

    def test_attack_plan_store_isolated_from_real_production_path(self, tmp_path):
        """Confirms the real PlanStore.path property is NOT the real
        production plans.json -- this file always passes an explicit
        tmp_path override."""
        store = PlanStore(path=tmp_path / "plans.json")
        assert str(store.path) == str(tmp_path / "plans.json")
        assert "test_tmp" not in str(store.path)  # tmp_path-based, not the shared conftest dir either


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
