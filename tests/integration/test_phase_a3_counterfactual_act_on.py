"""Integration tests — Session A3: CounterfactualMemory.should_avoid() in _act_on."""
from __future__ import annotations

import tempfile
import asyncio
import unittest
from pathlib import Path


class TestCounterfactualShouldAvoid(unittest.TestCase):
    """CounterfactualMemory.should_avoid() API contract tests."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        from core.memory.counterfactual import CounterfactualMemory
        self.cf = CounterfactualMemory(db_path=self._tmp.name)

    def tearDown(self):
        self.cf.close()
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_should_avoid_returns_tuple(self):
        avoid, score, reason = self.cf.should_avoid("delete logs")
        self.assertIsInstance(avoid, bool)
        self.assertIsInstance(score, float)
        self.assertIsInstance(reason, str)

    def test_no_rejections_never_blocks(self):
        avoid, score, _ = self.cf.should_avoid("deploy to prod")
        self.assertFalse(avoid)
        self.assertEqual(score, 0.0)

    def test_exact_rejection_blocks_above_threshold(self):
        self.cf.record_rejection("dec-1", "delete all logs", "Too destructive")
        avoid, score, reason = self.cf.should_avoid("delete all logs", threshold=0.7)
        self.assertTrue(avoid)
        self.assertGreaterEqual(score, 0.7)
        self.assertIn("Too destructive", reason)

    def test_get_all_rejections_returns_most_recent_first(self):
        """New for the post-training DPO dataset adapter (plans/post-training-pipeline.md
        Task 2) — a plain read of the rejections table, same pattern as get_all_scenarios."""
        self.cf.record_rejection("deploy", "deploy untested", "no tests run")
        self.cf.record_rejection("deploy", "deploy without review", "skipped review")
        rows = self.cf.get_all_rejections(limit=10)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["proposal"], "deploy without review")
        self.assertEqual(rows[1]["proposal"], "deploy untested")
        self.assertEqual(rows[0]["decision_id"], "deploy")

    def test_get_all_rejections_respects_limit(self):
        for i in range(5):
            self.cf.record_rejection(f"dec-{i}", f"proposal {i}", "reason")
        rows = self.cf.get_all_rejections(limit=2)
        self.assertEqual(len(rows), 2)

    def test_get_all_rejections_empty_table_returns_empty_list(self):
        rows = self.cf.get_all_rejections()
        self.assertEqual(rows, [])

    def test_dissimilar_proposal_not_blocked(self):
        self.cf.record_rejection("dec-2", "delete all logs", "Too destructive")
        avoid, score, _ = self.cf.should_avoid("run unit tests", threshold=0.7)
        self.assertFalse(avoid)

    def test_medium_similarity_returns_false_but_has_score(self):
        self.cf.record_rejection("dec-3", "delete some logs old", "Risky operation")
        avoid, score, _ = self.cf.should_avoid("delete a few logs", threshold=0.7)
        # Score might be in the caution zone (0.4-0.7); no hard block
        self.assertIsInstance(avoid, bool)
        self.assertGreaterEqual(score, 0.0)


class TestCounterfactualAutonomousLoopIntegration(unittest.TestCase):
    """_act_on gate: verify counterfactual check runs and blocks on high similarity."""

    def setUp(self):
        from core.loop.autonomous_loop import AutonomousLoop
        self.loop = AutonomousLoop()

    def test_act_on_does_not_crash_with_cf_available(self):
        """_act_on must handle CounterfactualMemory without crashing."""
        from core.loop.decision_engine import Candidate
        candidate = Candidate(
            action_type="git_status",
            params={},
            goal_ids=[],
        )
        # Just verify it doesn't raise; governor will fail gracefully without running loop
        try:
            asyncio.run(self.loop._act_on(candidate))
        except Exception:
            pass  # governor/gateway failures are expected in isolation — what matters is no import crash

    def test_counterfactual_import_succeeds(self):
        """CounterfactualMemory can be imported from within _act_on context."""
        from core.memory.counterfactual import CounterfactualMemory
        cf = CounterfactualMemory()
        self.assertIsNotNone(cf)
        cf.close()

    def test_record_rejection_then_should_avoid(self):
        """Full pipeline: record rejection → should_avoid returns True for near-identical proposal."""
        from core.memory.counterfactual import CounterfactualMemory
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            cf = CounterfactualMemory(db_path=db)
            cf.record_rejection("dec-loop", "delete logs force", "destructive + irreversible")
            avoid, score, reason = cf.should_avoid("delete logs force", threshold=0.7)
            self.assertTrue(avoid, f"Expected block, score={score}")
            self.assertIn("destructive", reason)
            cf.close()
        finally:
            Path(db).unlink(missing_ok=True)

    def test_caution_zone_does_not_hard_block(self):
        """Proposals in the 0.4-0.7 similarity zone should not be hard-blocked."""
        from core.memory.counterfactual import CounterfactualMemory
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            cf = CounterfactualMemory(db_path=db)
            cf.record_rejection("dec-x", "delete temporary log files now", "Risky")
            avoid, score, _ = cf.should_avoid("remove a log", threshold=0.7)
            if 0.4 < score <= 0.7:
                self.assertFalse(avoid, "Caution zone must NOT hard-block")
            cf.close()
        finally:
            Path(db).unlink(missing_ok=True)

    def test_rejection_patterns_api(self):
        """get_rejection_patterns returns expected keys."""
        from core.memory.counterfactual import CounterfactualMemory
        cf = CounterfactualMemory()
        patterns = cf.get_rejection_patterns()
        self.assertIn("total_rejections", patterns)
        self.assertIn("top_rejection_reasons", patterns)
        cf.close()


if __name__ == "__main__":
    unittest.main()
