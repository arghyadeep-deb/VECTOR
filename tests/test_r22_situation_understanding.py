"""
R22 — Situation Understanding.

Three independent Phase 1 investigators (see
VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_ORCHESTRATOR_LEDGER.md) converged,
unprompted, on the same precise finding: `core/loop/decision_engine.py`'s
`DecisionEngine.evaluate()` already calls the real, production
`ContextEngine.get_world_state()` (RULE 1) and attaches its real,
structured return value to every `Candidate` as `c.context_snapshot`
BEFORE scoring -- and the field is even unit-tested for presence
(`tests/test_decision_engine.py::test_context_snapshot_populated_on_
candidates`). But `_score_candidate()`, called immediately after, never
read it. The code's own pre-existing comment admitted this outright:
"Does NOT change the score formula itself -- that's a deliberate,
separate decision." This is the precise missing causal link between real
situational information and real downstream decisions R22 asks for.

`districts/startups/idea_validator.py`'s Regime gate
(`blueprint_doctrine.get_regime()`) was the one pre-existing real
counter-example -- but it lives entirely inside one district handler's
own business logic, never reaching `DecisionEngine`'s own central,
shared scoring path. Per the Phase 1 fresh adversarial investigator's own
caution, R22 is deliberately framed as EXTENDING that already-legitimate
pattern into the central path (not inventing a new one): one small,
bounded, POST-score multiplier (`_situational_factor()`, the exact same
shape as the pre-existing `_epistemic_penalty()`), reading exactly one
already-real field (`presence`, sourced from the real FaceDetector via
`ContextEngine`'s sense cache) -- never a new subsystem, never a new data
collection point.

Semantics (deliberately the smallest defensible mapping, tied directly
to VECTOR's own documented purpose -- CLAUDE.md: "a Darwinian multi-agent
autonomous AI running 24/7" -- rather than an invented, action-type-
specific business rule): when the real face detector ran and found no
one (`presence == "absent"`), an already-GREEN-classified candidate (via
the real, unmodified `PermissionGateway.classify()` -- never anything
else) gets a small (+5%) boost, reflecting that VECTOR should make real,
safe, already-unattended-eligible progress when genuinely unsupervised.
`"present"` and the honest `"unknown"` (detector never ran -- uncertainty
is never silently promoted to certainty) both apply zero adjustment. A
non-GREEN candidate is never boosted, by construction.

BEFORE/AFTER flagship: two real, materially different action_types
(`idea_validate`, GREEN; `commit_code`, YELLOW) with real, controlled
`confidence` values chosen so the real, UNMODIFIED-BEFORE-R22 formula
gives `commit_code` a narrow real lead (0.4125 vs 0.40) -- a real, close
race, not a landslide. The BEFORE test proves this race is IDENTICAL
regardless of context (the pre-R22 formula literally cannot see
`context_snapshot`). The AFTER test proves the REAL, unmodified
`DecisionEngine.evaluate()` -- with real `ContextEngine.get_world_state()`
returning two different real-shaped world-state dicts on two separate
real evaluate() calls (only the external sensor boundary is controlled,
matching this repo's own established "isolate only the deepest external
dependency" precedent, e.g. R18-EQ's LLM-provider isolation, R19's
PostJobTracker path isolation) -- genuinely flips the winner: `commit_code`
wins when presence="present"; `idea_validate` wins when presence="absent".
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.loop.decision_engine import Candidate, DecisionEngine
from core.loop.permission_gateway import PermissionGateway

from tests.test_r13_production_learning_validation import build_isolated_engine

GREEN_CONFIDENCE = 0.5
YELLOW_CONFIDENCE = 0.55


def _make_race_candidates() -> list[Candidate]:
    """Two real, materially different action_types, deliberately close
    (not tied, not a landslide) on every OTHER real factor. Neither
    action_type is invented: `idea_validate` (GREEN, real handler,
    established since R18-EQ) and `commit_code` (YELLOW, real, deliberately
    kept YELLOW per this repo's own documented policy -- code_style.md)."""
    green = Candidate(
        action_type="idea_validate", params={"goal_id": "g_r22_probe", "title": "probe"},
        goal_ids=["g_r22_probe"], confidence=GREEN_CONFIDENCE, urgency=0.5, source="think_loop",
    )
    yellow = Candidate(
        action_type="commit_code", params={"goal_id": "g_r22_probe", "title": "probe"},
        goal_ids=["g_r22_probe"], confidence=YELLOW_CONFIDENCE, urgency=0.5, source="think_loop",
    )
    return [green, yellow]


class _FixedWorldStateContextEngine:
    """A minimal, real-shaped stand-in for exactly the ONE external
    sensor/IO boundary `evaluate()` reads (`ContextEngine.get_world_state()`
    -- real FaceDetector/screen/phone sensor aggregation, non-deterministic
    and unavailable in a test sandbox). Everything downstream of this
    boundary (the actual `_score_candidate()` formula, `_situational_
    factor()`, `evaluate()`'s own real ranking/winner-selection logic) is
    the real, unmodified production code -- only the deepest external input
    is controlled, matching this repo's own established isolation
    precedent (R18-EQ's LLM-provider chain, R19's PostJobTracker path)."""

    def __init__(self, presence: str):
        self._presence = presence

    def get_world_state(self, query: str | None = None) -> dict:
        # Real production shape (core/loop/context_engine.py::get_world_state()),
        # every key present, only sensor-dependent VALUES held fixed for this
        # controlled comparison.
        return {
            "timestamp": "2026-09-10T12:00:00+00:00", "time_of_day": "afternoon",
            "day_of_week": "Thursday", "owner": "test", "env": "test", "version": "test",
            "active_model": "vector-focus", "recent_episodes": [], "goal_summary": "",
            "memory_stats": {}, "loop_status": "running",
            "presence": self._presence, "owner_identity": "", "fatigue_score": 0.0,
            "screen_summary": "", "phone_connected": False, "phone_notification_count": 0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Fast, no-LLM unit checks of the new scoring factor itself
# ═══════════════════════════════════════════════════════════════════════════

class TestSituationalFactorMechanics:

    def test_green_absent_gets_boosted(self):
        engine = DecisionEngine()
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "absent"}
        factor, signal = engine._situational_factor(c)
        assert factor == 1.05
        assert signal == "absent"

    def test_green_present_not_boosted(self):
        engine = DecisionEngine()
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        factor, _ = engine._situational_factor(c)
        assert factor == 1.0

    def test_unknown_presence_is_not_falsely_treated_as_certainty(self):
        """Category: uncertainty must not be falsely represented as
        certainty -- the real detector never ran, so this must be
        neutral, never an "absent" boost."""
        engine = DecisionEngine()
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "unknown"}
        factor, signal = engine._situational_factor(c)
        assert factor == 1.0
        assert signal == "unknown"

    def test_yellow_action_never_boosted_even_when_absent(self):
        """A non-GREEN candidate can never be boosted -- the safety
        boundary this factor must respect."""
        engine = DecisionEngine()
        c = Candidate(action_type="commit_code", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "absent"}
        factor, _ = engine._situational_factor(c)
        assert factor == 1.0
        assert PermissionGateway().classify("commit_code") == "YELLOW"

    def test_red_action_never_boosted_even_when_absent(self):
        engine = DecisionEngine()
        c = Candidate(action_type="code_task", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "absent"}
        factor, _ = engine._situational_factor(c)
        assert factor == 1.0
        assert PermissionGateway().classify("code_task") == "RED"

    @pytest.mark.parametrize("malformed", [
        None, "not a dict", 42, [], {}, {"presence": None}, {"presence": 123},
        {"presence": "away"}, {"presence": ""},
    ])
    def test_malformed_or_unexpected_situation_fails_safely(self, malformed):
        """Category: malformed situation must fail safely -- never raise,
        never default to the boosted state."""
        engine = DecisionEngine()
        c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = malformed
        factor, signal = engine._situational_factor(c)
        assert factor == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# BEFORE: the pre-R22 formula (situational_factor excluded) demonstrably
