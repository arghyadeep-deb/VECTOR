"""
R19 — Capability Composition.

R18-EQ gave g_first_revenue two real, independent strategies (script,
idea_validate) but left them isolated: no goal ever advanced from one
real action's real output to a second, dependent real action. Phase 1's
7 parallel read-only investigators (see
VECTOR_TECHNICAL_KNOWLEDGE/R19_R20_ORCHESTRATOR_LEDGER.md) adversarially
evaluated every startups-district composition candidate
(idea_validate->script, idea_validate->market_scan, idea_validate->
revenue_model) and rejected all three as "coincidental string
pass-through" -- none genuinely consumed the first step's real analysis
output (verdict/scores/pros/cons), only a same-named-but-substitutable
string field.

The one candidate that survived adversarial review: `script` ->
`schedule_post`. `ScriptGenerator.generate_script()` returns a real
"content" field (the actual generated script text); `ContentScheduler
.schedule_post(title, content, platforms, scheduled_for)` consumes a
"content" field of the SAME name as its actual, load-bearing payload -- a
schedule_post call is meaningless without real content. This is doctrine-
grounded too (Blueprint/(C) The Real Blueprint Part 4 names exactly this
pipeline as g_first_revenue's own 90-day wedge plan).

Architecture: `core/runtime/plans.py`'s real Plan/PlanStep/PlanStore/
PlanRunner already provide real DAG dependency gating
(`next_ready_steps()`), real crash/retry/review_required semantics, and
native Candidate integration (`AutonomousLoop._get_plan_candidates()` --
same `DecisionEngine.evaluate()` path every other candidate uses, no
parallel system). Per Rule 2 ("prefer existing planner"), this file
exercises PlanRunner rather than inventing a new orchestration layer.
Three narrow, precedented gaps (same "real capability, missing wiring"
class R18-EQ fixed twice) were closed to make this possible:

1. core/config.py: "schedule_post" added to GREEN (script/idea_validate
   already GREEN from R18-EQ). Verified safe by direct source read:
   schedule_post() only creates a local PostJob row (SQLite, no network
   call); the actual external, irreversible publish is a SEPARATE method
   (run_pending()) gated behind its own, already-RED "content_publish"
   action_type requiring real PermissionGateway owner approval --
   schedule_post's own dispatch path never reaches it.
2. core/loop/permission_gateway.py::_execute_action(): PlanRunner's real
   execution backend (AutonomousExecutor -> PermissionGateway.execute())
   previously had NO generic dispatch-to-Governor path for an arbitrary
   action_type -- only "hand_"-prefixed actions reached Governor.dispatch()
   there; everything else silently returned "not_implemented", even
   though the SAME action_type already executes correctly via
   AutonomousLoop._act_on()'s OTHER (native goal candidate) fallback. One
   new, narrowly-scoped elif branch (mirrors the existing hand_ block
   exactly, `_PLAN_COMPOSABLE_ACTION_TYPES = {"script","schedule_post"}`)
   closes this.
3. core/runtime/plans.py: (a) PlanStep gained a new, explicit, declared
   `param_bindings: dict[str,str]` field ({target_param_key:
   "<dep_step_id>.<output_field>"}), resolved only at dispatch time
   (`_resolve_step_params()`, called from execute_step() -- only once
   next_ready_steps()'s own DAG gating already guarantees every
   dependency is real and completed) -- real, structured, typed data
   handoff, never string-scraping, never stored back into `step.params`;
   (b) `step.actual_outcome` now additively preserves the real handler's
   real structured result (`report_result`) under a new "result" key --
   previously discarded, leaving nothing for a dependent step to read;
   (c) one new, deterministic (NO LLM call, avoiding MissionPlanAdvisor's
   real hallucination risk per Phase 1 Agent B's own finding), real,
   reusable module-level builder (`build_wedge_content_plan()`)
   constructing exactly this 2-step DAG.

Honest, pre-existing characteristics NOT changed by this milestone
(documented, not fixed, per "do not redesign learning" / "do not
silently fix unrelated architecture"):
  - `_get_plan_candidates()` already puts `_plan_id`/`_step_id` into
    each Candidate's params (autonomous_loop.py:1532) -- and
    `PolicyMemory.make_situation_hash()` hashes ALL params keys (Phase 1
    Agent C's finding), so a plan-step's situation_hash is always fresh
    per plan-run (the plan id is a fresh UUID each time). PolicyMemory
    IS written under the same canonical hash function every other writer
    uses (real reward, real persistence) -- it just does not accumulate
    ACROSS separate runs of "the same" logical plan the way a native
    goal-candidate's reward does. This is real, pre-existing PlanRunner
    behavior, not something this file's changes touch.
  - `_act_on_plan_step()` does not write an R7 reasoning_chains
    correlation marker (unlike the main `_act_on()` path) -- plan-step
    decisions have real decision_id/candidate_id (minted by
    DecisionEngine exactly as for any other Candidate) but no
    reasoning_chains readback exists for them today. Tested for honestly
    (asserted absent), not silently assumed present.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.brain.goal_system import GoalSystem, PRESEEDED_GOALS
from core.city.agent_registry import AgentRegistry
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory
from core.runtime.plans import (
    Plan,
    PlanStep,
    PlanStore,
    PlanRunner,
    _resolve_step_params,
    build_wedge_content_plan,
)
from districts.content.content_scheduler import ContentScheduler
from districts.content.script_generator import ScriptGenerator

from tests.test_r13_production_learning_validation import build_isolated_engine

EQUATION_GOAL_ID = "g_first_revenue"
EQUATION_GOAL_TITLE = next(g["title"] for g in PRESEEDED_GOALS if g["id"] == EQUATION_GOAL_ID)


def _preseeded_equation_goal() -> dict:
    return next(g.copy() for g in PRESEEDED_GOALS if g["id"] == EQUATION_GOAL_ID)


@pytest.fixture
def isolated_r19_registry():
    """Real AgentRegistry with ONLY ScriptGenerator + ContentScheduler --
    the two real handlers this composition's two real steps route to."""
    import core.city.agent_registry as registry_mod
    original = registry_mod._registry_singleton
    fresh = AgentRegistry()
    fresh.register(ScriptGenerator())
    fresh.register(ContentScheduler())
    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


