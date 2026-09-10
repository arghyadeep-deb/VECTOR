"""
R23 — World Model + Self Model.

Phase 1's world-model audit (see VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_
ORCHESTRATOR_LEDGER.md) found no genuine, coherent, cross-subsystem
world model exists today (`core/runtime/world_model.py::
build_world_snapshot()` is a real UI/status dashboard, not a decision
input) — but real, individually-queryable, ALREADY system-wide stores
do exist, each currently read only by its own owning subsystem.
`core/runtime/plans.py::PlanStore.active_plans()` is the smallest real
substrate: already unscoped/system-wide, zero new infrastructure needed
to make it genuinely cross-goal-visible.

Phase 1's self-model audit found real, already-wired signals exist
(epistemic dampening, MetaCognition's real bias penalty) but capability
EXISTENCE is checked only at `Governor.dispatch()` time — AFTER a
winning Candidate has already been committed to. `core/brain/
goal_system.py`/`core/loop/decision_engine.py` never consulted the real,
live `AgentRegistry` before that point: VECTOR could score/select a
candidate for a capability that does not currently exist, discovering
the gap only at dispatch (`governor.py`'s own real, honest
"no_capable_agent" refusal — which this milestone does NOT replace,
duplicate, or remove; it only makes the SAME real fact available one
step earlier).

Both new factors follow the exact architectural shape R22 already
established (`_situational_factor()`): a small, bounded, POST-score
multiplier on `_score_candidate()`, reading an already-real, already-
existing store via the SAME production classes (`AgentRegistry`,
`PlanStore`) real production code already uses -- no new subsystem, no
new memory store, no new persisted state.

CRITICAL SAFETY DISTINCTION (per the mission's own explicit
requirement): the self-model DESCRIBES capability/authority -- it never
CREATES it. `_capability_factor()` can only ever produce a PENALTY
(never a boost) for a candidate whose capability doesn't currently
exist, and never touches `PermissionGateway`/`core/config.py`/Governor's
own routing in any way. Likewise `_workload_factor()` (world-model) is
a pure scoring preference (finish committed work before starting new
work), never an authorization change.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.city.agent_registry import AgentRegistry
from core.loop.decision_engine import Candidate, DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.runtime.plans import Plan, PlanStep, PlanStore, build_wedge_content_plan
from districts.startups.idea_validator import IdeaValidator

from tests.test_r13_production_learning_validation import build_isolated_engine

EQUATION_GOAL_ID = "g_first_revenue"
EQUATION_GOAL_TITLE = "First ₹1 of product revenue from a stranger — wedge: AI content ops for creators (customer #1: father's accounts)"


class _FixedWorldStateContextEngine:
    """Same real-shaped stand-in R22's own flagship used for the ONE
    external sensor/IO boundary `evaluate()` reads -- keeps R22's own
    `_situational_factor()` neutral (presence="present" -> factor 1.0
    always) so R23's two new factors can be isolated and attributed
    cleanly, without a real FaceDetector/screen/phone sensor read."""

    def get_world_state(self, query: str | None = None) -> dict:
        return {
            "timestamp": 0.0, "time_of_day": "afternoon", "day_of_week": "Monday",
            "owner": "Arghyadeep", "env": "test", "version": "test",
            "active_model": "test", "recent_episodes": [], "goal_summary": "",
            "memory_stats": {}, "loop_status": "idle", "presence": "present",
            "owner_identity": "owner", "fatigue_score": 0.0, "screen_summary": "",
            "phone_connected": False, "phone_notification_count": 0,
        }


def _capability_race_candidates(goal_id: str = "g_r23_probe") -> list[Candidate]:
    """Real, materially different action_types (GREEN idea_validate vs
    YELLOW commit_code), same confidence gap R22 already established
    (0.5 vs 0.55) so the pre-capability-check race has a real, narrow,
    known winner (commit_code) to flip."""
    green = Candidate(
        action_type="idea_validate", params={"goal_id": goal_id, "title": "probe"},
        goal_ids=[goal_id], confidence=0.5, urgency=0.5, source="think_loop",
    )
    yellow = Candidate(
        action_type="commit_code", params={"goal_id": goal_id, "title": "probe"},
        goal_ids=[goal_id], confidence=0.55, urgency=0.5, source="think_loop",
    )
    return [green, yellow]


# ═══════════════════════════════════════════════════════════════════════════
# Fast, no-LLM unit checks of both new factors' mechanics
# ═══════════════════════════════════════════════════════════════════════════

class TestCapabilityFactorMechanics:

    def test_capable_action_not_penalized(self):
        engine = DecisionEngine()
        engine._agent_registry = MagicMock(get_all_agents=lambda: [
            MagicMock(capabilities=["idea_validate", "script"])
        ])
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, signal = engine._capability_factor(c)
        assert factor == 1.0
        assert signal == "capable"

    def test_no_capable_agent_is_penalized(self):
        engine = DecisionEngine()
        engine._agent_registry = MagicMock(get_all_agents=lambda: [
            MagicMock(capabilities=["something_else"])
        ])
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, signal = engine._capability_factor(c)
        assert factor == 0.85
        assert signal == "no_capable_agent"

    def test_empty_registry_penalizes_uniformly_not_a_crash(self):
        engine = DecisionEngine()
        engine._agent_registry = MagicMock(get_all_agents=lambda: [])
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, signal = engine._capability_factor(c)
        assert factor == 0.85

    def test_registry_error_fails_safe_neutral(self):
        """A self-model that cannot inspect itself must never be treated
        as evidence of incapability."""
        engine = DecisionEngine()
        def _raise():
            raise RuntimeError("registry unavailable")
        engine._get_agent_registry = _raise
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, signal = engine._capability_factor(c)
        assert factor == 1.0
        assert signal == "error"

    def test_factor_never_exceeds_neutral(self):
        """The self-model can only ever PENALIZE, never boost."""
        engine = DecisionEngine()
        for caps in ([], ["idea_validate"], ["idea_validate", "script", "commit_code"]):
            engine._agent_registry = MagicMock(get_all_agents=lambda caps=caps: [MagicMock(capabilities=caps)])
            c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
            factor, _ = engine._capability_factor(c)
            assert 0.85 <= factor <= 1.0


class TestWorkloadFactorMechanics:

    def test_no_active_plans_neutral(self):
        engine = DecisionEngine()
        engine._plan_store = MagicMock(active_plans=lambda: [])
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, signal = engine._workload_factor(c)
        assert factor == 1.0
        assert signal == "no_active_plans"

    def test_active_plans_penalize_new_native_work(self):
        engine = DecisionEngine()
        engine._plan_store = MagicMock(active_plans=lambda: [MagicMock()])
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, signal = engine._workload_factor(c)
        assert factor == 0.97
        assert signal == "new_work_while_plans_active"

    def test_active_plans_do_not_penalize_plan_continuation(self):
        engine = DecisionEngine()
        engine._plan_store = MagicMock(active_plans=lambda: [MagicMock()])
        c = Candidate(action_type="script", params={}, confidence=0.5, urgency=0.5, source="plan:plan-x:step-1")
        factor, signal = engine._workload_factor(c)
        assert factor == 1.0
        assert signal == "continues_active_plan"

    def test_plan_store_error_fails_safe_neutral(self):
        engine = DecisionEngine()
        def _raise():
            raise RuntimeError("plan store unavailable")
        engine._get_plan_store = _raise
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, signal = engine._workload_factor(c)
        assert factor == 1.0
        assert signal == "error"

    def test_factor_never_exceeds_neutral(self):
        engine = DecisionEngine()
        engine._plan_store = MagicMock(active_plans=lambda: [MagicMock()])
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, _ = engine._workload_factor(c)
        assert 0.97 <= factor <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# BEFORE: pre-R23 scoring components are blind to both real facts.
# ═══════════════════════════════════════════════════════════════════════════

class TestBeforeMissingDistinction:

    def test_pre_r23_formula_blind_to_capability_and_workload(self):
        engine = DecisionEngine()
        c1 = Candidate(action_type="idea_validate", params={"goal_id": "g_r23_probe"}, confidence=0.5, urgency=0.5, source="think_loop")
        c2 = Candidate(action_type="idea_validate", params={"goal_id": "g_r23_probe"}, confidence=0.5, urgency=0.5, source="think_loop")
        # Every OTHER real scoring component, unmodified by R23, cannot see
        # capability or workload state at all -- it only reads candidate.*
        # fields already set at construction time.
        assert engine._score_goal_alignment(c1) == engine._score_goal_alignment(c2)
        h1 = engine._make_situation_hash(c1)
        h2 = engine._make_situation_hash(c2)
        assert h1 == h2  # identity is action_type+params only, never capability/workload


# ═══════════════════════════════════════════════════════════════════════════
# AFTER / FLAGSHIP: real winner flips, real production classes (AgentRegistry,
# PlanStore), zero real LLM calls (pure scoring, no dispatch/execution).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def isolated_r23_registry():
    import core.city.agent_registry as registry_mod
    original = registry_mod._registry_singleton
    fresh = AgentRegistry()
    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


@pytest.mark.asyncio
class TestFlagshipSelfModel:

    async def test_real_evaluate_winner_flips_on_real_capability_existence(
        self, isolated_vector_db, isolated_r23_registry, tmp_path,
    ):
        """Self-model: a real, live IdeaValidator() is registered (declares
        the real "idea_validate" capability, per R18-EQ) -- NO agent
        declares "commit_code". No hardcoded winner: both scores are real,
        computed values."""
        isolated_r23_registry.register(IdeaValidator())

        engine = build_isolated_engine(str(tmp_path / "epi.db"))
        engine._context_engine = _FixedWorldStateContextEngine()  # isolate R22's situational factor
        engine._plan_store = MagicMock(active_plans=lambda: [])  # isolate workload
        candidates = _capability_race_candidates()
        decision = await engine.evaluate(candidates)

        assert decision.winner.action_type == "idea_validate", (
            f"the real, live-capable candidate must win once the real self-model "
            f"check is consulted, got {decision.winner.action_type}"
        )
        green = next(c for c in candidates if c.action_type == "idea_validate")
        yellow = next(c for c in candidates if c.action_type == "commit_code")
        assert any(s["factor"] == "self_model_capability" for s in yellow.reasoning_chain)
        assert not any(s["factor"] == "self_model_capability" for s in green.reasoning_chain)

    async def test_control_when_neither_capable_relative_order_unaffected(
        self, isolated_vector_db, isolated_r23_registry, tmp_path,
    ):
        """CONTROL: with NEITHER action_type capable (a genuinely empty
        registry), the uniform penalty must not flip the race on its own --
        commit_code's real merit advantage stays decisive."""
        engine = build_isolated_engine(str(tmp_path / "epi2.db"))
        engine._context_engine = _FixedWorldStateContextEngine()
        engine._plan_store = MagicMock(active_plans=lambda: [])
        candidates = _capability_race_candidates()
        decision = await engine.evaluate(candidates)
        assert decision.winner.action_type == "commit_code"

    async def test_self_model_cannot_self_authorize(self, isolated_vector_db, isolated_r23_registry, tmp_path):
        """Safety: even a candidate the self-model considers fully
        "capable" (factor=1.0, no penalty) never has its real permission
        tier altered -- the self-model describes capability, never
        authority."""
        isolated_r23_registry.register(IdeaValidator())
        engine = build_isolated_engine(str(tmp_path / "epi3.db"))
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        factor, signal = engine._capability_factor(c)
        assert factor == 1.0 and signal == "capable"
        assert PermissionGateway().classify("idea_validate") == "GREEN"
        # A RED action can never be promoted even if some (unrelated) live
        # agent happened to declare it as a capability.
        red_c = Candidate(action_type="code_task", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        engine._agent_registry = MagicMock(get_all_agents=lambda: [MagicMock(capabilities=["code_task"])])
        red_factor, red_signal = engine._capability_factor(red_c)
        assert red_factor == 1.0  # "capable" is real, but changes nothing about authorization
        assert PermissionGateway().classify("code_task") == "RED"


@pytest.mark.asyncio
class TestFlagshipWorldModel:

    async def test_real_evaluate_winner_flips_on_real_active_plan(
        self, isolated_vector_db, isolated_r23_registry, tmp_path,
    ):
        """World-model: a real, active Plan (built via R19's own real
        build_wedge_content_plan(), added to a real, isolated PlanStore)
        makes VECTOR real-world-state-aware that committed work already
        exists -- a fresh, unrelated native candidate for the SAME goal
        gets a small, real preference AGAINST it in favor of continuing
        work. Capability is held neutral (both action_types registered
        capable) to isolate the world-model effect specifically."""
        isolated_r23_registry.register(IdeaValidator())
        from districts.content.script_generator import ScriptGenerator
        isolated_r23_registry.register(ScriptGenerator())

        plan_store = PlanStore(path=tmp_path / "plans.json")
        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        plan.status = "active"
        plan_store.add(plan)

        engine = build_isolated_engine(str(tmp_path / "epi.db"))
        engine._context_engine = _FixedWorldStateContextEngine()
        engine._plan_store = plan_store

        native = Candidate(
            action_type="idea_validate", params={"goal_id": EQUATION_GOAL_ID, "title": "probe"},
            goal_ids=[EQUATION_GOAL_ID], confidence=0.52, urgency=0.5, source="think_loop",
        )
        plan_step = Candidate(
            action_type="script", params={"goal_id": EQUATION_GOAL_ID, "title": "probe"},
            goal_ids=[EQUATION_GOAL_ID], confidence=0.5, urgency=0.5, source=f"plan:{plan.id}:step-1",
        )
        decision = await engine.evaluate([native, plan_step])

        assert decision.winner.action_type == "script", (
            f"the real, plan-continuing candidate must be preferred once the real "
            f"world-model (an actual active Plan) is consulted, got {decision.winner.action_type}"
        )
        native_c = next(c for c in decision.all_candidates if c.action_type == "idea_validate")
        assert any(s["factor"] == "world_model_workload" for s in native_c.reasoning_chain)

    async def test_control_no_active_plans_relative_order_unaffected(
        self, isolated_vector_db, isolated_r23_registry, tmp_path,
    ):
        """CONTROL: with no real active plans, the native candidate's real
        confidence advantage stays decisive -- no phantom world-state
        effect."""
        isolated_r23_registry.register(IdeaValidator())
        from districts.content.script_generator import ScriptGenerator
        isolated_r23_registry.register(ScriptGenerator())

        plan_store = PlanStore(path=tmp_path / "plans_empty.json")
        engine = build_isolated_engine(str(tmp_path / "epi_ctrl.db"))
        engine._context_engine = _FixedWorldStateContextEngine()
        engine._plan_store = plan_store

        native = Candidate(
            action_type="idea_validate", params={"goal_id": EQUATION_GOAL_ID, "title": "probe"},
            goal_ids=[EQUATION_GOAL_ID], confidence=0.52, urgency=0.5, source="think_loop",
        )
        plan_step = Candidate(
            action_type="script", params={"goal_id": EQUATION_GOAL_ID, "title": "probe"},
            goal_ids=[EQUATION_GOAL_ID], confidence=0.5, urgency=0.5, source="plan:none:step-1",
        )
        decision = await engine.evaluate([native, plan_step])
        assert decision.winner.action_type == "idea_validate"

    def test_world_model_cannot_self_authorize(self):
        """Safety: workload preference never touches permission tiers."""
        src = inspect.getsource(DecisionEngine._workload_factor)
        for forbidden in ("PermissionGateway", "core.config", "GREEN.append", "RED.append", "YELLOW.append"):
            assert forbidden not in src


# ═══════════════════════════════════════════════════════════════════════════
# Persistence: honest scope statement + real proof where a claim IS made.
# ═══════════════════════════════════════════════════════════════════════════

class TestPersistence:

    def test_plan_store_world_state_survives_real_restart(self, tmp_path):
        """The world-model substrate (PlanStore) genuinely persists --
        already proven in R19, re-confirmed here as the specific fact R23
        relies on: a fresh PlanStore instance against the SAME on-disk
        file recovers the same active_plans() the scoring factor reads."""
        plan_store = PlanStore(path=tmp_path / "plans.json")
        plan = build_wedge_content_plan(EQUATION_GOAL_ID, EQUATION_GOAL_TITLE)
        plan.status = "active"
        plan_store.add(plan)
        assert len(plan_store.active_plans()) == 1

        reloaded = PlanStore(path=tmp_path / "plans.json")
        assert len(reloaded.active_plans()) == 1
        assert reloaded.active_plans()[0].id == plan.id

    def test_agent_registry_is_honestly_not_a_persisted_store(self):
        """Honest capability-boundary statement (not a defect): the
        self-model's substrate (AgentRegistry) is real, live, in-memory
        registration state -- agents register themselves fresh at every
        real process start, by real production design (core/city/
        agent_registry.py has no save/load-from-disk path). R23 does not
        claim self-model persistence across a restart; only the
        world-model (PlanStore) claim is a persistence claim, and only
        that one is proven above."""
        import core.city.agent_registry as registry_mod
        assert not hasattr(registry_mod.AgentRegistry, "save")
        assert not hasattr(registry_mod.AgentRegistry, "load")


# ═══════════════════════════════════════════════════════════════════════════
# Safety
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_capability_factor_never_calls_permission_gateway(self):
        """The self-model factor must never even indirectly consult
        authorization -- capability existence and permission tier are
        deliberately orthogonal real facts. Scans only the executable
        body (docstring stripped), since the docstring itself
        legitimately discusses PermissionGateway in prose to explain
        why it is NOT touched."""
        func = DecisionEngine._capability_factor
        body_src = inspect.getsource(func).split('"""', 2)[-1]
        for forbidden in ("PermissionGateway", "core.config", "classify("):
            assert forbidden not in body_src

    def test_neither_new_factor_mutates_permission_tiers(self):
        cap_src = inspect.getsource(DecisionEngine._capability_factor)
        work_src = inspect.getsource(DecisionEngine._workload_factor)
        for src in (cap_src, work_src):
            for line in src.splitlines():
                stripped = line.strip()
                assert not stripped.startswith(("GREEN =", "RED =", "YELLOW =", "FORBIDDEN ="))

    def test_permission_tiers_fully_unaffected_by_r23(self):
        assert PermissionGateway().classify("idea_validate") == "GREEN"
        assert PermissionGateway().classify("commit_code") == "YELLOW"
        assert PermissionGateway().classify("code_task") == "RED"

    def test_both_new_factors_are_strictly_bounded(self):
        engine = DecisionEngine()
        engine._agent_registry = MagicMock(get_all_agents=lambda: [])
        engine._plan_store = MagicMock(active_plans=lambda: [MagicMock()])
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        cap_factor, _ = engine._capability_factor(c)
        work_factor, _ = engine._workload_factor(c)
        assert 0.85 <= cap_factor <= 1.0
        assert 0.97 <= work_factor <= 1.0


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--timeout=60"])
    print("OK test_r23_world_self_model.py" if result.returncode == 0 else "FAILED test_r23_world_self_model.py")
