"""
E1 — Persistent Learning Verification.

Question: can VECTOR demonstrate experience -> persistent update -> retrieval
-> changed future decision, using REAL existing DecisionEngine + PolicyMemory
+ persistence -- no architecture modification, no hidden state, no injected
candidates beyond what a real DecisionEngine.evaluate() call already accepts?

Experiment (exactly as specified):
    1. baseline decision (A wins on raw confidence/urgency alone)
    2. real outcome for A, repeatedly bad
    3. legitimate PolicyMemory.update_from_outcome() calls (the same real
       RULE-7 write path autonomous_loop._act_on() uses)
    4. close persistence (real SQLite connection close)
    5. reopen (fresh DecisionEngine + PolicyMemory instances, same db file --
       simulating a process restart)
    6. same decision (identical candidates, freshly constructed)
    7. determine whether the winner changed
    8. prove the update caused it (controls below)

Controls: an unrelated action_type/situation is unaffected; a duplicate
identical update doesn't do anything qualitatively different from a single
update at the same total sample count; a legitimately OLD update (recorded
before the "restart") still counts correctly in the average after reopening.

This uses PolicyMemory's REAL production write/read API
(update_from_outcome / get_score / make_situation_hash) -- no architecture
change, no candidate injected into production, no scorer altered for the
experiment, no hardcoded expected winner (the winner is only known by
running the real 5-factor formula).

Per .claude/rules/testing.md, this is a real SQLite round-trip (PolicyMemory
has no db_path override -- it always uses the shared real episodic-memory
connection).

M1e (2026-09-09): isolation now uses the `isolated_vector_db` fixture
(tests/conftest.py) instead of a module-level `os.environ["VECTOR_DB_PATH"]`
assignment. The old pattern ran at pytest COLLECTION time and leaked into
every test that ran afterward in the same process for the rest of the
session -- root-caused in
VECTOR_TECHNICAL_KNOWLEDGE/M1E_DEVELOPMENT_FOUNDATION_REPORT.md. This file
can now safely run as part of a combined suite -- it no longer requires
standalone execution.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock

import pytest

from core.loop.decision_engine import Candidate, DecisionEngine
from core.memory.policy import PolicyMemory


def make_candidate(action_type, confidence=0.6, urgency=0.5, params=None):
    return Candidate(action_type=action_type, params=params or {}, confidence=confidence, urgency=urgency)


def _isolated_engine() -> DecisionEngine:
    """Real DecisionEngine + REAL PolicyMemory (the one thing under test).
    Every other subsystem stubbed so only the policy signal can move the
    ranking -- no hidden state, nothing this test doesn't control."""
    e = DecisionEngine()
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_epistemic = MagicMock()
    e._get_epistemic().get_belief.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    e._get_metacognition = MagicMock(return_value=None)
    e._get_correction_learner = MagicMock(return_value=None)
    # _get_policy is intentionally NOT stubbed -- real PolicyMemory, real db.
    return e