@pytest.fixture
def isolated_post_job_db(tmp_path, monkeypatch):
    """ContentScheduler.schedule_post() internally instantiates its own
    PostJobTracker() with no override parameter; PostJobTracker's default
    _DB_PATH is frozen at import from CONFIG["data_dir"] ("./data/datasets",
    a static relative default, NOT VECTOR_TEST_DATA_DIR-aware) -- a newly
    discovered under-isolated persistence path (Phase 2 synthesis, not
    covered by the R13-established isolated_vector_db fixture). Must be
    monkeypatched before any ContentScheduler/PostJobTracker use, or a test
    would write to the repo's own data/datasets/ directory."""
    import districts.content.post_job as post_job_mod
    isolated_path = tmp_path / "post_jobs.db"
    monkeypatch.setattr(post_job_mod, "_DB_PATH", isolated_path)
    yield isolated_path


@pytest.fixture
def isolated_plan_store(tmp_path):
    """PlanStore.path defaults to data_path("plans","plans.json") --
    VECTOR_TEST_DATA_DIR-aware at call time, but explicit override (same
    idiom as EpistemicTracker(db_path=...)) keeps this test's plan file
    genuinely per-test-isolated, not merely shared-test-dir-isolated."""
    return PlanStore(path=tmp_path / "plans.json")


# ═══════════════════════════════════════════════════════════════════════════
# A/B — Equation goal discovery + composition construction
# ═══════════════════════════════════════════════════════════════════════════

class TestCompositionConstruction:

    def test_real_equation_goal_title_used_as_topic(self):
        """The real g_first_revenue goal exists with its real, doctrine-
        written title -- the deterministic builder uses a caller-supplied
        topic (never invented), so this just confirms the real goal's
        title is a legitimate, non-empty real string to pass."""
        goal = _preseeded_equation_goal()
        assert goal["id"] == EQUATION_GOAL_ID
        assert "wedge" in goal["title"].lower()

    def test_build_wedge_content_plan_produces_real_2_step_dag(self):
        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        assert isinstance(plan, Plan)
        assert plan.goal_id == EQUATION_GOAL_ID
        assert len(plan.steps) == 2
        assert plan.steps[0].action_type == "script"
        assert plan.steps[1].action_type == "schedule_post"
        assert plan.steps[1].depends_on == ["step-1"]
        assert plan.has_circular_deps() is False

    def test_no_fake_action_types(self):
        """Rule 1: no make_money/grow_revenue/get_customer-style invented
        action_type anywhere in the real plan."""
        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        real_action_types = {"script", "schedule_post"}
        assert {s.action_type for s in plan.steps} == real_action_types
        for forbidden in ("make_money", "grow_revenue", "get_customer", "build_startup", "increase_income"):
            assert forbidden not in {s.action_type for s in plan.steps}

    def test_step2_content_param_absent_until_resolved(self):
        """Rule 3: no hard-coded test value for the handed-off field --
        step-2's static params never contain "content" at all; it exists
        ONLY via param_bindings, resolved from step-1's real output."""
        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        assert "content" not in plan.steps[1].params
        assert plan.steps[1].param_bindings == {"content": "step-1.content"}


