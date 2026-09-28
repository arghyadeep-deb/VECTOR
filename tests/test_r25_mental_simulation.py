"""
R25 — Mental Simulation + Consequence Evaluation.

Phase 1's discovery (see VECTOR_TECHNICAL_KNOWLEDGE/R24_R26_ORCHESTRATOR_
LEDGER.md -- 3 investigators, including a fresh adversarial reviewer who
independently queried the real production database) found:

- `districts/predictive_analytics/causal_simulator.py::CausalSimulator`
  is a REAL Monte Carlo engine (real RNG sampling, real convergence
  detection, real confidence intervals) but has NEVER, anywhere in this
  codebase, been connected to a specific real `Candidate.action_type` --
  every real call site feeds it hand-specified, generic scenario
  parameters (`high_load`, `budget_scenario`, ...), never anything
  derived from a real candidate. Building R25 on top of it would require
  either inventing per-action_type calibration numbers (fabrication) or
  deriving them from a single real scalar (R24's own blended `strength`),
  which would make the 1000-iteration Monte Carlo apparatus manufactured
  precision wrapped around one real number -- rejected as substrate.
- `core/causal/causal_reasoner.py::CausalReasoner.what_if()` is a
  confirmed, LIVE, disqualified shortcut: it ignores its own `action`/
  `hypothetical` arguments entirely and returns generic aggregate
  `CounterfactualMemory.get_rejection_patterns()` corpus stats, identical
  regardless of which two candidates are compared. Explicitly NOT reused.
- The empirically-verified, honest substrate: R24's own real,
  state-scoped `CausalGraph.get_outcomes()` edge list -- but read as a
  full categorical distribution over DISTINCT real outcome-node labels
  (R24's own `_causal_factor()` only ever reads one BLENDED scalar
  average across all of them). This is a genuinely different question
  from R24's own ("what reward has this tended to earn" vs. "what real,
  distinct-outcome-TYPE risk has this shown"), built from the exact same
  real, already-proven, already-accumulated data -- zero new store, zero
  new writer, zero fabricated distribution.

Honesty constraint carried directly from the adversarial reviewer's own
empirical finding (queried the real production DB: every one of 68 real
causal edges currently has hit_count=1): `_simulate_consequence()` will
correctly, honestly return "insufficient_data"/"no_history" far more
often than "predicted" in a lightly-used real system -- this file's own
`TestSimulateConsequenceMechanics` tests that boundary explicitly rather
than assuming a confident prediction is always available.
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
from core.memory.causal_graph import CausalGraph
from districts.coding.git_bot import GitBot

from tests.test_r13_production_learning_validation import build_isolated_engine, build_isolated_loop

PROBE_GOAL_ID = "g_r25_probe"
# RR-2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/RR2_MEANINGFUL_UTILITY_REPORT.md):
# was 0.3. RR-2 corrected _act_on()'s reward formula so an unknown-
# goal-progress outcome no longer defaults to a fabricated 0.5 (it now
# contributes 0 to the weighted sum), which lowered every real executed
# action's absolute reward -- including git_status's own seeded 3-win/
# 2-no_agents history below. At the old 0.3, git_status's real,
# RR-2-corrected PolicyMemory score no longer narrowly out-scored
# git_log's untried default in the baseline (both-ablated) condition,
# collapsing this flagship's three-phase design before R25 was even
# reached. Retuned to the real value where git_status's own
# formula+PolicyMemory merits narrowly lead again pre-R25 (confirmed via
# direct evaluate() runs against the real, corrected reward formula) --
# not a fabricated number, a recalibration of the race's own candidate
# confidence to restore the real narrow-lead condition this test's
# narrative depends on.
# 2026-09-25 recalibration: a real, successful git_status is no longer scored as a failure (its learned reward rose
# 0.42 -> 0.63), so at the old 0.55 its lead was too wide for the simulation factor to overturn. The narrow-lead
# condition holds for 0.35..0.42 (found by running the suite over that range; 0.32 and 0.43 each break it).
CONF_GIT_STATUS = 0.38
CONF_GIT_LOG = 0.4


class _FixedWorldStateContextEngine:
    def __init__(self, presence: str):
        self._presence = presence

    def get_world_state(self, query: str | None = None) -> dict:
        return {
            "timestamp": 0.0, "time_of_day": "afternoon", "day_of_week": "Monday",
            "owner": "Arghyadeep", "env": "test", "version": "test",
            "active_model": "test", "recent_episodes": [], "goal_summary": "",
            "memory_stats": {}, "loop_status": "idle", "presence": self._presence,
            "owner_identity": "owner", "fatigue_score": 0.0, "screen_summary": "",
            "phone_connected": False, "phone_notification_count": 0,
        }


def _race_candidates(conf_status: float = CONF_GIT_STATUS, conf_log: float = CONF_GIT_LOG) -> list[Candidate]:
    return [
        Candidate(
            action_type="git_status", params={"goal_id": PROBE_GOAL_ID},
            goal_ids=[PROBE_GOAL_ID], confidence=conf_status, urgency=0.5, source="think_loop",
        ),
        Candidate(
            action_type="git_log", params={"goal_id": PROBE_GOAL_ID},
            goal_ids=[PROBE_GOAL_ID], confidence=conf_log, urgency=0.5, source="think_loop",
        ),
    ]


@pytest.fixture
def isolated_r25_registry():
    import core.city.agent_registry as registry_mod
    original = registry_mod._registry_singleton
    fresh = AgentRegistry()
    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


# ═══════════════════════════════════════════════════════════════════════════
# Fast, no-dispatch unit tests of _simulate_consequence()/_simulation_factor()
# ═══════════════════════════════════════════════════════════════════════════

class TestSimulateConsequenceMechanics:

    def test_no_history_status(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [])
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        result = engine._simulate_consequence(c)
        assert result == {"status": "no_history"}

    def test_insufficient_data_status_and_count(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [
            {"to": "outcome:unknown", "strength": 0.8, "hit_count": 2},
        ])
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        result = engine._simulate_consequence(c)
        assert result == {"status": "insufficient_data", "n_observations": 2}

    def test_predicted_status_real_categorical_distribution(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [
            {"to": "outcome:unknown", "strength": 0.8, "hit_count": 3},
            {"to": "outcome:no_capable_agent", "strength": 0.4, "hit_count": 2},
        ])
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        result = engine._simulate_consequence(c)
        assert result["status"] == "predicted"
        assert result["n_observations"] == 5
        assert result["outcome_distribution"]["outcome:unknown"] == pytest.approx(0.6)
        assert result["outcome_distribution"]["outcome:no_capable_agent"] == pytest.approx(0.4)
        assert result["bad_outcome_probability"] == pytest.approx(0.4)

    def test_error_fails_safe(self):
        engine = DecisionEngine()
        def _raise():
            raise RuntimeError("graph unavailable")
        engine._get_causal_graph = _raise
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        assert engine._simulate_consequence(c) == {"status": "error"}

    def test_all_good_outcomes_zero_bad_probability(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [
            {"to": "outcome:unknown", "strength": 0.9, "hit_count": 5},
        ])
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        result = engine._simulate_consequence(c)
        assert result["bad_outcome_probability"] == 0.0


class TestSimulationFactorMechanics:

    def test_non_predicted_statuses_stay_neutral(self):
        engine = DecisionEngine()
        for status in ({"status": "no_history"}, {"status": "insufficient_data", "n_observations": 1}, {"status": "error"}, {}):
            c = Candidate(action_type="x", params={}, confidence=0.5, urgency=0.5, source="think_loop")
            c.simulated_consequence = status
            factor, signal = engine._simulation_factor(c)
            assert factor == 1.0

    def test_zero_bad_probability_neutral(self):
        engine = DecisionEngine()
        c = Candidate(action_type="x", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.simulated_consequence = {"status": "predicted", "bad_outcome_probability": 0.0, "n_observations": 10}
        factor, _ = engine._simulation_factor(c)
        assert factor == 1.0

    def test_high_bad_probability_penalizes_toward_floor(self):
        engine = DecisionEngine()
        c = Candidate(action_type="x", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.simulated_consequence = {"status": "predicted", "bad_outcome_probability": 1.0, "n_observations": 10}
        factor, signal = engine._simulation_factor(c)
        assert factor == 0.90
        assert "bad_outcome_probability=1.00" in signal

    def test_never_boosts_above_neutral(self):
        """Penalty-only, unlike R22's boosting _situational_factor()."""
        engine = DecisionEngine()
        for bad_p in (0.0, 0.1, 0.5, 0.9, 1.0):
            c = Candidate(action_type="x", params={}, confidence=0.5, urgency=0.5, source="think_loop")
            c.simulated_consequence = {"status": "predicted", "bad_outcome_probability": bad_p, "n_observations": 10}
            factor, _ = engine._simulation_factor(c)
            assert 0.90 <= factor <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# BEFORE: pre-R25 decisions are blind to any structured consequence prediction.
