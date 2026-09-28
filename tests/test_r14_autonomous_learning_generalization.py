"""
R14 — Autonomous Learning Generalization.

R13 proved: real production-path experience -> real outcome-derived reward
-> persistent PolicyMemory update -> later fresh decision change. But
R13's flagship and multi-cycle tests called `bias_toward()` before every
real `_act_on()` execution -- confidence 0.95/0.1 -- to CHOOSE which real
GREEN action executed each cycle. That is experimenter steering, not
autonomous selection. R14's job is to remove it entirely from the primary
evidence and see what VECTOR's own, real, unmodified DecisionEngine
actually does and learns on its own.

============================================================
PHASE 1 — R13 METHODOLOGY AUDIT (see also the report's own section 3)
============================================================

Grepping tests/test_r13_production_learning_validation.py for every
`bias_toward(` call site (there are 20+) confirms: EVERY real `_act_on()`
execution in that file -- the flagship's 2, Control D's 2, Multi-Cycle's
6, and nearly every adversarial test's 1 -- was preceded by a
`bias_toward()` call forcing confidence to 0.95/0.1 for a specific,
test-chosen action_type. The only bias-FREE `evaluate()` calls in R13's
file were the "BASELINE" (before) and final "after" neutral checks -- and
those candidates were never passed to `_act_on()`. Zero real executions in
R13 were the product of the real DecisionEngine's own unbiased selection.
This file's job is to close exactly that gap.

============================================================
PHASE 2/3 — SCENARIO AND EMPIRICAL AUTONOMOUS BASELINE
============================================================

Reusing the same real, existing goal-tag pattern R13 used
(tags=["git","coding"], mirroring the real `g_daily_commit` goal) --
per the mission's own "do not create artificial goals merely to make this
possible" instruction, and because this session's own audit (R12/R13)
already established it is the ONLY real goal pattern with >= 2 legitimate
GREEN strategies (git_status, read_code) alongside a RED one (code_task)
that must never autonomously execute.

Empirically observed via this session's own isolated, bias-free scratch
probe (fully isolated: tmp VECTOR_DB_PATH, tmp VECTOR_TEST_DATA_DIR,
isolated AgentRegistry with only GitBot+ArchitectBot registered -- same
isolation as R13):

  Cycle 1 (zero learning, all 3 candidates' confidence/urgency IDENTICAL,
  no bias_toward call anywhere): all 3 total_scores tie at 0.4 (policy=0.5
  default for all). `max()`'s stable tie-break picks the FIRST candidate
  in generation order -- git_status (from tag "git", processed before
  "coding"'s code_task/read_code). git_status is GREEN -- safe to execute
  autonomously without any human/test override. Real execution (real
  GitBot.get_status()) -> real reward, pre-RR-2 0.545 (honestly capped by
  a real return-shape gap in git_bot.py, not fabricated). Persisted.

  RR-2 UPDATE (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
  RR2_MEANINGFUL_UTILITY_REPORT.md): the paragraph below described a real,
  but now DELIBERATELY REMOVED, architectural property -- that the reward
  floor for any non-failing dispatch (~0.545 under the OLD fabricated
  goal_progress=0.5 default) sat always above PolicyMemory.DEFAULT_SCORE
  (0.5), guaranteeing an autonomously-selected GREEN action could only
  ever reinforce itself. Under the corrected formula (see
  TestRewardQualityAudit.test_reward_floor_no_longer_guarantees_
  reinforcement) that floor is ~0.42 -- now BELOW default. This file's own
  assertions (score_after_cycle_1 != DEFAULT_SCORE, etc.) were written
  direction-agnostically and still hold either way; whether git_status's
  real cycle-2+ total_score still exceeds the untouched alternatives'
  frozen-at-default score, or is now overtaken by one of them, is no
  longer assumed here -- both are legitimate, honestly-observable
  outcomes this test does not force in either direction. Historical
  narrative (kept for provenance, not re-verified numerically): under the
  OLD formula git_status won 7/7 real autonomous cycles with a widening
  margin, reward converging on 0.545.

This file proves the full autonomous select->act->observe->reward->
persist->reselect loop is real (Phase 6-9) regardless of which specific
direction (reinforcement vs. a possible switch) the corrected reward
formula now produces empirically -- that distinction was, and remains,
explicitly out of this file's own claim (Phase 10: "AUTONOMOUS LEARNING
LOOP PROVEN BUT AUTONOMOUS EXPLORATION UNPROVEN"). No random exploration
was added to manufacture or prevent a flip -- the mission explicitly
forbids this.
"""
from __future__ import annotations

import datetime
import inspect
import sys
from pathlib import Path

import pytest
from tests._small_scan import small_scan_root  # noqa: F401  (autouse: real read_code scan over a small project)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.brain.epistemic_tracker import EpistemicTracker
from core.brain.goal_system import GoalSystem
from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate, DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory

# Reuse R13's proven isolation infrastructure rather than duplicating it --
# same real GitBot/ArchitectBot registry, same episodic/epistemic isolation.
from tests.test_r13_production_learning_validation import (
    PROBE_GOAL_TITLE,
    build_isolated_engine,
    build_isolated_loop,
    isolated_agent_registry,
    isolated_probe_goal_system,
    native_candidates,
    read_reasoning_chain_for_decision,
)

