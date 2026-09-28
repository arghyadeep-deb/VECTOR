"""Integration tests — EpistemicTracker full cognitive loop.

Tests the complete belief → confidence → staleness → decision → action flow
with a REAL EpistemicTracker (SQLite-backed, not mocked).

Flow tested:
1. Fresh domain → no penalty → action executes → belief recorded
2. Repeated success → confidence rises → no penalty
3. Repeated failure → confidence drops → dampening kicks in
4. Aged belief → stale → heavy dampening
5. decay_epistemic() ages beliefs correctly
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

from core.loop.decision_engine import Candidate, DecisionEngine


def _make_candidate(action_type="search_web", confidence=0.5, urgency=0.5):
    return Candidate(
        action_type=action_type,
        params={},
        goal_ids=[],
        confidence=confidence,
        urgency=urgency,
        timing_score=1.0,
        estimated_cost_inr=0.0,
    )


def _make_engine_with_real_epistemic(db_path: str) -> DecisionEngine:
    """DecisionEngine with a real EpistemicTracker + mocked other deps."""
    from core.brain.epistemic_tracker import EpistemicTracker

    engine = DecisionEngine()
    engine._epistemic = EpistemicTracker(db_path=db_path)
    engine._get_epistemic = lambda: engine._epistemic
    engine._get_policy = MagicMock()
    engine._get_policy().get_score.return_value = 0.5
    engine._get_goals = MagicMock()
    engine._get_goals().get_active_goals.return_value = []
    engine._get_memory = MagicMock()
    engine._get_memory().store.return_value = None
    engine._get_reasoning_bank = MagicMock(return_value=None)
    engine._get_neural_trainer = MagicMock(return_value=None)
    engine._get_context_engine = MagicMock()
    engine._get_context_engine().get_world_state.return_value = {}
    return engine


class TestEpistemicCognitiveLoop(unittest.TestCase):
    """Full belief → confidence → decision → action → belief update loop."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)
        self.engine = _make_engine_with_real_epistemic(self._db)

    def tearDown(self):
        self.engine._epistemic.close()
        Path(self._db).unlink(missing_ok=True)

    def test_fresh_domain_no_penalty(self):
        """First action in a domain → no epistemic penalty."""
        c = _make_candidate("newaction_test")
        # This test is about the epistemic factor alone. The later post-score multipliers (situational,
        # capability, workload, causal, simulation) read live agent/plan/causal state -- e.g. an action no
        # live agent declares gets the capability factor 0.85 -- so pin them neutral to keep it deterministic.
        for factor in ("_situational_factor", "_capability_factor", "_workload_factor",
                       "_causal_factor", "_simulation_factor"):
            setattr(self.engine, factor, lambda cand, _f=factor: (1.0, "neutral"))
        self.engine._score_candidate(c)

        # Score should be the 5-factor result with no epistemic dampening
        # (all neutral inputs: goal=0.3, conf=0.5, policy=0.5, urg=0.5, timing=1.0)
        # total = 0.30*0.3 + 0.25*0.5 + 0.20*0.5 + 0.15*0.5 + 0.10*1.0 - 0.05*0
        # = 0.09 + 0.125 + 0.10 + 0.075 + 0.10 = 0.49
        self.assertAlmostEqual(c.total_score, 0.49, places=2)

        # No epistemic entry in reasoning chain
        epistemic_entries = [
            e for e in c.reasoning_chain
            if e.get("factor") == "epistemic_confidence"
        ]
        self.assertEqual(len(epistemic_entries), 0)

    def test_successful_action_builds_confidence(self):
        """After recording high reward, epistemic confidence rises."""
        # Record a high-reward outcome
        self.engine.record_epistemic_belief("search_web", "ok", 0.9)

        # Now score a candidate in the same domain
        c = _make_candidate("search_web")
        factor, conf = self.engine._epistemic_penalty(c)

        # Confidence should be ≥ 0.5 (high reward → high confidence)
        self.assertGreaterEqual(conf, 0.5)
        # Factor should be 1.0 (high confidence → no penalty)
        self.assertEqual(factor, 1.0)

    def test_failed_action_reduces_confidence(self):
        """After recording low reward, epistemic confidence is low."""
        # Record a low-reward outcome
        self.engine.record_epistemic_belief("search_web", "failed", 0.1)

        # Now score a candidate in the same domain
        c = _make_candidate("search_web")
        factor, conf = self.engine._epistemic_penalty(c)

        # Confidence should be low
        self.assertLess(conf, 0.3)
        # Factor should be 0.80 (low confidence → dampening)
        self.assertEqual(factor, 0.80)

    def test_repeated_failure_triggers_dampening_in_scoring(self):
        """Multiple failures → low confidence → score is dampened."""
        # Record several low-reward outcomes
        for _ in range(5):
            self.engine.record_epistemic_belief("risky_action", "failed", 0.1)

        # Score two candidates: one in the failed domain, one neutral
        c_failed = _make_candidate("risky_action", confidence=0.7, urgency=0.5)
        c_neutral = _make_candidate("neutral_action", confidence=0.7, urgency=0.5)

        self.engine._score_candidate(c_failed)
        self.engine._score_candidate(c_neutral)

        # The failed-domain candidate should score lower
        self.assertLess(c_failed.total_score, c_neutral.total_score,
                        "Repeated failures should dampen future scores")

    def test_stale_belief_triggers_heavy_dampening(self):
        """Belief past TTL → stale → 0.70 factor.

        R16 (2026-09-10): the candidate's action_type must exactly match
        the belief key's domain now that domain is the full action_type
        (previously "oldaction_test" incidentally matched "oldaction" via
        the removed action_type.split("_")[0] grouping -- see
        decision_engine.py's _epistemic_penalty() docstring).
        """
        # Create a belief and backdate it past TTL
        self.engine._epistemic.update_belief(
            "action_domain:oldaction", "old outcome", 0.9, "test", ttl_hours=1
        )
        # Backdate to 2 hours ago (past 1h TTL)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.engine._epistemic._conn.execute(
            "UPDATE claims SET last_seen_at=?, created_at=? WHERE id=?",
            (old_ts, old_ts, "action_domain:oldaction"),
        )
        self.engine._epistemic._conn.commit()
        self.engine._epistemic._beliefs["action_domain:oldaction"]["created_at"] = old_ts

        c = _make_candidate("oldaction")
        factor, conf = self.engine._epistemic_penalty(c)

        self.assertEqual(factor, 0.70)
        self.assertEqual(conf, 0.0)

    def test_decay_ages_beliefs(self):
        """decay_epistemic() reduces confidence on aged beliefs."""
        # Create a belief and backdate it
        self.engine._epistemic.update_belief(
            "action_domain:decay_test", "outcome", 0.9, "test"
        )
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
        self.engine._epistemic._conn.execute(
            "UPDATE claims SET last_seen_at=?, created_at=? WHERE id=?",
            (old_ts, old_ts, "action_domain:decay_test"),
        )
        self.engine._epistemic._conn.commit()
        self.engine._epistemic._beliefs["action_domain:decay_test"]["created_at"] = old_ts

        before = self.engine._epistemic.get_confidence("action_domain:decay_test")
        count = self.engine.decay_epistemic()
        after = self.engine._epistemic.get_confidence("action_domain:decay_test")

        self.assertGreaterEqual(count, 0)
        self.assertLessEqual(after, before)

    def test_full_loop_score_act_record_score(self):
        """Complete cognitive loop: score → simulate act → record → score again."""
        # Step 1: Score candidate in fresh domain
        c1 = _make_candidate("loop_test", confidence=0.7, urgency=0.5)
        self.engine._score_candidate(c1)
        score_before = c1.total_score

        # Step 2: Simulate action with low reward (failure)
        self.engine.record_epistemic_belief("loop_test", "failed", 0.15)

        # Step 3: Score again — should be dampened
        c2 = _make_candidate("loop_test", confidence=0.7, urgency=0.5)
        self.engine._score_candidate(c2)
        score_after = c2.total_score

        self.assertLess(score_after, score_before,
                        f"Score should drop after failure: {score_before} → {score_after}")

        # Step 4: Now simulate high reward (success) to recover
        for _ in range(5):
            self.engine.record_epistemic_belief("loop_test", "ok", 0.95)

        c3 = _make_candidate("loop_test", confidence=0.7, urgency=0.5)
        self.engine._score_candidate(c3)
        score_recovered = c3.total_score

        # Score should recover (high confidence → no penalty)
        self.assertGreaterEqual(score_recovered, score_after,
                                "Score should recover after repeated success")

    def test_different_domains_independent(self):
        """Beliefs in one domain don't affect another.

        R16 (2026-09-10): domain is now the exact, full action_type (see
        decision_engine.py's _epistemic_penalty()/record_epistemic_belief()
        docstrings) rather than action_type.split("_")[0] -- the original
        fixture names here ("domain_a"/"domain_a_action",
        "domain_b"/"domain_b_action") were written under the OLD, buggy
        first-token-split scheme, where both pairs collapsed to the SAME
        domain ("domain") purely by coincidence of sharing a first word --
        this test was accidentally not testing what its own name claims
        (it never actually recorded a belief under the same exact
        action_type it queried). Fixed to record and query the SAME exact
        action_type per domain, matching how every other test in this file
        already does it (see test_successful_action_builds_confidence,
        test_failed_action_reduces_confidence, etc.).
        """
        self.engine.record_epistemic_belief("domain_a_action", "failed", 0.1)
        self.engine.record_epistemic_belief("domain_b_action", "ok", 0.9)

        c_a = _make_candidate("domain_a_action")
        c_b = _make_candidate("domain_b_action")

        factor_a, _ = self.engine._epistemic_penalty(c_a)
        factor_b, _ = self.engine._epistemic_penalty(c_b)

        # domain_a should be penalised, domain_b should not
        self.assertLess(factor_a, 1.0)
        self.assertEqual(factor_b, 1.0)


