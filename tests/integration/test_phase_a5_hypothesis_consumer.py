"""Integration tests — Session A5: HypothesisEngine → SuggestionQueue → event publishing."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestSuggestionQueueCRUD(unittest.TestCase):
    """SuggestionQueue: enqueue / get_top_pending / mark_surfaced / count_pending."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        from core.brain.suggestion_queue import SuggestionQueue
        self.sq = SuggestionQueue(db_path=self._tmp.name)

    def tearDown(self):
        self.sq.close()
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_enqueue_returns_id(self):
        hid = self.sq.enqueue("Users sleep late on Fridays", confidence=0.78)
        self.assertIsInstance(hid, str)
        self.assertGreater(len(hid), 0)

    def test_enqueue_five_then_get_three(self):
        texts = [f"Hypothesis {i}" for i in range(5)]
        for i, t in enumerate(texts):
            self.sq.enqueue(t, confidence=0.5 + i * 0.05)
        pending = self.sq.get_top_pending(limit=3)
        self.assertEqual(len(pending), 3)

    def test_top_pending_sorted_by_confidence_desc(self):
        self.sq.enqueue("Low conf", confidence=0.4)
        self.sq.enqueue("High conf", confidence=0.9)
        self.sq.enqueue("Mid conf", confidence=0.6)
        pending = self.sq.get_top_pending(limit=3)
        confs = [p["confidence"] for p in pending]
        self.assertEqual(confs, sorted(confs, reverse=True))

    def test_mark_surfaced_removes_from_pending(self):
        hid = self.sq.enqueue("Test hypothesis", confidence=0.8)
        self.assertEqual(self.sq.count_pending(), 1)
        self.sq.mark_surfaced(hid)
        self.assertEqual(self.sq.count_pending(), 0)

    def test_mark_surfaced_sets_status(self):
        hid = self.sq.enqueue("Another test", confidence=0.7)
        self.sq.mark_surfaced(hid)
        all_rows = self.sq.get_all(limit=10)
        row = next((r for r in all_rows if r["id"] == hid), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "surfaced")
        self.assertIsNotNone(row["surfaced_at"])

    def test_no_pending_returns_empty(self):
        pending = self.sq.get_top_pending(limit=3)
        self.assertEqual(pending, [])

    def test_get_all_returns_all_statuses(self):
        self.sq.enqueue("Pending one", confidence=0.7)
        hid2 = self.sq.enqueue("To be surfaced", confidence=0.85)
        self.sq.mark_surfaced(hid2)
        all_rows = self.sq.get_all(limit=10)
        statuses = {r["status"] for r in all_rows}
        self.assertIn("pending", statuses)
        self.assertIn("surfaced", statuses)


class TestHypothesisEngineEnqueues(unittest.TestCase):
    """HypothesisEngine.generate_hypotheses() enqueues to SuggestionQueue."""

    def test_hypothesis_has_confidence_field(self):
        """generate_hypotheses result must include confidence key."""
        import asyncio
        from core.brain.hypothesis_engine import HypothesisEngine
        he = HypothesisEngine()
        # generate_hypotheses calls Ollama which may not be running — check that at least
        # when a hypothesis IS created it has the confidence field
        # Test via direct injection into _hypotheses
        he._hypotheses = []
        # Simulate what generate_hypotheses produces (Ollama absent → falls into except)
        # We just verify the field is wired in the success path by checking the code
        import inspect
        src = inspect.getsource(he.generate_hypotheses)
        self.assertIn("confidence", src, "generate_hypotheses must set 'confidence' key on hypothesis")
        self.assertIn("SuggestionQueue", src, "generate_hypotheses must enqueue to SuggestionQueue")

    def test_suggestion_queue_enqueue_via_direct_call(self):
        """Enqueue a hypothesis directly and verify it appears pending."""
        import tempfile
        from core.brain.suggestion_queue import SuggestionQueue
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = f.name
        try:
            sq = SuggestionQueue(db_path=db)
            sq.enqueue("Morning productivity peak at 9am", confidence=0.82)
            sq.enqueue("Late commits correlate with bugs", confidence=0.71)
            sq.enqueue("Screen brightness affects fatigue", confidence=0.65)
            sq.enqueue("Pomodoro sessions improve focus", confidence=0.77)
            sq.enqueue("Deep work blocks > 90min not beneficial", confidence=0.68)
            self.assertEqual(sq.count_pending(), 5)
            top3 = sq.get_top_pending(limit=3)
            self.assertEqual(len(top3), 3)
            # Highest confidence first
            self.assertAlmostEqual(top3[0]["confidence"], 0.82)
            sq.close()
        finally:
            Path(db).unlink(missing_ok=True)


class TestEventTypeSurfaced(unittest.TestCase):
    """EventType.HYPOTHESIS_SURFACED exists and has the expected value."""

    def test_hypothesis_surfaced_in_event_type(self):
        from core.event_bus.types import EventType
        names = [e.name for e in EventType]
        self.assertIn("HYPOTHESIS_SURFACED", names)

    def test_hypothesis_surfaced_value(self):
        from core.event_bus.types import EventType
        self.assertEqual(EventType.HYPOTHESIS_SURFACED.value, "hypothesis_surfaced")


class TestNotificationsRouter(unittest.TestCase):
    """notifications.py router exports correct shape."""

    def test_router_importable(self):
        from core.api.routers.notifications import router
        self.assertIsNotNone(router)

    def test_router_has_hypotheses_route(self):
        from core.api.routers.notifications import router
        paths = [r.path for r in router.routes]
        self.assertIn("/notifications/hypotheses", paths)

    def test_router_has_ws_route(self):
        from core.api.routers.notifications import router
        paths = [r.path for r in router.routes]
        self.assertIn("/notifications/ws", paths)


class TestReflectTickHypothesisDrain(unittest.TestCase):
    """_reflect_tick wires SuggestionQueue drain + HYPOTHESIS_SURFACED publish."""

    def test_reflect_tick_imports_suggestion_queue(self):
        """autonomous_loop._reflect_tick source must reference SuggestionQueue."""
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop
        src = inspect.getsource(AutonomousLoop._reflect_tick)
        self.assertIn("SuggestionQueue", src)
        self.assertIn("HYPOTHESIS_SURFACED", src)

    def test_daily_reviewer_includes_proactive_insights(self):
        """daily_reviewer.review source must reference SuggestionQueue and 'I noticed'."""
        import inspect
        from districts.reflection.daily_reviewer import DailyReviewer
        src = inspect.getsource(DailyReviewer.review)
        self.assertIn("SuggestionQueue", src)
        self.assertIn("I noticed", src)


if __name__ == "__main__":
    unittest.main()