# ═══════════════════════════════════════════════════════════════════════════
# C/D — dependency/order correctness + real data handoff (fast, no LLM)
# ═══════════════════════════════════════════════════════════════════════════

class TestDependencyAndDataHandoff:

    def test_step2_not_ready_until_step1_completed(self):
        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        ready = plan.next_ready_steps()
        assert [s.id for s in ready] == ["step-1"]

        plan.steps[0].status = "completed"
        ready2 = plan.next_ready_steps()
        assert [s.id for s in ready2] == ["step-2"]

    def test_resolve_step_params_reads_real_dependency_output(self):
        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        plan.steps[0].status = "completed"
        plan.steps[0].actual_outcome = {
            "status": "executed", "summary": "ok", "verification_passed": True,
            "result": {"content": "REAL SCRIPT TEXT", "topic": EQUATION_GOAL_TITLE},
        }
        resolved = _resolve_step_params(plan, plan.steps[1])
        assert resolved["content"] == "REAL SCRIPT TEXT"
        assert resolved["title"] == EQUATION_GOAL_TITLE
        # step.params itself must never be mutated (Rule 3: no implicit
        # global/hidden state -- the static declaration stays static).
        assert "content" not in plan.steps[1].params

    def test_resolve_step_params_malformed_input_no_crash(self):
        """Category M: missing dependency, missing field, non-dict result,
        malformed binding string -- all must degrade safely, never raise."""
        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)

        # step-1 never completed -- binding unresolvable, must not crash.
        resolved = _resolve_step_params(plan, plan.steps[1])
        assert "content" not in resolved

        # step-1 completed but its real result lacks the bound field.
        plan.steps[0].status = "completed"
        plan.steps[0].actual_outcome = {"status": "executed", "summary": "ok", "verification_passed": True, "result": {"topic": "x"}}
        resolved2 = _resolve_step_params(plan, plan.steps[1])
        assert "content" not in resolved2

        # actual_outcome["result"] is not a dict at all.
        plan.steps[0].actual_outcome = {"status": "executed", "summary": "ok", "verification_passed": True, "result": "not a dict"}
        resolved3 = _resolve_step_params(plan, plan.steps[1])
        assert "content" not in resolved3

        # malformed binding string (no ".") on an otherwise-valid step.
        bad_step = PlanStep(id="s2", action_type="schedule_post", params={}, depends_on=["step-1"], param_bindings={"content": "no_dot_here"})
        resolved4 = _resolve_step_params(plan, bad_step)
        assert "content" not in resolved4

    def test_next_ready_steps_limit_and_priority_unaffected(self):
        """Regression: R19's new PlanStep field must not break the
        pre-existing DAG/priority machinery's own self-test shape."""
        plan = Plan(
            id="plan-regress", goal_id="g_x", objective="x", status="active",
            steps=[
                PlanStep(id="a", action_type="x"),
                PlanStep(id="b", action_type="y", depends_on=["a"]),
                PlanStep(id="c", action_type="z", depends_on=["a"]),
            ],
            created_at="now", updated_at="now",
        )
        assert [s.id for s in plan.next_ready_steps()] == ["a"]
        plan.steps[0].status = "completed"
        assert {s.id for s in plan.next_ready_steps()} == {"b", "c"}