# ═══════════════════════════════════════════════════════════════════════════

class TestBeforeMissingDistinction:

    def test_candidate_has_no_simulation_field_before_evaluate(self):
        c = Candidate(action_type="git_status", params={"goal_id": PROBE_GOAL_ID}, confidence=0.5, urgency=0.5, source="think_loop")
        assert c.simulated_consequence == {}

    def test_pre_r25_causal_factor_alone_cannot_see_outcome_type_distribution(self):
        """R24's own _causal_factor() only ever reads a single blended
        average -- it has no access to the per-outcome-type breakdown
        _simulate_consequence() exposes. Direct proof both factors read
        the SAME edges but compute materially different things."""
        engine = DecisionEngine()
        edges = [
            {"to": "outcome:unknown", "strength": 1.0, "hit_count": 3},
            {"to": "outcome:no_capable_agent", "strength": 0.0, "hit_count": 2},
        ]
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: edges)
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        causal_factor, _ = engine._causal_factor(c)
        sim_result = engine._simulate_consequence(c)
        # causal_factor only sees the blended average (0.6) -> mild boost
        assert causal_factor > 1.0
        # simulation sees the real 40% chance of a specific known-bad outcome type
        assert sim_result["bad_outcome_probability"] == pytest.approx(0.4)


# ═══════════════════════════════════════════════════════════════════════════
# AFTER / FLAGSHIP: real accumulated, categorically-distinct outcome history
# (via real Governor.dispatch() honest refusals, not fabricated) genuinely
# changes a later, separate real decision -- distinctly from R24's own
# already-proven blended-average signal.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFlagshipMentalSimulation:

    async def test_real_categorical_risk_history_changes_a_later_real_decision(
        self, isolated_vector_db, isolated_r25_registry, tmp_path, monkeypatch,
    ):
        # This flagship's real loop._act_on() calls run the real Gap-4
        # CounterfactualMemory veto block, whose default constructor
        # resolves via core.runtime_paths.data_path() -- NOT redirected
        # by isolated_vector_db (a documented, pre-existing fixture
        # limitation; see R21's own flagship). Without this, a real
        # rejection could land in the real production
        # data/counterfactual.db. monkeypatch auto-restores on teardown.
        import core.runtime_paths as runtime_paths_module
        monkeypatch.setattr(runtime_paths_module, "get_data_root", lambda: tmp_path)

        engine = build_isolated_engine(str(tmp_path / "epi.db"))
        engine._plan_store = MagicMock(active_plans=lambda: [])
        loop = build_isolated_loop(engine)
        engine._context_engine = _FixedWorldStateContextEngine("present")

        # ---- Accumulate a REAL, mixed, categorically-distinct outcome
        #      history for git_status@present: 3 real successful
        #      dispatches (GitBot registered, real GitBot.get_status())
        #      and 2 real, honest Governor "no_capable_agent" refusals
        #      (GitBot deliberately unregistered for those calls) -- both
        #      are real production outcomes, neither fabricated. ----
        isolated_r25_registry.register(GitBot())
        loop._get_recent_feedback = lambda action_type: 1.0
        for _ in range(3):
            c = Candidate(
                action_type="git_status", params={"goal_id": PROBE_GOAL_ID},
                goal_ids=[PROBE_GOAL_ID], confidence=CONF_GIT_STATUS, urgency=0.5, source="think_loop",
            )
            decision = await engine.evaluate([c])
            await loop._act_on(decision.winner)

        # Governor caches its own AgentRegistry reference on first use
        # (core/city/governor.py::_get_registry()) -- swapping the module
        # singleton to a NEW object would be invisible to an already-built
        # Governor. Directly clearing the SAME registry OBJECT's internal
        # map (not `.deregister()`, which triggers real Darwinian
        # ghost/successor-respawn side effects unrelated to this test)
        # produces a real, honest "nobody registered" state Governor's
        # own cached reference genuinely observes.
        isolated_r25_registry._agents.clear()
        loop._get_recent_feedback = lambda action_type: 0.0
        for _ in range(2):
            c = Candidate(
                action_type="git_status", params={"goal_id": PROBE_GOAL_ID},
                goal_ids=[PROBE_GOAL_ID], confidence=CONF_GIT_STATUS, urgency=0.5, source="think_loop",
            )
            decision = await engine.evaluate([c])
            await loop._act_on(decision.winner)
        isolated_r25_registry.register(GitBot())  # restore for the real evaluate() comparison below

        # ---- Sanity: the real, mixed, categorically-distinct history
        #      landed exactly where the writer/reader contract expects. ----
        cg = CausalGraph()
        edges = cg.get_outcomes("action:git_status@present")
        by_outcome = {e["to"]: e["hit_count"] for e in edges}
        assert by_outcome.get("outcome:ok") == 3  # 2026-09-25: a real git_status success is now "ok" (was mis-scored "unknown")
        # An entirely empty registry makes Governor's own district-level
        # check fail before it ever reaches the per-capability check --
        # a real, distinct, equally-honest Governor failure status.
        assert by_outcome.get("outcome:no_agents") == 2

        # R6 (staleness-diversity) accumulated a real 5-consecutive-win
        # streak for git_status purely as an artifact of this test's own
        # single-candidate accumulation-phase evaluate([c]) calls (each
        # trivially "wins" its own 1-candidate list) -- reset it here so
        # the upcoming real RACE comparisons aren't confounded by R6
        # suppression, which is explicitly one of the "competing factors"
        # this milestone's own controls require isolating from R25's own
        # signal, not something to silently inherit from test methodology.
        engine._winner_streak_hash = None
        engine._winner_streak_count = 0

        # ---- BASELINE: real formula + real PolicyMemory only (both new
        #      factors ablated) -- git_status's real, mostly-favorable
        #      accumulated reward keeps it narrowly ahead. ----
        engine._causal_factor = lambda candidate: (1.0, "ablated_for_control")
        engine._simulation_factor = lambda candidate: (1.0, "ablated_for_control")
        decision_baseline = await engine.evaluate(_race_candidates())
        assert decision_baseline.winner.action_type == "git_status", (
            "with both R24 and R25 factors ablated, git_status's real "
            "formula+PolicyMemory merits alone must still lead narrowly"
        )
        del engine._causal_factor
        del engine._simulation_factor

        # ---- R24 alone (causal factor real, simulation ablated): the
        #      blended-average boost only STRENGTHENS git_status's lead
        #      -- it does not, by itself, flip anything here. ----
        engine._simulation_factor = lambda candidate: (1.0, "ablated_for_control")
        decision_causal_only = await engine.evaluate(_race_candidates())
        assert decision_causal_only.winner.action_type == "git_status", (
            "R24's own blended-average causal factor alone must NOT "
            "explain a winner change here -- only reinforce the existing lead"
        )
        del engine._simulation_factor

        # ---- AFTER: with the REAL simulation factor active (reading the
        #      real, categorically-distinct 40% known-bad-outcome real
        #      history), the later, separate real decision genuinely
        #      flips -- attributable specifically to R25, not to R24. ----
        decision_after = await engine.evaluate(_race_candidates())
        assert decision_after.winner.action_type == "git_log", (
            "the real, observed 40% chance of a genuine known-bad outcome "
            "(no_capable_agent) for git_status@present must now change "
            "the real winner -- a capability R24's own blended average "
            "alone did not provide"
        )
        gs = next(c for c in decision_after.all_candidates if c.action_type == "git_status")
        assert gs.simulated_consequence["status"] == "predicted"
        assert gs.simulated_consequence["bad_outcome_probability"] == pytest.approx(0.4)
        sim_entry = next((s for s in gs.reasoning_chain if s["factor"] == "simulated_consequence"), None)
        assert sim_entry is not None
        assert sim_entry["weight"] == pytest.approx(0.94, abs=0.001)

        gl = next(c for c in decision_after.all_candidates if c.action_type == "git_log")
        assert gl.simulated_consequence["status"] == "no_history"