@pytest.mark.asyncio
async def test_e1_experience_causes_persistent_behavior_change_across_restart(isolated_vector_db):
    action_a = "e1_action_a"
    action_b = "e1_action_b"
    params = {}

    # ---- 1. Baseline decision ------------------------------------------------
    e1 = _isolated_engine()
    baseline = await e1.evaluate([
        make_candidate(action_a, confidence=0.62, urgency=0.5, params=params),
        make_candidate(action_b, confidence=0.60, urgency=0.5, params=params),
    ])
    assert baseline.winner.action_type == action_a, (
        "sanity check: with no policy history, the higher-confidence candidate must win"
    )

    # ---- 2 & 3. Real outcome + legitimate PolicyMemory update ----------------
    # Repeatedly record a genuinely BAD real outcome for A -- the same write
    # path autonomous_loop._act_on() uses after every real action.
    pm = e1._get_policy()
    h_a = pm.make_situation_hash(action_a, params)
    for _ in range(8):
        pm.update_from_outcome(action_a, h_a, 0.05)  # consistently poor real outcome

    score_after_bad_outcomes = pm.get_score(action_a, h_a)
    assert score_after_bad_outcomes < PolicyMemory.DEFAULT_SCORE, (
        "the real reward signal must have genuinely lowered A's learned policy score"
    )

    # ---- 4. Close persistence -------------------------------------------------
    from core.memory.episodic import close_db_connection
    close_db_connection()

    # ---- 5. Reopen (fresh instances, same db file = simulated restart) -------
    e2 = _isolated_engine()

    # ---- 6 & 7. Same decision, determine whether the winner changed ----------
    after_restart = await e2.evaluate([
        make_candidate(action_a, confidence=0.62, urgency=0.5, params=params),
        make_candidate(action_b, confidence=0.60, urgency=0.5, params=params),
    ])

    # ---- 8. Prove the update caused it -----------------------------------
    assert after_restart.winner.action_type == action_b, (
        "persistent learning must survive a real restart and change the winner: "
        f"got {after_restart.winner.action_type}, expected {action_b}"
    )
    a_candidate = next(c for c in after_restart.all_candidates if c.action_type == action_a)
    assert a_candidate.policy_score == pytest.approx(score_after_bad_outcomes, abs=0.01), (
        "A's policy_score after restart must match what was persisted before closing -- "
        "not reset, not recomputed from scratch"
    )


@pytest.mark.asyncio
async def test_e1_control_unrelated_situation_unaffected(isolated_vector_db):
    """Control: the bad-outcome learning for e1_action_a/params={} must not
    leak into an unrelated action_type or unrelated params."""
    e = _isolated_engine()
    pm = e._get_policy()
    h = pm.make_situation_hash("e1_control_action_unique", {})
    baseline_score = pm.get_score("e1_control_action_unique", h)
    assert baseline_score == PolicyMemory.DEFAULT_SCORE

    d = await e.evaluate([
        make_candidate("e1_control_action_unique", confidence=0.6),
        make_candidate("e1_control_other", confidence=0.5),
    ])
    assert d.winner.action_type == "e1_control_action_unique"  # untouched by the OTHER test's learning


@pytest.mark.asyncio
async def test_e1_control_duplicate_update_averages_not_amplifies(isolated_vector_db):
    """Control: repeating the SAME reward value N times converges to that
    value (a real online average), it does not runaway/amplify beyond the
    real reward's own magnitude."""
    e = _isolated_engine()
    pm = e._get_policy()
    action_type = "e1_dup_control_action"
    h = pm.make_situation_hash(action_type, {})
    for _ in range(20):
        pm.update_from_outcome(action_type, h, 0.3)
    score = pm.get_score(action_type, h)
    assert score == pytest.approx(0.3, abs=0.01), (
        f"repeated identical updates must converge to the real value (0.3), got {score} -- "
        "not amplify past it"
    )


@pytest.mark.asyncio
async def test_e1_control_old_update_still_counts_correctly_after_restart(isolated_vector_db):
    """Control: an update recorded BEFORE the simulated restart is not lost
    or double-counted -- the average across the full real history remains
    mathematically correct after reopening."""
    action_type = "e1_old_update_action"
    e1 = _isolated_engine()
    pm1 = e1._get_policy()
    h = pm1.make_situation_hash(action_type, {})
    pm1.update_from_outcome(action_type, h, 0.8)  # "old" -- before restart
    pm1.update_from_outcome(action_type, h, 0.8)

    from core.memory.episodic import close_db_connection
    close_db_connection()

    e2 = _isolated_engine()
    pm2 = e2._get_policy()
    pm2.update_from_outcome(action_type, h, 0.8)  # "new" -- after restart

    final_score = pm2.get_score(action_type, h)
    assert final_score == pytest.approx(0.8, abs=0.01), (
        "three real updates of the same value, split across a restart, must "
        f"still average to 0.8 -- got {final_score} (old update lost or double-counted)"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