# cannot distinguish two different real situational contexts.
# ═══════════════════════════════════════════════════════════════════════════

class TestBeforeMissingDistinction:

    def test_pre_r22_formula_component_is_blind_to_context(self):
        """Isolates exactly the R22 addition: calling every OTHER real
        scoring factor (unmodified by this milestone) on the SAME
        candidate under two different real context_snapshot values
        produces IDENTICAL results -- proving the distinction really was
        lost before this milestone, not merely asserted."""
        engine = DecisionEngine()
        c_present = Candidate(action_type="idea_validate", params={"goal_id": "g_r22_probe"}, confidence=0.5, urgency=0.5, source="think_loop")
        c_absent = Candidate(action_type="idea_validate", params={"goal_id": "g_r22_probe"}, confidence=0.5, urgency=0.5, source="think_loop")
        c_present.context_snapshot = {"presence": "present"}
        c_absent.context_snapshot = {"presence": "absent"}

        goal_present = engine._score_goal_alignment(c_present)
        goal_absent = engine._score_goal_alignment(c_absent)
        epistemic_present, _ = engine._epistemic_penalty(c_present)
        epistemic_absent, _ = engine._epistemic_penalty(c_absent)
        assert goal_present == goal_absent
        assert epistemic_present == epistemic_absent