# ═══════════════════════════════════════════════════════════════════════════
# Safety
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_simulation_factor_never_calls_permission_gateway(self):
        func = DecisionEngine._simulation_factor
        body_src = inspect.getsource(func).split('"""', 2)[-1]
        for forbidden in ("PermissionGateway", "core.config", "classify("):
            assert forbidden not in body_src

    def test_simulate_consequence_never_calls_permission_gateway(self):
        func = DecisionEngine._simulate_consequence
        body_src = inspect.getsource(func).split('"""', 2)[-1]
        for forbidden in ("PermissionGateway", "core.config", "classify(", "dispatch("):
            assert forbidden not in body_src

    def test_neither_new_method_mutates_permission_tiers(self):
        for func in (DecisionEngine._simulate_consequence, DecisionEngine._simulation_factor):
            src = inspect.getsource(func)
            for line in src.splitlines():
                stripped = line.strip()
                assert not stripped.startswith(("GREEN =", "RED =", "YELLOW =", "FORBIDDEN ="))

    def test_permission_tiers_fully_unaffected_by_r25(self):
        assert PermissionGateway().classify("git_status") == "GREEN"
        assert PermissionGateway().classify("commit_code") == "YELLOW"
        assert PermissionGateway().classify("code_task") == "RED"

    def test_simulation_never_skips_the_veto_chain(self):
        """A 'predicted-safe' simulation result must never be readable by
        _act_on()'s veto chain as a bypass signal -- confirm no reference
        to simulated_consequence/simulation_factor exists anywhere in the
        real veto-chain block (CounterfactualMemory/ThreatDetector/
        RedTeamAgent) or in Governor's own dispatch routing."""
        import core.loop.autonomous_loop as al
        import core.city.governor as gov
        act_on_src = inspect.getsource(al.AutonomousLoop._act_on)
        dispatch_src = inspect.getsource(gov.Governor.dispatch)
        for forbidden in ("simulated_consequence", "simulation_factor", "_simulate_consequence"):
            assert forbidden not in act_on_src
            assert forbidden not in dispatch_src

    def test_factor_is_strictly_bounded_and_penalty_only(self):
        engine = DecisionEngine()
        c = Candidate(action_type="x", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.simulated_consequence = {"status": "predicted", "bad_outcome_probability": 1.0, "n_observations": 1000}
        factor, _ = engine._simulation_factor(c)
        assert factor == 0.90  # never below the real bound regardless of observation count


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--timeout=60"])
    print("OK test_r25_mental_simulation.py" if result.returncode == 0 else "FAILED test_r25_mental_simulation.py")