# ═══════════════════════════════════════════════════════════════════════════
# E/F — native Candidate + DecisionEngine integration (fast, no LLM)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCandidateAndDecisionIntegration:

    async def test_plan_step_becomes_real_native_candidate(self, isolated_vector_db, isolated_plan_store, tmp_path):
        """_get_plan_candidates() (the REAL, unmodified production method)
        must translate a real, active plan's real ready step into a real
        Candidate -- no hand-built Candidate."""
        from core.loop.autonomous_loop import AutonomousLoop

        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        plan.status = "active"
        isolated_plan_store.add(plan)

        loop = AutonomousLoop()
        loop._plan_store = isolated_plan_store
        candidates = loop._get_plan_candidates()

        assert len(candidates) == 1
        c = candidates[0]
        assert c.action_type == "script"
        assert c.source == f"plan:{plan.id}:step-1"
        assert c.goal_ids == [EQUATION_GOAL_ID]

    async def test_plan_candidate_competes_in_real_decision_engine(self, isolated_vector_db, isolated_plan_store, tmp_path):
        """The real DecisionEngine.evaluate() must accept and score a
        plan-sourced Candidate exactly like any other -- same path, no
        parallel decision system."""
        from core.loop.autonomous_loop import AutonomousLoop

        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        plan.status = "active"
        isolated_plan_store.add(plan)

        loop = AutonomousLoop()
        loop._plan_store = isolated_plan_store
        candidates = loop._get_plan_candidates()

        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        decision = await engine.evaluate(candidates)
        assert decision.winner.action_type == "script"
        assert any(decision.winner is c for c in candidates)
        assert decision.winner.decision_id and decision.winner.decision_id.startswith("d:")
        assert decision.winner.candidate_id and decision.winner.candidate_id.startswith("c:")


# ═══════════════════════════════════════════════════════════════════════════
# G/H — Governor + Permission verification (fast, real dispatch, no LLM)
# ═══════════════════════════════════════════════════════════════════════════

class TestGovernorAndPermission:

    def test_both_steps_green(self):
        gw = PermissionGateway()
        assert gw.classify("script") == "GREEN"
        assert gw.classify("schedule_post") == "GREEN"

    def test_governor_district_task_map_exact_match(self):
        from core.city.governor import DISTRICT_TASK_MAP
        assert DISTRICT_TASK_MAP["script"] == "content"
        assert DISTRICT_TASK_MAP["schedule_post"] == "content"

    def test_content_publish_still_red_and_untouched(self):
        """The actual external/irreversible publish action_type
        (run_pending()'s real gate) must remain RED and unaffected."""
        from core.config import CONFIG
        assert "content_publish" in CONFIG["permission"]["red"]

    @pytest.mark.asyncio
    async def test_schedule_post_dispatches_to_real_content_scheduler(
        self, isolated_vector_db, isolated_r19_registry, isolated_post_job_db, isolated_plan_store,
    ):
        """Real Governor.dispatch() for schedule_post reaches the real
        ContentScheduler (via the new _execute_action() branch), creates a
        real local PostJob row, and never touches run_pending()/publish."""
        plan = Plan(
            id="plan-h", goal_id=EQUATION_GOAL_ID, objective="test",
            status="active",
            steps=[PlanStep(id="step-2", action_type="schedule_post",
                             params={"title": "probe", "content": "hello", "platforms": ["devto"]})],
            created_at="now", updated_at="now",
        )
        isolated_plan_store.add(plan)
        runner = PlanRunner(store=isolated_plan_store)
        result = await runner.execute_step(plan, plan.steps[0])
        assert result["status"] == "completed"
        assert plan.steps[0].actual_outcome["result"]["job_ids"]

    def test_plan_composable_action_types_narrowly_scoped(self):
        """Category O (adversarial): the new _execute_action() dispatch
        branch must be a small, explicit allowlist -- never "any non-hand_
        action_type" -- so a RED action can never reach Governor.dispatch()
        through this specific new path merely by being routed via a plan.

        RR-3.5A (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        RR3_5_FOUNDATION_CLOSURE_REPORT.md) added "idea_validate" to this
        same allowlist -- a third, individually source-verified, GREEN-tier
        entry (real handler, real single unambiguous DISTRICT_TASK_MAP
        route), not a loosening of the allowlist's shape. RR-3.7B
        (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        RR3_7B_STRUCTURED_ROUTER_AUTHORIZATION_REPORT.md) added
        "log_exercise"/"create_project" -- two individually source-verified,
        YELLOW-tier entries (real handlers, real exact task_type branches)
        closing structured-router authorization gaps in health.py/
        projects.py. The real security invariant this test protects -- no
        RED action ever reachable via this delegation path -- is unchanged
        and re-verified below; only the exact-membership snapshot grows by
        each new, deliberately authorized entry.
        """
        from core.loop.permission_gateway import _PLAN_COMPOSABLE_ACTION_TYPES
        from core.config import CONFIG
        assert _PLAN_COMPOSABLE_ACTION_TYPES == {
            "script", "schedule_post", "idea_validate",
            "log_exercise", "create_project", "web_extract",
        }
        for red_action in CONFIG["permission"]["red"]:
            assert red_action not in _PLAN_COMPOSABLE_ACTION_TYPES

    def test_no_maybe_decompose_style_bundling(self):
        """Category O: PlanRunner.execute_step() must dispatch exactly ONE
        action_type per call (never Governor._maybe_decompose()'s pattern
        of one top-level permission check fanning out into multiple real
        sub-dispatches) -- source-level structural check."""
        src = inspect.getsource(PlanRunner.execute_step)
        assert src.count("executor.execute(") == 1
        assert "_maybe_decompose" not in src