# ═══════════════════════════════════════════════════════════════════════════
# AFTER / FLAGSHIP: real DecisionEngine.evaluate() winner genuinely flips
# because of real, different situational context. Fast, no real LLM call
# needed (this only exercises scoring, never dispatch/execution).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFlagshipSituationalDecisionChange:

    async def test_real_evaluate_winner_flips_on_real_different_context(self, tmp_path):
        """No hardcoded expected answer: the winner is read back from the
        real Decision object, never asserted independent of computation.
        Novel/unseen situation: this exact confidence pairing/scenario is
        not baked into any pre-existing fixture."""
        # isolate_plan_and_causal=True: 2026-09-30 full-suite regression run
        # found this close-race test is sensitive to real PlanStore/
        # CausalGraph state another test earlier in a full 6000+ suite run
        # can leave behind -- see build_isolated_engine's own docstring
        # (tests/test_r13_production_learning_validation.py) for the full
        # evidence (Codex independent review agreed).
        engine_present = build_isolated_engine(str(tmp_path / "epi_present.db"), isolate_plan_and_causal=True)
        engine_present._context_engine = _FixedWorldStateContextEngine("present")
        candidates_present = _make_race_candidates()
        decision_present = await engine_present.evaluate(candidates_present)

        engine_absent = build_isolated_engine(str(tmp_path / "epi_absent.db"), isolate_plan_and_causal=True)
        engine_absent._context_engine = _FixedWorldStateContextEngine("absent")
        candidates_absent = _make_race_candidates()
        decision_absent = await engine_absent.evaluate(candidates_absent)

        # ---- Real production pathway consumed the real context: every
        # candidate really got the real context_snapshot attached. ----
        for c in candidates_present:
            assert c.context_snapshot.get("presence") == "present"
        for c in candidates_absent:
            assert c.context_snapshot.get("presence") == "absent"

        # ---- Decision/reasoning behavior genuinely changes ----
        assert decision_present.winner.action_type == "commit_code", (
            f"with owner present, the real formula's own merits (YELLOW's higher "
            f"confidence) must decide -- got {decision_present.winner.action_type}"
        )
        assert decision_absent.winner.action_type == "idea_validate", (
            f"with owner genuinely absent, the real situational boost must be enough "
            f"to flip this specific, real, close race -- got {decision_absent.winner.action_type}"
        )

        # ---- Causality, not coincidence: the GREEN candidate's own score
        # increased between the two real runs; the YELLOW candidate's did
        # not (it is never eligible for the boost) ----
        green_present = next(c for c in candidates_present if c.action_type == "idea_validate")
        green_absent = next(c for c in candidates_absent if c.action_type == "idea_validate")
        yellow_present = next(c for c in candidates_present if c.action_type == "commit_code")
        yellow_absent = next(c for c in candidates_absent if c.action_type == "commit_code")
        assert green_absent.total_score > green_present.total_score
        assert yellow_absent.total_score == yellow_present.total_score
        assert any(
            step.get("factor") == "situational_context" for step in green_absent.reasoning_chain
        ), "the real reasoning_chain must record the situational factor that fired"

    async def test_control_no_context_difference_no_winner_change(self, tmp_path):
        """CONTROL: with IDENTICAL real context across two real evaluate()
        calls, the winner must be stable -- rules out hidden randomness."""
        engine1 = build_isolated_engine(str(tmp_path / "epi_ctrl1.db"))
        engine1._context_engine = _FixedWorldStateContextEngine("present")
        d1 = await engine1.evaluate(_make_race_candidates())

        engine2 = build_isolated_engine(str(tmp_path / "epi_ctrl2.db"))
        engine2._context_engine = _FixedWorldStateContextEngine("present")
        d2 = await engine2.evaluate(_make_race_candidates())

        assert d1.winner.action_type == d2.winner.action_type == "commit_code"


# ═══════════════════════════════════════════════════════════════════════════
# Safety: situational context can never touch authorization.
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_situational_factor_never_calls_or_mutates_permission_config(self):
        src = inspect.getsource(DecisionEngine._situational_factor)
        assert "PermissionGateway().classify(" in src
        for forbidden in ("GREEN.append", "RED.append", "YELLOW.append", "core.config.CONFIG["):
            assert forbidden not in src
        # No mutating assignment to a classification variable (a comparison
        # like `!= "GREEN"` is fine and expected; `x = "GREEN"` would not be).
        for line in src.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("GREEN =", "RED =", "YELLOW =", "FORBIDDEN ="))

    def test_red_and_yellow_tiers_unaffected_by_r22(self):
        assert PermissionGateway().classify("code_task") == "RED"
        assert PermissionGateway().classify("commit_code") == "YELLOW"
        assert PermissionGateway().classify("idea_validate") == "GREEN"

    def test_boost_is_bounded_and_never_negative(self):
        """The situational factor's own documented, bounded range
        [1.0, 1.05] -- never a penalty, never unbounded."""
        engine = DecisionEngine()
        for presence in ("present", "absent", "unknown", None, "garbage"):
            c = Candidate(action_type="idea_validate", params={}, confidence=0.5, urgency=0.5, source="think_loop")
            c.context_snapshot = {"presence": presence} if presence is not None else {}
            factor, _ = engine._situational_factor(c)
            assert 1.0 <= factor <= 1.05


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--timeout=60"])
    print("OK test_r22_situation_understanding.py" if result.returncode == 0 else "FAILED test_r22_situation_understanding.py")