R14_GOAL_ID_PREFIX = "g_r14"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _module_calls_bias_toward() -> bool:
    """AST-based (not regex/substring) check for whether this file
    actually INVOKES `bias_toward(...)` anywhere in real code -- robust
    against docstrings/comments that merely mention the function by name
    (including backtick-quoted markdown fragments like `` `bias_toward(` ``,
    which a naive "next char isn't ')'" regex incorrectly flags). Parses
    this module's own source and walks for any ast.Call whose function
    name is `bias_toward` -- the only way this could ever be true is a
    genuine call statement, never prose."""
    import ast
    import tests.test_r14_autonomous_learning_generalization as this_module
    tree = ast.parse(inspect.getsource(this_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name == "bias_toward":
                return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1 — R13 methodology audit, formalized as a passing test (not just a
# docstring claim).
# ═══════════════════════════════════════════════════════════════════════════

class TestR13MethodologyAudit:

    def test_every_r13_real_execution_was_experimenter_steered(self):
        """Formal confirmation of this file's own module docstring claim.
        Counts every `bias_toward(` call in R13's file and confirms it is
        non-zero (i.e., R13's real executions WERE steered) -- the precise
        gap R14 exists to close. Does not count the BASELINE/neutral
        observation-only evaluate() calls (which never reached _act_on())
        as executions at all."""
        import tests.test_r13_production_learning_validation as r13
        src = inspect.getsource(r13)
        # Precise count via the actual defining call sites (excludes the
        # function's own definition and docstring mentions).
        import re
        call_sites = re.findall(r"^\s+bias_toward\(", src, re.MULTILINE)
        assert len(call_sites) >= 15, (
            f"expected R13's real executions to be steered by bias_toward() "
            f"at (nearly) every call site -- found {len(call_sites)} call sites, "
            f"confirming the gap R14 closes"
        )

    def test_r13_neutral_evaluations_were_never_executed(self):
        """R13's own 'BASELINE'/'neutral' evaluate() calls (no bias) were
        real observations of what the engine WOULD pick -- but were never
        passed to _act_on(). Confirmed by reading R13's flagship test body:
        baseline_decision's winner is never passed to loop._act_on()."""
        import tests.test_r13_production_learning_validation as r13
        flagship_src = inspect.getsource(
            r13.TestFlagshipProductionLearning.test_real_autonomous_experience_changes_a_later_fresh_decision
        )
        # baseline_decision is computed and its winner inspected, but the
        # only _act_on() calls in the flagship operate on decision_a/decision_b
        # (both bias_toward()-steered), never baseline_decision.
        assert "await loop._act_on(baseline_decision" not in flagship_src
        assert flagship_src.count("await loop._act_on(") == 2  # decision_a, decision_b -- both biased


# ═══════════════════════════════════════════════════════════════════════════
# Phase 3/4/5/6/7 — the flagship: fully autonomous, bias-free selection,
# real execution, real outcome, real reward, persistence, autonomous
# second decision.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestAutonomousLearningFlagship:

    async def test_fully_autonomous_selection_execution_and_relearning(
        self, isolated_vector_db, isolated_agent_registry, tmp_path,
    ):
        """The R14 flagship. `native_candidates()` is called with a single,
        UNIFORM confidence for every candidate and `bias_toward()` is never
        called anywhere in this test -- the winner that gets executed is
        exactly whatever the real, unmodified DecisionEngine picks on its
        own."""
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()
        goal_id = f"{R14_GOAL_ID_PREFIX}_flagship"

        gs = isolated_probe_goal_system(goal_id=goal_id)

        # ---- Phase 3: TRUE AUTONOMOUS BASELINE ----
        candidates_1 = native_candidates(gs, confidence=0.5)  # neutral, uniform -- no bias_toward anywhere
        assert {c.action_type for c in candidates_1} == {"git_status", "code_task", "read_code"}
        assert len({c.confidence for c in candidates_1}) == 1, "no candidate may be pre-biased"
        assert len({c.urgency for c in candidates_1}) == 1, "no candidate may be pre-biased"

        decision_1 = await engine.evaluate(candidates_1)
        winner_1_type = decision_1.winner.action_type
        decision_id_1 = decision_1.winner.decision_id
        candidate_id_1 = decision_1.winner.candidate_id

        # Record full factor breakdown for every candidate (not just the winner).
        factor_snapshot_1 = {
            c.action_type: {f["factor"]: f["value"] for f in c.reasoning_chain}
            for c in decision_1.all_candidates
        }

        # ---- Safety gate BEFORE autonomous execution: the winner the engine
        # itself picked must be GREEN. If it were RED, this test would refuse
        # to execute it (see TestSafety below for the dedicated RED-cannot-
        # autoexecute proof) -- but this scenario's own real, tag-derived
        # generation order makes git_status (GREEN) the deterministic
        # zero-learning winner, confirmed empirically (see module docstring).
        tier_1 = PermissionGateway().classify(winner_1_type)
        assert tier_1 == "GREEN", (
            f"the autonomously-selected winner must be GREEN for this test to "
            f"safely auto-execute it -- got {winner_1_type} ({tier_1}). If this "
            f"ever changes (e.g. a future scoring change makes code_task win "
            f"the tie), this test must refuse to execute and report the "
            f"limitation rather than force a different action."
        )

        # ---- Phase 4: REAL EXECUTION of EXACTLY the autonomous winner ----
        await loop._act_on(decision_1.winner)  # real Governor, real district agent, no stubs

        # ---- Phase 5: REAL OUTCOME / REWARD ----
        h_1 = pm.make_situation_hash(winner_1_type, {"goal_id": goal_id, "title": PROBE_GOAL_TITLE})
        score_after_cycle_1 = pm.get_score(winner_1_type, h_1)
        # RR-2: git_status's real completed=0.0 (no "status" key) now yields
        # a below-default reward (~0.42), not above -- the old ">" direction
        # was itself an artifact of the fabricated goal_progress=0.5 default
        # this task removed (see test_reward_floor_no_longer_guarantees_
        # reinforcement). The test's real intent -- "the real executed
        # outcome must have genuinely moved the learned score away from
        # default" -- is preserved via "!=", without assuming a direction.
        assert score_after_cycle_1 != PolicyMemory.DEFAULT_SCORE, (
            "the real executed outcome must have genuinely moved the learned "
            "score away from default"
        )
        # Outcome attribution, exactly as R13 established.
        attribution_1 = read_reasoning_chain_for_decision(decision_id_1)
        assert attribution_1 is not None
        assert attribution_1["candidate_id"] == candidate_id_1
        assert attribution_1["action_taken"] == winner_1_type
        assert attribution_1["reward"] == pytest.approx(score_after_cycle_1, abs=0.001)

        # ---- Phase 6: PERSISTENCE ----
        from core.memory.episodic import close_db_connection
        close_db_connection()

        # ---- Phase 7: TRUE AUTONOMOUS SECOND DECISION -- still no bias ----
        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        engine2 = build_isolated_engine(str(tmp_path / "epistemic2.db"))
        candidates_2 = native_candidates(gs2, confidence=0.5)
        assert {c.action_type for c in candidates_2} == {"git_status", "code_task", "read_code"}, (
            "candidate generation must be unchanged by learning (Control G)"
        )
        assert len({c.confidence for c in candidates_2}) == 1
        assert len({c.urgency for c in candidates_2}) == 1

        decision_2 = await engine2.evaluate(candidates_2)
        winner_2_type = decision_2.winner.action_type

        # ---- Honest reporting: did the WINNER change? ----
        # RR-2 update (see module docstring): the reward formula's floor
        # for a successful-but-evidence-unknown dispatch is now ~0.42,
        # BELOW DEFAULT_SCORE (0.5) -- unlike the old formula, this no
        # longer guarantees a real, successfully-executing autonomous
        # choice can only reinforce itself. Whichever way this resolves is
        # reported honestly below, not forced in either direction.
        winner_changed = winner_2_type != winner_1_type

        # What DID demonstrably change: the winner's own internal scoring.
        factor_snapshot_2 = {
            c.action_type: {f["factor"]: f["value"] for f in c.reasoning_chain}
            for c in decision_2.all_candidates
        }
        assert factor_snapshot_2[winner_1_type]["policy_score"] == pytest.approx(score_after_cycle_1, abs=0.01)
        assert factor_snapshot_2[winner_1_type]["policy_score"] != factor_snapshot_1[winner_1_type]["policy_score"], (
            "the real learned experience must measurably change the "
            "DecisionEngine's own internal scoring for the action it "
            "actually executed, even where it does not change WHICH "
            "action wins"
        )
        assert decision_2.winner.total_score != decision_1.winner.total_score or winner_changed, (
            "learning must produce SOME measurable effect on the decision "
            "-- either a different winner, or a different score for the "
            "same winner"
        )

        # Record the honest verdict as an attribute other tests / the
        # report can rely on rather than re-deriving.
        TestAutonomousLearningFlagship.LAST_RESULT = {
            "winner_1": winner_1_type, "winner_2": winner_2_type,
            "winner_changed": winner_changed,
            "score_1": decision_1.winner.total_score, "score_2": decision_2.winner.total_score,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Phase 8 — Causal controls (R13's A-E retained/strengthened + new F/G/H/I)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestCausalControls:

    async def test_control_a_no_learning_no_change(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """No real execution at all between two autonomous evaluations --
        the winner and its total_score must be identical."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_control_a"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d1 = await engine.evaluate(native_candidates(gs, confidence=0.5))

        from core.memory.episodic import close_db_connection
        close_db_connection()

        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        engine2 = build_isolated_engine(str(tmp_path / "epistemic2.db"))
        d2 = await engine2.evaluate(native_candidates(gs2, confidence=0.5))

        assert d1.winner.action_type == d2.winner.action_type
        assert d1.winner.total_score == pytest.approx(d2.winner.total_score, abs=0.001)

    async def test_control_b_unrelated_goal_unaffected(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        goal_id = f"{R14_GOAL_ID_PREFIX}_control_b_probe"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()

        gs = isolated_probe_goal_system(goal_id=goal_id)
        d = await engine.evaluate(native_candidates(gs, confidence=0.5))
        await loop._act_on(d.winner)

        gs_unrelated = isolated_probe_goal_system(
            goal_id=f"{R14_GOAL_ID_PREFIX}_control_b_unrelated", title="An entirely unrelated goal",
        )
        d_unrelated = await engine.evaluate(native_candidates(gs_unrelated, confidence=0.5))
        h_unrelated = pm.make_situation_hash(
            d_unrelated.winner.action_type,
            {"goal_id": f"{R14_GOAL_ID_PREFIX}_control_b_unrelated", "title": "An entirely unrelated goal"},
        )
        assert pm.get_score(d_unrelated.winner.action_type, h_unrelated) == PolicyMemory.DEFAULT_SCORE

    async def test_control_c_persistence(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        goal_id = f"{R14_GOAL_ID_PREFIX}_control_c"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d = await engine.evaluate(native_candidates(gs, confidence=0.5))
        await loop._act_on(d.winner)
        h = pm.make_situation_hash(d.winner.action_type, {"goal_id": goal_id, "title": PROBE_GOAL_TITLE})
        before = pm.get_score(d.winner.action_type, h)

        from core.memory.episodic import close_db_connection
        close_db_connection()
        pm2 = PolicyMemory()
        after = pm2.get_score(d.winner.action_type, h)
        assert after == pytest.approx(before, abs=0.001)
        assert after != PolicyMemory.DEFAULT_SCORE

    async def test_control_d_wrong_candidate_attribution(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """Two autonomous cycles in a row (both unbiased) -- the second
        cycle's real reward must attribute only to the second cycle's real
        candidate_id, never the first's, even when (as expected) both
        cycles pick the same action_type."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_control_d"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_probe_goal_system(goal_id=goal_id)

        d1 = await engine.evaluate(native_candidates(gs, confidence=0.5))
        await loop._act_on(d1.winner)

        d2 = await engine.evaluate(native_candidates(gs, confidence=0.5))
        await loop._act_on(d2.winner)

        attr_1 = read_reasoning_chain_for_decision(d1.winner.decision_id)
        attr_2 = read_reasoning_chain_for_decision(d2.winner.decision_id)
        assert attr_1["candidate_id"] == d1.winner.candidate_id
        assert attr_2["candidate_id"] == d2.winner.candidate_id
        assert attr_1["candidate_id"] != attr_2["candidate_id"], (
            "even identical repeated real winners must mint fresh, "
            "non-colliding candidate_ids each cycle"
        )

    async def test_control_e_reward_provenance(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """The reward for the autonomously-selected winner must be the
        computed 5-factor expression applied to a REAL result -- never a
        literal. Source-level confirmation (shared with R13)."""
        act_src = inspect.getsource(AutonomousLoop._act_on)
        assert "reward = (" in act_src
        assert "uf * 0.40" in act_src
        assert "self._get_governor().dispatch(" in act_src

    async def test_control_f_no_bias_anywhere_in_flagship_evidence(self):
        """Formal proof this file itself never calls bias_toward() or
        manually sets a non-uniform confidence/urgency anywhere in its
        flagship, multi-cycle, or control evidence (TestSafety's RED
        control is explicitly the one exception, exactly like R13's)."""
        assert not _module_calls_bias_toward(), (
            "R14's flagship evidence must never actually CALL bias_toward() "
            "with arguments -- only reference it by name in prose"
        )
        # every native_candidates() call in this file must pass a single,
        # uniform confidence value shared by all candidates.
        import re
        import tests.test_r14_autonomous_learning_generalization as this_module
        src = inspect.getsource(this_module)
        confidences = re.findall(r"native_candidates\([^)]*confidence=([\d.]+)", src)
        assert confidences, "expected native_candidates() calls with an explicit uniform confidence"
        assert len(set(confidences)) == 1, (
            f"every native_candidates() call in this file must use the SAME "
            f"uniform confidence value -- found {set(confidences)}"
        )

    async def test_control_g_generation_stability(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """The candidate SET (3 real strategies) must be identical whether
        or not learning has occurred -- the only thing learning may change
        is ranking, never which strategies exist."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_control_g"
        gs_before = isolated_probe_goal_system(goal_id=goal_id)
        types_before = {c.action_type for c in native_candidates(gs_before, confidence=0.5)}
        gs_after = isolated_probe_goal_system(goal_id=goal_id)
        types_after = {c.action_type for c in native_candidates(gs_after, confidence=0.5)}
        assert types_before == types_after == {"git_status", "code_task", "read_code"}

    async def test_control_h_factor_stability(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """Confirm confidence/urgency/goal_alignment for the UNTOUCHED
        candidates remain identical across the learning boundary -- only
        the executed winner's policy_score may move."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_control_h"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d1 = await engine.evaluate(native_candidates(gs, confidence=0.5))
        winner_type = d1.winner.action_type
        untouched_types = {"git_status", "code_task", "read_code"} - {winner_type}
        before = {c.action_type: {f["factor"]: f["value"] for f in c.reasoning_chain}
                  for c in d1.all_candidates if c.action_type in untouched_types}

        await loop._act_on(d1.winner)

        from core.memory.episodic import close_db_connection
        close_db_connection()
        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        engine2 = build_isolated_engine(str(tmp_path / "epistemic2.db"))
        d2 = await engine2.evaluate(native_candidates(gs2, confidence=0.5))
        after = {c.action_type: {f["factor"]: f["value"] for f in c.reasoning_chain}
                 for c in d2.all_candidates if c.action_type in untouched_types}

        for t in untouched_types:
            assert before[t]["confidence"] == after[t]["confidence"]
            assert before[t]["urgency"] == after[t]["urgency"]
            assert before[t]["goal_alignment"] == after[t]["goal_alignment"]
            assert before[t]["policy_score"] == after[t]["policy_score"] == PolicyMemory.DEFAULT_SCORE, (
                f"{t} was never executed -- its policy_score must remain at default"
            )

    async def test_control_i_policy_only_change(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """The winner's total_score change across the learning boundary is
        attributable ENTIRELY to its policy_score factor -- every other
        factor for that same candidate identity is unchanged."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_control_i"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d1 = await engine.evaluate(native_candidates(gs, confidence=0.5))
        winner_type = d1.winner.action_type
        factors_1 = {f["factor"]: f["value"] for f in d1.winner.reasoning_chain}

        await loop._act_on(d1.winner)

        from core.memory.episodic import close_db_connection
        close_db_connection()
        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        engine2 = build_isolated_engine(str(tmp_path / "epistemic2.db"))
        d2 = await engine2.evaluate(native_candidates(gs2, confidence=0.5))
        winner_2 = next(c for c in d2.all_candidates if c.action_type == winner_type)
        factors_2 = {f["factor"]: f["value"] for f in winner_2.reasoning_chain}

        for factor in ("goal_alignment", "confidence", "urgency", "timing_score", "cost_penalty"):
            assert factors_1[factor] == factors_2[factor], f"{factor} must not change -- only policy_score may"
        assert factors_1["policy_score"] != factors_2["policy_score"]
        # RR-2: this scenario's real winner (git_status) has real
        # completed=0.0 (GitBot.get_status() carries no "status" key), so
        # its corrected reward (~0.42) is now BELOW default (0.5) rather
        # than above -- the old ">" direction assumed the pre-RR-2 fixed
        # goal_progress=0.5 default, which guaranteed any non-failing
        # dispatch's floor sat above default. This control's real claim --
        # ONLY policy_score changes, attributably, for the same candidate
        # identity -- is fully preserved by the "!=" above; the direction
        # is no longer asserted.


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9 — Autonomous multi-cycle test. The system chooses every winner;
# this test never specifies or steers which action should win.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestAutonomousMultiCycle:

    async def test_six_cycle_autonomous_experiment_no_steering(
        self, isolated_vector_db, isolated_agent_registry, tmp_path,
    ):
        """6 real, bias-free autonomous cycles using a SINGLE, PERSISTENT
        DecisionEngine (no restart between cycles) -- deliberately matching
        how the real autonomous_loop actually operates (one long-lived
        DecisionEngine across many think-ticks), unlike the flagship's own
        restart-focused design. The test does not choose, alternate, or
        influence which action wins -- it only observes and records.

        MAJOR EMPIRICAL FINDING (discovered by this test, not assumed):
        `core/loop/decision_engine.py::_select_staleness_aware_winner()`
        (R6, Task 91) is a REAL, EXISTING, already-shipped production
        mechanism, entirely separate from PolicyMemory learning: it tracks
        the current winner's IN-PROCESS consecutive-win streak
        (`self._winner_streak_hash`/`_winner_streak_count`, reset by any
        restart -- consistent with the flagship never encountering it) and,
        once a streak reaches `CONFIG["candidate_staleness_streak"]`
        (confirmed real default: 5), forces the NEXT-ranked candidate with
        a DIFFERENT identity to win instead -- using candidates already
        scored by the real 5-factor formula, inventing nothing.

        Empirically, with a persistent engine: cycles 1-5 all naturally
        pick `git_status` (reinforcing it exactly as the flagship found).
        Cycle 6 triggers R6: since `code_task` and `read_code` remain tied
        at the default policy score, and `code_task` is ranked first among
        them (real generation order: git_status, code_task, read_code),
        R6's real "next distinct candidate" becomes `code_task` -- which
        is RED. This is genuine, unsteered, real autonomous exploration
        (Phase 9/10) -- but it surfaces a RED candidate, which this test
        must NOT blindly auto-execute. Instead, this cycle becomes a real,
        in-line Phase 12 safety proof: the R6-selected RED candidate is
        run through the REAL `_act_on()` with only the gateway's owner-
        approval OUTCOME stubbed to a denial (identical, established
        pattern to R13/R11's own RED-boundary test) -- proving a genuinely
        autonomously-surfaced RED winner still cannot execute without
        approval."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_multicycle"
        # R23's capability factor scores an action_type no live agent declares at x0.85. The two-agent test registry
        # declares neither `code_task` nor anything else that covers it, so code_task (0.34) fell below read_code
        # (0.40) and R6 picked the GREEN read_code instead -- which skipped the RED-boundary proof this test exists
        # for. In production the manifest declares that capability on a coding agent (ManifestLoader injects
        # `capabilities` after construction), so do the same here on the real ArchitectBot; nothing is stubbed.
        architect = next(a for a in isolated_agent_registry.get_all_agents() if type(a).__name__ == "ArchitectBot")
        architect.capabilities = list(getattr(architect, "capabilities", []) or []) + ["code_task"]
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()
        gs = isolated_probe_goal_system(goal_id=goal_id)

        cycles = []
        decision_ids: set[str] = set()
        candidate_ids: set[str] = set()
        red_boundary_confirmed = False

        for cycle_num in range(1, 7):
            candidates = native_candidates(gs, confidence=0.5)  # NO bias, ever
            assert len({c.confidence for c in candidates}) == 1
            decision = await engine.evaluate(candidates)
            decision_ids.add(decision.winner.decision_id)
            candidate_ids.add(decision.winner.candidate_id)

            tier = PermissionGateway().classify(decision.winner.action_type)
            record = {
                "cycle": cycle_num,
                "decision_id": decision.winner.decision_id,
                "candidate_id": decision.winner.candidate_id,
                "winner": decision.winner.action_type,
                "tier": tier,
                "total_score": decision.winner.total_score,
            }

            if tier == "GREEN":
                # Real autonomous execution -- exactly R14's core claim.
                await loop._act_on(decision.winner)
                h = pm.make_situation_hash(decision.winner.action_type, {"goal_id": goal_id, "title": PROBE_GOAL_TITLE})
                record["reward"] = pm.get_score(decision.winner.action_type, h)
            else:
                # A genuinely, autonomously (R6-)surfaced non-GREEN winner.
                # This is the Phase 12 safety proof, in-line: confirm the
                # REAL _act_on() stops it at the authorization boundary,
                # never silently executing it, even though NOTHING about
                # this test chose or steered toward this candidate.
                from unittest.mock import AsyncMock, MagicMock
                fake_gateway = MagicMock()
                fake_gateway.classify = MagicMock(return_value=tier)
                denied_result = MagicMock()
                denied_result.approved = False
                denied_result.reason = "simulated owner non-approval (R14 multi-cycle -- no real approval requested)"
                fake_gateway.execute = AsyncMock(return_value=denied_result)
                original_gateway = loop._gateway
                loop._gateway = fake_gateway
                bridge_reached = {"value": False}
                try:
                    import districts.coding.vectorcode_bridge as vcb
                    original_get_bridge = vcb.get_bridge

                    class _BridgeGuard:
                        def is_available(self):
                            bridge_reached["value"] = True
                            return False

                    vcb.get_bridge = lambda: _BridgeGuard()
                    try:
                        await loop._act_on(decision.winner)
                    finally:
                        vcb.get_bridge = original_get_bridge
                finally:
                    loop._gateway = original_gateway

                fake_gateway.execute.assert_called_once()  # the real gate was genuinely reached
                assert bridge_reached["value"] is False, (
                    "an R6-surfaced RED winner, denied at the authorization "
                    "boundary, must NEVER reach the code-execution bridge"
                )
                record["reward"] = None
                record["red_boundary_stopped"] = True
                red_boundary_confirmed = True

            cycles.append(record)

        assert len(decision_ids) == 6, "every cycle must mint a fresh decision_id"
        assert len(candidate_ids) == 6, "every cycle must mint a fresh candidate_id"

        winners = [c["winner"] for c in cycles]
        distinct_winners = set(winners)

        # Honest reporting per Phase 10 -- no forced alternation, no
        # steering. Whatever the real engine chose is recorded as-is.
        assert distinct_winners == {"git_status", "code_task"}, (
            f"expected the real R6 staleness mechanism to naturally diversify "
            f"away from git_status after 5 consecutive real wins -- got "
            f"winners={winners}. If this repo's exact tie-break/config ever "
            f"changes, this assertion (not the underlying claim) needs "
            f"updating -- do not silently loosen it without re-verifying "
            f"the real cause."
        )
        green_cycles = [c for c in cycles if c["tier"] == "GREEN"]
        assert len(green_cycles) == 5 and all(c["winner"] == "git_status" for c in green_cycles)
        red_cycles = [c for c in cycles if c["tier"] != "GREEN"]
        assert len(red_cycles) == 1 and red_cycles[0]["winner"] == "code_task"
        assert red_boundary_confirmed, "the RED-boundary safety proof must have actually run"

        scores = [c["total_score"] for c in green_cycles]
        assert scores == sorted(scores), (
            "git_status's real total_score must trend non-decreasing across "
            "its reinforced cycles as real reward accumulates"
        )

        TestAutonomousMultiCycle.VERDICT = (
            "AUTONOMOUS LEARNING LOOP PROVEN; AUTONOMOUS EXPLORATION PROVEN "
            "(via the real, existing R6 staleness-diversity mechanism -- NOT "
            "via PolicyMemory learning itself, and NOT via random exploration "
            "added for this mission). The R6-surfaced alternative (cycle 6) "
            "was RED and was correctly stopped at the real authorization "
            "boundary, never autonomously executed."
        )
        TestAutonomousMultiCycle.CYCLES = cycles


# ═══════════════════════════════════════════════════════════════════════════
# Phase 11 — Reward quality audit.
# ═══════════════════════════════════════════════════════════════════════════

class TestRewardQualityAudit:

    def test_git_status_missing_status_key_does_not_block_r14_claim(self):
        """git_status's real result dict (GitBot.get_status()) never
        carries a 'status' key -- confirmed by source read. This makes
        `completed` a DEFAULTED (not genuinely observed as failing)
        component for git_status specifically, honestly classified here.
        It does NOT compromise R14's causal claim: the reward is still
        real (computed from a real dispatch, never hardcoded), still
        varies from DEFAULT_SCORE, and the autonomous-selection +
        real-learning-loop claim does not depend on git_status's
        completion signal being semantically perfect -- only on it being
        real and non-fabricated, which it is. Deferred, not fixed, per
        this mission's explicit 'do not automatically fix' instruction."""
        import inspect
        from districts.coding.git_bot import GitBot
        src = inspect.getsource(GitBot.get_status)
        assert '"status"' not in src and "'status'" not in src, (
            "confirms get_status()'s return dict has no status key -- a "
            "DEFAULTED, not genuinely-observed, completion signal for this "
            "one action type"
        )

    def test_goal_progress_defaults_for_both_real_action_types(self):
        """Neither GitBot.get_status() nor ArchitectBot.scan_codebase_
        with_graph() ever sets a 'goal_progress' key -- confirmed by
        source read. `_act_on()`'s `result.get("goal_progress", 0.5)`
        therefore uses the DEFAULT for both real action types this file
        exercises. Classified honestly as DEFAULTED, not genuinely
        observed, for this scenario -- 4 of 5 factors (uf, not_overridden,
        not_corrected, completed) still vary with the real result, which
        is sufficient for this file's causal claim (a genuine reward
        differential between git_status and read_code was already proven
        in R13 to arise purely from the `completed` factor)."""
        import inspect
        from districts.coding.git_bot import GitBot
        from districts.coding.architect_bot import ArchitectBot
        for src in (inspect.getsource(GitBot.get_status), inspect.getsource(ArchitectBot.run)):
            assert "goal_progress" not in src

    def test_reward_floor_no_longer_guarantees_reinforcement(self):
        """RR-2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        RR2_MEANINGFUL_UTILITY_REPORT.md) update: this test used to prove
        the OPPOSITE of what it now asserts -- that for ANY action whose
        real dispatch does not hit an outright failure, the 5-factor
        formula's floor (uf(0.3)*.40 + goal_progress(0.5, the OLD fabricated
        default)*.25 + not_overridden(1)*.15 + not_corrected(1)*.15 +
        completed(0)*.05 = 0.42) sat ALWAYS above PolicyMemory.DEFAULT_SCORE
        (0.5) -- a genuine architectural property that guaranteed even a
        technically-executed-but-zero-evidence action could only ever
        reinforce itself, never fall below neutral. That property is
        EXACTLY RG-D's own root cause (RR-0 traced it precisely to this
        fabricated 0.5 default) and is now deliberately, correctly removed:
        with goal_progress UNKNOWN contributing 0 (not 0.5) when no real
        evidence exists, the SAME floor is uf(0.3)*.40 + 0*.25 + 1.0*.15 +
        1.0*.15 + 0*.05 = 0.42 -- now genuinely BELOW DEFAULT_SCORE. R14's
        own causal claim (autonomous SELECTION and LEARNING FROM
        CONSEQUENCES) is unaffected by this -- it was never about
        EXPLORATION (Phase 10, explicitly out of scope then and now) -- but
        the specific "guaranteed self-reinforcement" property this test
        documented is gone, which is the intended, verified RR-2 outcome."""
        floor = 0.3 * 0.40 + 0.0 * 0.25 + 1.0 * 0.15 + 1.0 * 0.15 + 0.0 * 0.05
        assert floor == pytest.approx(0.42, abs=0.001)
        assert floor < PolicyMemory.DEFAULT_SCORE, (
            "RR-2 must remove the old guaranteed-reinforcement floor -- a "
            "technically-executed, zero-evidence action's reward should no "
            "longer sit above neutral by construction"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 12 — Safety: learning must never bypass GREEN/YELLOW/RED/FORBIDDEN,
# even for an autonomously (not experimenter) selected winner.
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestSafety:

    async def test_learned_preference_cannot_autoexecute_red(self, isolated_vector_db):
        """Even if code_task's learned score were driven to 1.0 (via the
        real update_from_outcome() API -- the one explicit, labeled
        non-flagship control this file permits, identical in spirit to
        R13's own equivalent), its permission tier remains RED and
        _act_on()'s VC-bridge gate still requires real gateway approval."""
        pm = PolicyMemory()
        h = pm.make_situation_hash("code_task", {"goal_id": "g_r14_safety", "title": PROBE_GOAL_TITLE})
        for _ in range(10):
            pm.update_from_outcome("code_task", h, 1.0)
        assert pm.get_score("code_task", h) == pytest.approx(1.0, abs=0.01)
        assert PermissionGateway().classify("code_task") == "RED"

        src = inspect.getsource(AutonomousLoop._act_on)
        assert '_level in ("RED", "YELLOW")' in src
        assert "if not _gw_result.approved:" in src

    async def test_autonomous_selection_never_bypasses_governor(self):
        """generate_immediate_actions() and evaluate() never call
        PermissionGateway/Governor directly -- authorization happens only
        at _act_on() time, and only after the engine's own (possibly
        learned) selection, never influencing whether the gate itself
        fires."""
        gen_src = inspect.getsource(GoalSystem.generate_immediate_actions)
        assert "PermissionGateway" not in gen_src and "Governor" not in gen_src


# ═══════════════════════════════════════════════════════════════════════════
# Phase 13 — Adversarial review (18 points)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestAdversarialReview:

    async def test_attack_1_experimenter_bias(self):
        """Already the subject of Control F -- re-confirmed narrowly: this
        entire module contains zero bias_toward() calls."""
        assert not _module_calls_bias_toward()

    async def test_attack_2_candidate_ordering(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """Candidates are generated in the real, unmodified tag-processing
        order every time -- the test never reorders the list before
        calling evaluate()."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack2"
        gs = isolated_probe_goal_system(goal_id=goal_id)
        c = native_candidates(gs, confidence=0.5)
        assert [x.action_type for x in c] == ["git_status", "code_task", "read_code"], (
            "native order must be exactly generate_immediate_actions()'s own "
            "real output order, never permuted by the test"
        )

    async def test_attack_3_confidence_leakage(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack3"
        gs = isolated_probe_goal_system(goal_id=goal_id)
        c1 = native_candidates(gs, confidence=0.5)
        c2 = native_candidates(gs, confidence=0.5)
        assert {x.confidence for x in c1} == {x.confidence for x in c2} == {0.5}

    async def test_attack_4_urgency_leakage(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack4"
        gs = isolated_probe_goal_system(goal_id=goal_id)
        c = native_candidates(gs, confidence=0.5)
        assert {x.urgency for x in c} == {0.5}

    async def test_attack_5_stale_policymemory(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack5"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d = await engine.evaluate(native_candidates(gs, confidence=0.5))
        await loop._act_on(d.winner)
        h = pm.make_situation_hash(d.winner.action_type, {"goal_id": goal_id, "title": PROBE_GOAL_TITLE})
        from core.memory.episodic import close_db_connection
        close_db_connection()
        # RR-2: the deterministic winner in this scenario (git_status) now
        # scores below DEFAULT_SCORE (real completed=0.0, no fabricated
        # goal_progress credit) -- "!=" preserves this test's real intent
        # (a real outcome moved the score away from default) without
        # assuming the pre-RR-2 direction.
        assert pm.get_score(d.winner.action_type, h) != PolicyMemory.DEFAULT_SCORE

    async def test_attack_6_wrong_db(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        import os
        assert os.environ.get("VECTOR_DB_PATH") == isolated_vector_db
        assert isolated_vector_db != "vector_memory.db"

    async def test_attack_7_hash_mismatch(self):
        act_src = inspect.getsource(AutonomousLoop._act_on)
        assert "pm.make_situation_hash(winner.action_type, winner.params)" in act_src

    async def test_attack_8_candidate_regeneration_changes(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack8"
        gs1 = isolated_probe_goal_system(goal_id=goal_id)
        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        assert {c.action_type for c in native_candidates(gs1)} == {c.action_type for c in native_candidates(gs2)}

    async def test_attack_9_factor_changes(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """Already covered by Control H/I -- re-confirmed: untouched
        candidates' factors never move."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack9"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d1 = await engine.evaluate(native_candidates(gs, confidence=0.5))
        untouched_before = {
            c.action_type: c.confidence for c in d1.all_candidates if c.action_type != d1.winner.action_type
        }
        await loop._act_on(d1.winner)
        from core.memory.episodic import close_db_connection
        close_db_connection()
        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        engine2 = build_isolated_engine(str(tmp_path / "epistemic2.db"))
        d2 = await engine2.evaluate(native_candidates(gs2, confidence=0.5))
        untouched_after = {
            c.action_type: c.confidence for c in d2.all_candidates if c.action_type != d1.winner.action_type
        }
        assert untouched_before == untouched_after

    async def test_attack_10_reward_hardcoding(self):
        src = inspect.getsource(AutonomousLoop._act_on)
        assert "reward = (" in src

    async def test_attack_11_manual_reward_injection(self):
        """Exactly 1 direct update_from_outcome() call exists in this
        entire file (TestSafety's RED-bypass control) -- confirmed by
        source count excluding this assertion's own literal."""
        import tests.test_r14_autonomous_learning_generalization as this_module
        src = inspect.getsource(this_module)
        direct_calls = src.count("pm.update_from_outcome(") - 1  # -1 for this line's own literal
        assert direct_calls == 1

    async def test_attack_12_manual_winner_selection(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """No test in this file ever passes a hand-constructed Candidate
        to _act_on() -- every _act_on() call operates on a real
        Decision.winner object."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack12"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_probe_goal_system(goal_id=goal_id)
        candidates = native_candidates(gs, confidence=0.5)
        decision = await engine.evaluate(candidates)
        assert any(decision.winner is c for c in candidates), (
            "the winner passed to _act_on() must be one of the objects "
            "DecisionEngine.evaluate() itself scored, never a fresh, "
            "hand-built stand-in"
        )
        await loop._act_on(decision.winner)

    async def test_attack_13_hidden_test_only_branches(self):
        act_src = inspect.getsource(AutonomousLoop._act_on)
        gen_src = inspect.getsource(GoalSystem.generate_immediate_actions)
        for src in (act_src, gen_src):
            assert "PYTEST" not in src.upper()

    async def test_attack_14_staleness_logic(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """The winner's own policy_score factor, read directly, matches
        the real learned value -- ruling out an unrelated staleness
        penalty as the actual explanation for its score change."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack14"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d1 = await engine.evaluate(native_candidates(gs, confidence=0.5))
        await loop._act_on(d1.winner)
        h = pm.make_situation_hash(d1.winner.action_type, {"goal_id": goal_id, "title": PROBE_GOAL_TITLE})
        real_score = pm.get_score(d1.winner.action_type, h)

        from core.memory.episodic import close_db_connection
        close_db_connection()
        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        engine2 = build_isolated_engine(str(tmp_path / "epistemic2.db"))
        d2 = await engine2.evaluate(native_candidates(gs2, confidence=0.5))
        winner_2 = next(c for c in d2.all_candidates if c.action_type == d1.winner.action_type)
        assert winner_2.policy_score == pytest.approx(real_score, abs=0.01)

    async def test_attack_15_wrong_candidate_attribution(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """Already covered by Control D -- re-confirmed narrowly here."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack15"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d = await engine.evaluate(native_candidates(gs, confidence=0.5))
        await loop._act_on(d.winner)
        attribution = read_reasoning_chain_for_decision(d.winner.decision_id)
        assert attribution["candidate_id"] == d.winner.candidate_id

    async def test_attack_16_cross_goal_contamination(self):
        pm = PolicyMemory()
        h1 = pm.make_situation_hash("git_status", {"goal_id": "g_x", "title": "t"})
        h2 = pm.make_situation_hash("git_status", {"goal_id": "g_y", "title": "t"})
        assert h1 != h2

    async def test_attack_17_cached_decisionengine_state(self, isolated_vector_db, isolated_agent_registry, tmp_path):
        """A wholly separate DecisionEngine object (never touched by the
        writer) must still read the real persisted score correctly."""
        goal_id = f"{R14_GOAL_ID_PREFIX}_attack17"
        engine = build_isolated_engine(str(tmp_path / "epistemic.db"))
        loop = build_isolated_loop(engine)
        pm = PolicyMemory()
        gs = isolated_probe_goal_system(goal_id=goal_id)
        d1 = await engine.evaluate(native_candidates(gs, confidence=0.5))
        await loop._act_on(d1.winner)
        h = pm.make_situation_hash(d1.winner.action_type, {"goal_id": goal_id, "title": PROBE_GOAL_TITLE})
        real_score = pm.get_score(d1.winner.action_type, h)

        fresh_engine = build_isolated_engine(str(tmp_path / "epistemic_fresh.db"))
        gs2 = isolated_probe_goal_system(goal_id=goal_id)
        d2 = await fresh_engine.evaluate(native_candidates(gs2, confidence=0.5))
        winner_2 = next(c for c in d2.all_candidates if c.action_type == d1.winner.action_type)
        assert winner_2.policy_score == pytest.approx(real_score, abs=0.01)

    async def test_attack_18_safety_bypass(self):
        gw = PermissionGateway()
        assert gw.classify("code_task") == "RED"
        assert gw.classify("git_status") == "GREEN"
        assert gw.classify("read_code") == "GREEN"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