class TestEpistemicPersistence(unittest.TestCase):
    """Beliefs survive engine restart (simulating VECTOR restart)."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)

    def tearDown(self):
        Path(self._db).unlink(missing_ok=True)

    def test_beliefs_survive_restart(self):
        """Record belief → close engine → reopen → belief still affects scoring."""
        # Phase 1: record beliefs
        engine1 = _make_engine_with_real_epistemic(self._db)
        engine1.record_epistemic_belief("persist_action", "ok", 0.9)
        engine1._epistemic.close()

        # Phase 2: reopen and verify
        engine2 = _make_engine_with_real_epistemic(self._db)
        c = _make_candidate("persist_action")
        factor, conf = engine2._epistemic_penalty(c)

        self.assertEqual(factor, 1.0)
        self.assertGreater(conf, 0.5)
        engine2._epistemic.close()


class TestEpistemicEvaluateEndToEnd(unittest.TestCase):
    """Test that evaluate() produces correct winner with epistemic dampening."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db = self._tmp.name
        self._tmp.close()
        Path(self._db).unlink(missing_ok=True)
        self.engine = _make_engine_with_real_epistemic(self._db)

    def tearDown(self):
        self.engine._epistemic.close()
        Path(self._db).unlink(missing_ok=True)

    def test_well_known_domain_wins_over_stale(self):
        """Identical candidates — well-known domain wins over stale one."""
        # Build up confidence in domain "known"
        for _ in range(3):
            self.engine.record_epistemic_belief("known_action", "ok", 0.9)

        # Create stale belief for domain "stale"
        self.engine._epistemic.update_belief(
            "action_domain:stale", "old outcome", 0.9, "test", ttl_hours=1
        )
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        self.engine._epistemic._conn.execute(
            "UPDATE claims SET last_seen_at=?, created_at=? WHERE id=?",
            (old_ts, old_ts, "action_domain:stale"),
        )
        self.engine._epistemic._conn.commit()
        self.engine._epistemic._beliefs["action_domain:stale"]["created_at"] = old_ts

        c_known = _make_candidate("known_action", confidence=0.6, urgency=0.5)
        c_stale = _make_candidate("stale_action", confidence=0.6, urgency=0.5)

        decision = asyncio.run(self.engine.evaluate([c_known, c_stale]))
        self.assertEqual(decision.winner.action_type, "known_action")


if __name__ == "__main__":
    unittest.main()