# ═══════════════════════════════════════════════════════════════════════════
# I/J/K/L — FLAGSHIP: real production-boundary composition. The ONE real
# LLM-calling execution in this file (step-1's real script generation).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.timeout(900)
class TestFlagshipRealComposition:

    async def test_real_goal_to_real_composed_2step_execution(
        self, isolated_vector_db, isolated_r19_registry, isolated_post_job_db, isolated_plan_store, tmp_path,
    ):
        """No hand-built Candidate, no fake handler, no fake outcome. Real
        g_first_revenue goal's real title -> real deterministic Plan ->
        real _get_plan_candidates() -> real DecisionEngine.evaluate() ->
        real AutonomousLoop._act_on() -> real _act_on_plan_step() -> real
        PlanRunner.execute_step() -> real ScriptGenerator (real LLM call)
        -> real content -> real param_bindings resolution -> (cycle 2)
        real ContentScheduler.schedule_post() consuming that real content
        -> real local PostJob row. Crosses the real production boundary
        for BOTH steps."""
        from core.loop.autonomous_loop import AutonomousLoop

        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        plan.status = "active"
        isolated_plan_store.add(plan)

        loop = AutonomousLoop()
        loop._plan_store = isolated_plan_store
        loop._decision_engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        pm = PolicyMemory()

        # ---- Cycle 1: step-1 (script), real production path ----
        candidates_1 = loop._get_plan_candidates()
        assert len(candidates_1) == 1 and candidates_1[0].action_type == "script"
        decision_1 = await loop._decision_engine.evaluate(candidates_1)
        assert decision_1.winner.action_type == "script"
        assert any(decision_1.winner is c for c in candidates_1), (
            "the executed winner must be DecisionEngine's own real object"
        )
        decision_id_1 = decision_1.winner.decision_id
        candidate_id_1 = decision_1.winner.candidate_id

        await loop._act_on(decision_1.winner)  # REAL _act_on() -> detects
        # source.startswith("plan:") -> real _act_on_plan_step() -> real
        # PlanRunner.execute_step() -> real Governor.dispatch() -> real
        # ScriptGenerator.run() -> real LLM call.

        step1 = plan.get_step("step-1")
        assert step1.status == "completed", f"step-1 did not complete: {step1.actual_outcome}"
        real_content = step1.actual_outcome["result"].get("content")
        assert isinstance(real_content, str) and len(real_content) > 0, (
            "step-1 must have produced real, non-empty generated script content"
        )

        h1 = pm.make_situation_hash("script", decision_1.winner.params)
        score1 = pm.get_score("script", h1)
        assert score1 != PolicyMemory.DEFAULT_SCORE, "step-1's real execution must have written a real policy score"

        # ---- Cycle 2: step-2 (schedule_post) is NOW ready -- its real
        # input is step-1's real, just-produced output, read back through
        # the real production representation (plan.steps[0].actual_outcome),
        # never re-injected/hand-typed here. ----
        candidates_2 = loop._get_plan_candidates()
        assert len(candidates_2) == 1 and candidates_2[0].action_type == "schedule_post", (
            f"step-2 must become ready only now that step-1 is real-completed, got {[c.action_type for c in candidates_2]}"
        )
        decision_2 = await loop._decision_engine.evaluate(candidates_2)
        assert decision_2.winner.action_type == "schedule_post"
        decision_id_2 = decision_2.winner.decision_id
        candidate_id_2 = decision_2.winner.candidate_id
        assert decision_id_2 != decision_id_1
        assert candidate_id_2 != candidate_id_1

        await loop._act_on(decision_2.winner)  # REAL _act_on() -> real
        # _act_on_plan_step() -> real PlanRunner.execute_step() ->
        # _resolve_step_params() reads step-1's REAL content ->
        # real Governor.dispatch() -> real ContentScheduler.schedule_post()
        # -> real local PostJob row (never publishes externally).

        step2 = plan.get_step("step-2")
        assert step2.status == "completed", f"step-2 did not complete: {step2.actual_outcome}"
        job_ids = step2.actual_outcome["result"].get("job_ids")
        assert job_ids, "step-2 must have created a real PostJob row"
        dispatched_content = step2.actual_outcome["result"].get("params", {}).get("content")
        assert dispatched_content == real_content, (
            "step-2's REAL dispatched content must be byte-identical to step-1's "
            "REAL generated content -- proves genuine structural data handoff, "
            "not a coincidental or hand-typed value"
        )

        h2 = pm.make_situation_hash("schedule_post", decision_2.winner.params)
        score2 = pm.get_score("schedule_post", h2)
        assert score2 != PolicyMemory.DEFAULT_SCORE, "step-2's real execution must have written a real policy score"

        assert plan.status == "completed"
        assert plan.progress == 1.0

        # ---- Persistence: real restart, both real outcomes survive ----
        isolated_plan_store.save()
        reloaded_store = PlanStore(path=isolated_plan_store.path)
        reloaded_plan = reloaded_store.get(plan.id)
        assert reloaded_plan is not None
        assert reloaded_plan.status == "completed"
        assert reloaded_plan.steps[0].actual_outcome["result"].get("content") == real_content
        assert reloaded_plan.steps[1].actual_outcome["result"].get("job_ids") == job_ids

        from core.memory.episodic import close_db_connection
        close_db_connection()
        pm2 = PolicyMemory()
        assert pm2.get_score("script", h1) == pytest.approx(score1, abs=0.001)
        assert pm2.get_score("schedule_post", h2) == pytest.approx(score2, abs=0.001)

        # ---- Honest learning-compatibility check (documented, not fixed):
        # plan-step decisions do NOT get an R7 reasoning_chains correlation
        # marker today (only the main, non-plan _act_on() path writes one) --
        # asserted absent, not silently assumed present. ----
        from tests.test_r13_production_learning_validation import read_reasoning_chain_for_decision
        assert read_reasoning_chain_for_decision(decision_id_1) is None
        assert read_reasoning_chain_for_decision(decision_id_2) is None


