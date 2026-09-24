"""
R24 — Causal Reasoning + Consequence Prediction.

Phase 1's converged investigation (see VECTOR_TECHNICAL_KNOWLEDGE/
R24_R26_ORCHESTRATOR_LEDGER.md -- 5 investigators covering all 9 named
angles, including a fresh adversarial reviewer with no inherited
context, independently reconstructing the same picture) found a real,
already-production-wired, SQLite-backed causal substrate
(`core/memory/causal_graph.py::CausalGraph`, "Gap 6") that received a
real write on every real dispatched action's real outcome -- but was,
before this milestone, structurally incapable of supporting a genuine
causal claim for two independent reasons, both closed here:

1. STATE-BLIND: the real writer (`autonomous_loop.py`'s post-outcome
   Gap-6 block) keyed nodes on `action:{action_type}` alone -- zero
   antecedent-state dimension, collapsing "action A under state S1" and
   "action A under state S2" into one indistinguishable node. Fixed by
   `causal_state_key()` (this file's own real, shared helper, reused by
   BOTH the writer and the reader) -- scoping every real edge by the
   SAME real `context_snapshot["presence"]` field R22's own
   `_situational_factor()` already established as real and proven.

2. OVERWRITE-NOT-ACCUMULATE: `CausalGraph.add_edge()`'s `INSERT OR
   REPLACE` on `PRIMARY KEY(from_id, to_id)` meant a repeat observation
   silently discarded the prior strength rather than accumulating it --
   `strength` was "whatever the single most recent reward happened to
   be," never a statistically meaningful signal, and no observation
   count existed anywhere. Fixed by making `add_edge()` compute a real
   running average + real `hit_count`, and gating `DecisionEngine.
   _causal_factor()` on `CAUSAL_MIN_OBSERVATIONS` before it ever
   deviates from neutral -- mirroring this codebase's own established
   `PolicyMemory.rank_actions()` `sample_count >= 3` precedent for when
   an aggregate is honest rather than fabricated confidence.

Zero new subsystem, zero new memory store, zero new table -- the
already-real, already-populated graph was extended (one migration-safe
column) and, for the first time, actually READ by a real decision path.
`CausalReasoner`'s pre-existing, independently-confirmed `source`/
`target` vs. `from`/`to` key-mismatch bug (core/causal/causal_reasoner.py)
is a real, separate, pre-existing defect this milestone does NOT depend
on or touch (R24 reads `CausalGraph` directly, never through
`CausalReasoner`) -- deliberately deferred, not silently inherited.
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
from core.memory.causal_graph import CausalGraph, causal_state_key
from districts.coding.git_bot import GitBot

from tests.test_r13_production_learning_validation import build_isolated_engine, build_isolated_loop

PROBE_GOAL_ID = "g_r24_probe"
# RR-2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/RR2_MEANINGFUL_UTILITY_REPORT.md):
# was 0.3/0.6. RR-2 corrected _act_on()'s reward formula so an unknown-
# goal-progress outcome no longer defaults to a fabricated 0.5, lowering
# the real reward (and PolicyMemory score) this flagship's own seeded
# git_status/git_log history earns per action from ~0.825 to 0.70, and
# correspondingly shrinking R24's own causal-factor multiplier (which
# scales with that same strength) from 1.0325 to 1.02. At the old 0.3/0.6
# gap, git_status's real formula+PolicyMemory+causal merits could no
# longer overcome git_log's larger raw confidence edge even with the
# real causal boost applied -- collapsing both this file's own flagship
# (git_status never re-took the lead) and its intervention-control twin
# (the swapped-roles race never flipped to git_log either). Retuned to
# 0.4/0.58 (found by directly running evaluate() against the real,
# corrected formula) so the causally-boosted candidate still narrowly
# retakes the lead in both directions -- not a fabricated number, a
# recalibration of the race's own candidate confidence to restore the
# real narrow-margin condition this test's narrative depends on.
# 2026-09-25 recalibration: a real, successful git_status is no longer scored as a failure (the reward code now
# accepts a real "branch" as evidence of success), so its learned strength rose 0.70 -> 0.75 and it out-scored
# git_log at 0.58 even with the causal factor ablated. The narrow-margin condition holds again for git_log
# confidence 0.62..0.64 (found by running the suite over that range); 0.63 is the middle of the passing window.
CONF_GIT_STATUS = 0.4
CONF_GIT_LOG = 0.63  # 2026-09-25: was 0.58; see the note below


class _FixedWorldStateContextEngine:
    """Same real-shaped stand-in R22/R23's own flagships used for the ONE
    external sensor/IO boundary `evaluate()` reads -- everything
    downstream (the real formula, real _causal_factor(), real ranking)
    runs completely unmodified."""

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
    """Two real, materially different, real GREEN action_types (both real
    GitBot capabilities), a real, deliberately narrow real-formula-only
    edge for git_log (favored by a real confidence gap the base formula
    alone cannot let git_status overcome -- see the flagship's own
    ablation control), so any winner flip TO git_status is attributable
    only to a real, additional, non-formula signal."""
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
def isolated_r24_registry():
    import core.city.agent_registry as registry_mod
    original = registry_mod._registry_singleton
    fresh = AgentRegistry()
    registry_mod._registry_singleton = fresh
    yield fresh
    registry_mod._registry_singleton = original


# ═══════════════════════════════════════════════════════════════════════════
# Fast, no-dispatch unit tests: the shared state-key helper + CausalGraph's
# own real accumulation logic + _causal_factor()'s mechanics in isolation.
# ═══════════════════════════════════════════════════════════════════════════

class TestCausalStateKey:

    def test_real_presence_values_pass_through(self):
        assert causal_state_key({"presence": "present"}) == "present"
        assert causal_state_key({"presence": "absent"}) == "absent"
        assert causal_state_key({"presence": "unknown"}) == "unknown"

    def test_malformed_input_fails_safe_to_unknown(self):
        assert causal_state_key(None) == "unknown"
        assert causal_state_key({}) == "unknown"
        assert causal_state_key({"presence": "bogus"}) == "unknown"
        assert causal_state_key("not a dict") == "unknown"


class TestCausalGraphAccumulation:

    def test_repeat_edges_accumulate_not_overwrite(self, tmp_path):
        cg = CausalGraph(json_path=str(tmp_path / "cg1.json"))
        cg.add_node("action:x", "action", "x")
        cg.add_node("outcome:y", "outcome", "y")
        cg.add_edge("action:x", "outcome:y", strength=1.0)
        cg.add_edge("action:x", "outcome:y", strength=0.0)
        edge = next(e for e in cg.get_all_edges() if e["from"] == "action:x" and e["to"] == "outcome:y")
        assert edge["hit_count"] == 2
        assert abs(edge["strength"] - 0.5) < 1e-9

    def test_third_observation_continues_the_real_running_average(self, tmp_path):
        cg = CausalGraph(json_path=str(tmp_path / "cg2.json"))
        cg.add_node("action:x", "action", "x")
        cg.add_node("outcome:y", "outcome", "y")
        cg.add_edge("action:x", "outcome:y", strength=1.0)
        cg.add_edge("action:x", "outcome:y", strength=1.0)
        cg.add_edge("action:x", "outcome:y", strength=0.0)
        edge = next(e for e in cg.get_all_edges() if e["from"] == "action:x" and e["to"] == "outcome:y")
        assert edge["hit_count"] == 3
        assert abs(edge["strength"] - (2.0 / 3.0)) < 1e-9

    def test_single_observation_hit_count_one(self, tmp_path):
        cg = CausalGraph(json_path=str(tmp_path / "cg3.json"))
        cg.add_node("action:x", "action", "x")
        cg.add_node("outcome:y", "outcome", "y")
        cg.add_edge("action:x", "outcome:y", strength=0.7)
        edge = cg.get_outcomes("action:x")[0]
        assert edge["hit_count"] == 1
        assert edge["strength"] == pytest.approx(0.7)

    def test_distinct_state_scoped_node_ids_are_independent_edges(self, tmp_path):
        cg = CausalGraph(json_path=str(tmp_path / "cg4.json"))
        cg.add_node("action:x@present", "action", "x")
        cg.add_node("action:x@absent", "action", "x")
        cg.add_node("outcome:y", "outcome", "y")
        cg.add_edge("action:x@present", "outcome:y", strength=1.0)
        cg.add_edge("action:x@absent", "outcome:y", strength=0.0)
        present_edges = cg.get_outcomes("action:x@present")
        absent_edges = cg.get_outcomes("action:x@absent")
        assert present_edges[0]["strength"] == pytest.approx(1.0)
        assert absent_edges[0]["strength"] == pytest.approx(0.0)
        assert present_edges[0]["hit_count"] == 1
        assert absent_edges[0]["hit_count"] == 1


class TestCausalFactorMechanics:

    def test_no_history_neutral(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [])
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        factor, signal = engine._causal_factor(c)
        assert factor == 1.0
        assert signal == "no_causal_history"

    def test_insufficient_observations_stays_neutral(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [
            {"strength": 1.0, "hit_count": 2},
        ])
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        factor, signal = engine._causal_factor(c)
        assert factor == 1.0
        assert "insufficient_observations" in signal

    def test_well_observed_favorable_history_boosts(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [
            {"strength": 1.0, "hit_count": 5},
        ])
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        factor, signal = engine._causal_factor(c)
        assert factor == 1.05
        assert "strength=1.00" in signal and "n=5" in signal

    def test_well_observed_unfavorable_history_penalizes(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [
            {"strength": 0.0, "hit_count": 5},
        ])
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        factor, signal = engine._causal_factor(c)
        assert factor == 0.95

    def test_error_fails_safe_neutral(self):
        engine = DecisionEngine()
        def _raise():
            raise RuntimeError("graph unavailable")
        engine._get_causal_graph = _raise
        c = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        factor, signal = engine._causal_factor(c)
        assert factor == 1.0
        assert signal == "error"

    def test_scope_control_state_key_selects_only_the_matching_edge(self):
        """A candidate's own current state key is the ONLY thing that
        determines which real edge it can see -- an edge recorded under a
        different real state is architecturally invisible."""
        engine = DecisionEngine()
        calls = []
        def _get_outcomes(action_id):
            calls.append(action_id)
            return [] if "@absent" in action_id else [{"strength": 1.0, "hit_count": 5}]
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=_get_outcomes)
        c_present = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c_present.context_snapshot = {"presence": "present"}
        c_absent = Candidate(action_type="git_status", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c_absent.context_snapshot = {"presence": "absent"}
        f_present, _ = engine._causal_factor(c_present)
        f_absent, s_absent = engine._causal_factor(c_absent)
        assert f_present == 1.05
        assert f_absent == 1.0 and s_absent == "no_causal_history"
        assert calls == ["action:git_status@present", "action:git_status@absent"]

    def test_factor_always_within_bounds(self):
        engine = DecisionEngine()
        for strength in (0.0, 0.25, 0.5, 0.75, 1.0):
            engine._get_causal_graph = lambda strength=strength: MagicMock(
                get_outcomes=lambda aid: [{"strength": strength, "hit_count": 10}]
            )
            c = Candidate(action_type="x", params={}, confidence=0.5, urgency=0.5, source="think_loop")
            c.context_snapshot = {"presence": "present"}
            factor, _ = engine._causal_factor(c)
            assert 0.95 <= factor <= 1.05


# ═══════════════════════════════════════════════════════════════════════════
# BEFORE: pre-R24 scoring components are blind to causal history.
# ═══════════════════════════════════════════════════════════════════════════

class TestBeforeMissingDistinction:

    def test_pre_r24_formula_components_blind_to_causal_history(self):
        engine = DecisionEngine()
        c1 = Candidate(action_type="git_status", params={"goal_id": PROBE_GOAL_ID}, confidence=0.5, urgency=0.5, source="think_loop")
        c2 = Candidate(action_type="git_status", params={"goal_id": PROBE_GOAL_ID}, confidence=0.5, urgency=0.5, source="think_loop")
        assert engine._score_goal_alignment(c1) == engine._score_goal_alignment(c2)
        assert engine._make_situation_hash(c1) == engine._make_situation_hash(c2)

    def test_pre_r24_causal_graph_had_no_state_dimension(self):
        """Direct proof of the exact real gap this milestone closes: before
        `causal_state_key()`, two real edges for the same action_type under
        materially different real states were architecturally
        indistinguishable -- the OLD node-id scheme (`action:{action_type}`
        alone, still constructible today) cannot tell them apart."""
        old_style_id_present = "action:git_status"
        old_style_id_absent = "action:git_status"
        assert old_style_id_present == old_style_id_absent
        new_style_present = f"action:git_status@{causal_state_key({'presence': 'present'})}"
        new_style_absent = f"action:git_status@{causal_state_key({'presence': 'absent'})}"
        assert new_style_present != new_style_absent


# ═══════════════════════════════════════════════════════════════════════════
# AFTER / FLAGSHIP: real accumulated experience, through the real
# evaluate() -> _act_on() -> Governor -> GitBot -> outcome -> writer path,
# genuinely changes a LATER, SEPARATE real decision (L0-L4 per the
# mission's own classification).
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestFlagshipCausalReasoning:

    async def test_real_accumulated_history_changes_a_later_real_decision(
        self, isolated_vector_db, isolated_r24_registry, tmp_path, monkeypatch,
    ):
        # This flagship's real loop._act_on() calls run the real Gap-4
        # CounterfactualMemory veto block, whose default constructor
        # resolves via core.runtime_paths.data_path() -- NOT redirected
        # by isolated_vector_db (a documented, pre-existing fixture
        # limitation; see R21's own flagship, which established this
        # exact isolation). Without it, a real rejection could land in
        # the real production data/counterfactual.db. monkeypatch
        # auto-restores on teardown regardless of pass/fail.
        import core.runtime_paths as runtime_paths_module
        monkeypatch.setattr(runtime_paths_module, "get_data_root", lambda: tmp_path)

        isolated_r24_registry.register(GitBot())
        engine = build_isolated_engine(str(tmp_path / "epi.db"))
        engine._plan_store = MagicMock(active_plans=lambda: [])
        loop = build_isolated_loop(engine)
        # The ONE external boundary override this flagship needs: real user
        # feedback is itself sourced from real prior user actions in
        # production (episodic recall) -- controlling it here is the same
        # class of isolation as R22's _FixedWorldStateContextEngine (one
        # real external sensor/signal boundary), not a manufactured belief.
        loop._get_recent_feedback = lambda action_type: 1.0

        # ---- L3: accumulate REAL causal + policy history via the REAL
        #      production pipeline (evaluate -> real winner -> real
        #      _act_on -> real Governor.dispatch -> real GitBot ->
        #      real outcome -> real CausalGraph/PolicyMemory writes),
        #      3x, all under a real, isolated presence="present" state. ----
        engine._context_engine = _FixedWorldStateContextEngine("present")
        for _ in range(3):
            c = Candidate(
                action_type="git_status", params={"goal_id": PROBE_GOAL_ID},
                goal_ids=[PROBE_GOAL_ID], confidence=CONF_GIT_STATUS, urgency=0.5, source="think_loop",
            )
            decision = await engine.evaluate([c])
            await loop._act_on(decision.winner)

        # ---- Sanity: the real accumulated facts landed exactly where
        #      the real writer/reader contract expects. ----
        cg = CausalGraph()
        edges = cg.get_outcomes("action:git_status@present")
        assert edges, "the real writer must have created a real, state-scoped edge"
        assert edges[0]["hit_count"] == 3
        # RR-2: was 0.825 -- the real reward for this repeated,
        # unknown-goal-progress action is now 0.70 (unknown progress no
        # longer defaults to a fabricated 0.5). See module-level RR-2 note.
        # 2026-09-25: 0.75 -- a real, successful git_status now counts as a success (its result has no
        # "status" key but a real "branch", which _act_on() now accepts as evidence). It used to be scored as a
        # failure, which is where the old 0.70 came from.
        assert edges[0]["strength"] == pytest.approx(0.75, abs=0.01)

        pm = loop._get_policy()
        h = pm.make_situation_hash("git_status", {"goal_id": PROBE_GOAL_ID})
        assert pm.get_score("git_status", h) == pytest.approx(0.75, abs=0.01)

        # ---- L0 ABLATION / COMPETING-FACTOR CONTROL: the SAME real,
        #      accumulated PolicyMemory data, with ONLY the causal factor
        #      forced neutral -- proves PolicyMemory's own real 20%-
        #      weighted boost for git_status is NOT, by itself, enough to
        #      overcome git_log's real confidence edge. ----
        engine._causal_factor = lambda candidate: (1.0, "ablated_for_control")
        decision_baseline = await engine.evaluate(_race_candidates())
        assert decision_baseline.winner.action_type == "git_log", (
            "with the causal factor ablated, git_log's real confidence "
            "edge must still decide the race on its own real formula "
            "merits -- PolicyMemory's real favorable history alone is "
            "not sufficient to flip it"
        )
        del engine._causal_factor  # restore the real bound method

        # ---- L4: AFTER, under the SAME real state the history was learned
        #      under, the real causal factor now genuinely changes the
        #      later, separate decision's real winner. ----
        decision_present = await engine.evaluate(_race_candidates())
        assert decision_present.winner.action_type == "git_status", (
            "the real, accumulated, favorable causal history for "
            "git_status@present must now genuinely change the real winner"
        )
        gs = next(c for c in decision_present.all_candidates if c.action_type == "git_status")
        causal_entry = next((s for s in gs.reasoning_chain if s["factor"] == "causal_prediction"), None)
        assert causal_entry is not None
        # RR-2: was 1.0325 -- the causal factor is 1.0 + (strength-0.5)*0.1;
        # with the real, RR-2-corrected strength now 0.70 (not 0.825),
        # the real factor is 1.02. See module-level RR-2 note.
        # 2026-09-25: strength is now 0.75 -> factor 1.0 + (0.75-0.5)*0.1 = 1.025.
        assert causal_entry["weight"] == pytest.approx(1.025, abs=0.001)

        # ---- SCOPE CONTROL: under a DIFFERENT real state (git_status was
        #      NEVER dispatched under "absent"), the exact same real,
        #      accumulated graph must NOT leak the favorable history in --
        #      the real winner reverts to the real baseline. ----
        engine._context_engine = _FixedWorldStateContextEngine("absent")
        decision_absent = await engine.evaluate(_race_candidates())
        assert decision_absent.winner.action_type == "git_log", (
            "git_status's real history was learned ONLY under "
            "presence=present -- it must not influence an unrelated "
            "presence=absent decision"
        )
        gs_absent = next(c for c in decision_absent.all_candidates if c.action_type == "git_status")
        causal_entry_absent = next((s for s in gs_absent.reasoning_chain if s["factor"] == "causal_prediction"), None)
        assert causal_entry_absent is None, "no_causal_history stays neutral -> no reasoning_chain entry"

    async def test_intervention_control_winner_follows_the_dispatched_candidate_not_a_hardcoded_name(
        self, isolated_vector_db, isolated_r24_registry, tmp_path, monkeypatch,
    ):
        """Swap which real action_type accumulates the favorable real
        history (git_log this time, not git_status) and swap the base
        confidence edge accordingly -- the winner must follow the ACTUAL
        candidate with real history, proving this isn't a hardcoded
        `action_type == "git_status"` special case anywhere in
        `_causal_factor()`."""
        import core.runtime_paths as runtime_paths_module
        monkeypatch.setattr(runtime_paths_module, "get_data_root", lambda: tmp_path)

        isolated_r24_registry.register(GitBot())
        engine = build_isolated_engine(str(tmp_path / "epi_swap.db"))
        engine._plan_store = MagicMock(active_plans=lambda: [])
        loop = build_isolated_loop(engine)
        loop._get_recent_feedback = lambda action_type: 1.0
        engine._context_engine = _FixedWorldStateContextEngine("present")

        for _ in range(3):
            c = Candidate(
                action_type="git_log", params={"goal_id": PROBE_GOAL_ID},
                goal_ids=[PROBE_GOAL_ID], confidence=CONF_GIT_LOG, urgency=0.5, source="think_loop",
            )
            decision = await engine.evaluate([c])
            await loop._act_on(decision.winner)

        # Swapped confidences: now git_status (CONF_GIT_LOG, the higher
        # value) has the real formula merit edge, git_log (CONF_GIT_STATUS,
        # the lower value) has the real accumulated favorable causal
        # history. RR-2: was the literal 0.6/0.3 -- now reuses the same
        # module-level constants (0.58/0.4) the non-swapped flagship above
        # was itself recalibrated to, so both directions of this race are
        # tuned to the same real, RR-2-corrected margin.
        decision = await engine.evaluate(_race_candidates(conf_status=CONF_GIT_LOG, conf_log=CONF_GIT_STATUS))
        assert decision.winner.action_type == "git_log", (
            "the real accumulated favorable history now belongs to "
            "git_log -- the winner must follow it, not stay pinned to "
            "whichever action_type won in the other flagship test"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Persistence: CausalGraph's real restart-survival (SQLite-backed).
# ═══════════════════════════════════════════════════════════════════════════

class TestPersistence:

    def test_accumulated_edge_survives_a_real_restart(self, isolated_vector_db):
        """Uses CausalGraph's REAL production constructor (no json_path --
        the same shared, disk-backed episodic SQLite connection the real
        writer/reader both use), with a genuine connection close+reopen
        between write and read -- the same restart-proof technique this
        repo's own `isolated_vector_db` fixture and R23's PlanStore proof
        both already established. The isolated `json_path=` mode (used by
        every other test in this file) is a private in-memory namespace
        for test isolation, not a genuine restart proof on its own."""
        cg = CausalGraph()
        cg.add_node("action:x@present", "action", "x")
        cg.add_node("outcome:y", "outcome", "y")
        cg.add_edge("action:x@present", "outcome:y", strength=0.9)
        cg.add_edge("action:x@present", "outcome:y", strength=0.9)
        cg.add_edge("action:x@present", "outcome:y", strength=0.9)

        from core.memory.episodic import close_db_connection
        close_db_connection()

        reloaded = CausalGraph()
        edges = reloaded.get_outcomes("action:x@present")
        assert edges
        assert edges[0]["hit_count"] == 3
        assert edges[0]["strength"] == pytest.approx(0.9, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════════════
# Safety
# ═══════════════════════════════════════════════════════════════════════════

class TestSafety:

    def test_causal_factor_never_calls_permission_gateway(self):
        func = DecisionEngine._causal_factor
        body_src = inspect.getsource(func).split('"""', 2)[-1]
        for forbidden in ("PermissionGateway", "core.config", "classify("):
            assert forbidden not in body_src

    def test_causal_factor_never_mutates_permission_tiers(self):
        src = inspect.getsource(DecisionEngine._causal_factor)
        for line in src.splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("GREEN =", "RED =", "YELLOW =", "FORBIDDEN ="))

    def test_permission_tiers_fully_unaffected_by_r24(self):
        assert PermissionGateway().classify("git_status") == "GREEN"
        assert PermissionGateway().classify("commit_code") == "YELLOW"
        assert PermissionGateway().classify("code_task") == "RED"

    def test_causal_write_path_never_touches_governor_or_permission_gateway(self):
        """The real production writer block (autonomous_loop.py) runs
        strictly AFTER real dispatch/execution has already happened and
        the real veto chain has already been passed -- it cannot suppress
        or bypass anything upstream of itself."""
        import core.loop.autonomous_loop as al
        src = inspect.getsource(al.AutonomousLoop._act_on)
        write_idx = src.index("Gap 6")
        governor_idx = src.index("_get_governor().dispatch(")
        assert governor_idx < write_idx, (
            "the real causal-graph write must occur strictly AFTER the "
            "real Governor.dispatch() call, never before/instead of it"
        )

    def test_factor_is_strictly_bounded_both_directions(self):
        engine = DecisionEngine()
        engine._get_causal_graph = lambda: MagicMock(get_outcomes=lambda aid: [
            {"strength": 1.0, "hit_count": 1000},
        ])
        c = Candidate(action_type="x", params={}, confidence=0.5, urgency=0.5, source="think_loop")
        c.context_snapshot = {"presence": "present"}
        factor, _ = engine._causal_factor(c)
        assert factor == 1.05  # never exceeds the real bound regardless of observation count


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v", "--timeout=60"])
    print("OK test_r24_causal_reasoning.py" if result.returncode == 0 else "FAILED test_r24_causal_reasoning.py")