# ═══════════════════════════════════════════════════════════════════════════
# Safety: source-level audit, no second real LLM call
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_schedule_post_has_no_external_io(self):
        src = inspect.getsource(ContentScheduler.schedule_post)
        for forbidden in ("httpx.post", "httpx.get", "requests.", "smtplib", "subprocess.", "os.system", "publish_all(", "_get_publisher("):
            assert forbidden not in src

    def test_run_pending_remains_the_only_publish_path_and_stays_gated(self):
        """The one method that DOES publish externally must keep its own,
        separate, real owner-approval gate -- confirms R19's composition
        never reaches it."""
        src = inspect.getsource(ContentScheduler.run_pending)
        assert "PermissionGateway" in src
        assert 'action_type="content_publish"' in src
        assert "_approved" in src

    def test_new_permission_gateway_branch_never_bypasses_forbidden_or_tier_gate(self):
        """The new _execute_action() branch is reached only AFTER
        execute()'s FORBIDDEN check and tier-based GREEN/YELLOW/RED routing
        (source-level: _execute_action() is a private helper only ever
        called from inside execute()'s own tier branches, never directly)."""
        import core.loop.permission_gateway as pg
        src = inspect.getsource(pg.PermissionGateway.execute)
        assert "_execute_action" in src
        assert src.index("FORBIDDEN") < src.index("_execute_action")


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--timeout=900"])
    print("OK test_r19_capability_composition.py" if result.returncode == 0 else "FAILED test_r19_capability_composition.py")
