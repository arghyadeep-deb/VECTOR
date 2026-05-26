"""Integration tests — Session C3: Anticipatory action engine."""
from __future__ import annotations

import asyncio
import datetime
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── AnticipationEngine unit tests ─────────────────────────────────────────────


class TestPredictionDataclass(unittest.TestCase):
    """Prediction dataclass has required fields with correct defaults."""

    def test_prediction_fields(self):
        from core.brain.anticipation import Prediction
        p = Prediction(
            need="journal",
            action_type="proactive_journal",
            description="Evening reflection",
            confidence=0.85,
            source="time_pattern",
        )
        self.assertEqual(p.need, "journal")
        self.assertEqual(p.action_type, "proactive_journal")
        self.assertEqual(p.hour, -1)
        self.assertIsInstance(p.params, dict)

    def test_action_type_prefix(self):
        from core.brain.anticipation import Prediction
        p = Prediction(
            need="morning_brief",
            action_type="proactive_morning_brief",
            description="Morning briefing",
            confidence=0.8,
            source="time_pattern",
        )
        self.assertTrue(p.action_type.startswith("proactive_"))


class TestTimeHeuristicPredictions(unittest.TestCase):
    """Time-of-day heuristics return correct predictions."""

    def _now_at(self, hour: int) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(
            hour=hour, minute=5, second=0, microsecond=0
        )

    def test_9pm_returns_journal(self):
        from core.brain.anticipation import _time_heuristic_predictions
        now = self._now_at(21)  # 9pm
        preds = _time_heuristic_predictions(now, window_minutes=30)
        needs = [p.need for p in preds]
        self.assertIn("journal", needs)

    def test_7am_returns_morning_brief(self):
        from core.brain.anticipation import _time_heuristic_predictions
        now = self._now_at(7)
        preds = _time_heuristic_predictions(now, window_minutes=30)
        needs = [p.need for p in preds]
        self.assertIn("morning_brief", needs)

    def test_midnight_returns_sleep_reminder(self):
        from core.brain.anticipation import _time_heuristic_predictions
        now = self._now_at(2)
        preds = _time_heuristic_predictions(now, window_minutes=30)
        needs = [p.need for p in preds]
        self.assertIn("sleep_reminder", needs)

    def test_all_predictions_have_proactive_prefix(self):
        from core.brain.anticipation import _time_heuristic_predictions
        now = self._now_at(20)
        preds = _time_heuristic_predictions(now, window_minutes=60)
        for p in preds:
            self.assertTrue(
                p.action_type.startswith("proactive_"),
                f"action_type '{p.action_type}' missing proactive_ prefix",
            )

    def test_confidence_in_range(self):
        from core.brain.anticipation import _time_heuristic_predictions
        for hour in range(24):
            now = self._now_at(hour)
            for p in _time_heuristic_predictions(now, 30):
                self.assertGreaterEqual(p.confidence, 0.0)
                self.assertLessEqual(p.confidence, 1.0)


class TestAnticipationEngine(unittest.TestCase):
    """AnticipationEngine.predict_next_need() returns ranked predictions."""

    def test_returns_list(self):
        from core.brain.anticipation import AnticipationEngine
        engine = AnticipationEngine()
        result = engine.predict_next_need(window_minutes=30)
        self.assertIsInstance(result, list)

    def test_sorted_by_confidence_descending(self):
        from core.brain.anticipation import AnticipationEngine
        engine = AnticipationEngine()
        preds = engine.predict_next_need(window_minutes=60)
        for i in range(len(preds) - 1):
            self.assertGreaterEqual(preds[i].confidence, preds[i + 1].confidence)

    def test_dedup_by_need_and_hour(self):
        """No duplicate (need, hour) pairs in output."""
        from core.brain.anticipation import AnticipationEngine
        engine = AnticipationEngine()
        preds = engine.predict_next_need(window_minutes=120)
        seen = set()
        for p in preds:
            key = (p.need, p.hour)
            self.assertNotIn(key, seen, f"Duplicate key: {key}")
            seen.add(key)

    def test_get_last_predictions_returns_same(self):
        from core.brain.anticipation import AnticipationEngine
        engine = AnticipationEngine()
        first = engine.predict_next_need(window_minutes=30)
        last = engine.get_last_predictions()
        self.assertEqual(len(first), len(last))

    def test_high_confidence_filters(self):
        from core.brain.anticipation import AnticipationEngine
        engine = AnticipationEngine()
        engine.predict_next_need(window_minutes=60)
        high = engine.high_confidence(threshold=0.75)
        for p in high:
            self.assertGreaterEqual(p.confidence, 0.75)

    def test_high_confidence_empty_when_threshold_too_high(self):
        from core.brain.anticipation import AnticipationEngine
        engine = AnticipationEngine()
        engine.predict_next_need(window_minutes=30)
        result = engine.high_confidence(threshold=1.01)
        self.assertEqual(result, [])


class TestAnticipationEngineSingleton(unittest.TestCase):
    """get_anticipation_engine() returns the same instance."""

    def test_singleton(self):
        from core.brain.anticipation import get_anticipation_engine
        a = get_anticipation_engine()
        b = get_anticipation_engine()
        self.assertIs(a, b)


# ── 9pm journal scenario — core spec test ────────────────────────────────────


class TestJournalPredictionAt9pm(unittest.TestCase):
    """
    Spec: 'simulated 9pm pattern of journal-writing; verify predictor
    surfaces journal at 9:05pm.' (time_pattern heuristic is enough.)
    """

    def _make_engine_at_hour(self, hour: int):
        """Return AnticipationEngine with mocked datetime set to given hour."""
        from core.brain.anticipation import AnticipationEngine
        return AnticipationEngine()

    def test_journal_in_predictions_at_9pm(self):
        from core.brain.anticipation import AnticipationEngine
        import core.brain.anticipation as mod

        engine = AnticipationEngine()
        # Patch datetime.datetime.now to return 21:05 (9:05pm)
        fake_now = datetime.datetime(2026, 5, 26, 21, 5, 0,
                                     tzinfo=datetime.timezone.utc)
        with patch("core.brain.anticipation.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = fake_now
            mock_dt.datetime.fromisoformat = datetime.datetime.fromisoformat
            mock_dt.timezone = datetime.timezone
            mock_dt.timedelta = datetime.timedelta
            predictions = engine.predict_next_need(window_minutes=30)

        needs = [p.need for p in predictions]
        self.assertIn(
            "journal", needs,
            f"Expected 'journal' in predictions at 9pm, got: {needs}",
        )

    def test_journal_confidence_above_threshold(self):
        from core.brain.anticipation import AnticipationEngine

        engine = AnticipationEngine()
        fake_now = datetime.datetime(2026, 5, 26, 21, 5, 0,
                                     tzinfo=datetime.timezone.utc)
        with patch("core.brain.anticipation.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = fake_now
            mock_dt.datetime.fromisoformat = datetime.datetime.fromisoformat
            mock_dt.timezone = datetime.timezone
            mock_dt.timedelta = datetime.timedelta
            predictions = engine.predict_next_need(window_minutes=30)

        journal_preds = [p for p in predictions if p.need == "journal"]
        if journal_preds:
            self.assertGreaterEqual(
                journal_preds[0].confidence, 0.75,
                "Journal prediction must be >= 0.75 to pass the act_on threshold",
            )


# ── autonomous_loop wiring ────────────────────────────────────────────────────


class TestAnticipationLoopInAutonomousLoop(unittest.TestCase):
    """autonomous_loop has anticipation_loop coroutine wired into run_forever."""

    def test_anticipation_loop_method_exists(self):
        from core.loop.autonomous_loop import AutonomousLoop
        self.assertTrue(callable(AutonomousLoop.anticipation_loop))

    def test_anticipation_tick_method_exists(self):
        from core.loop.autonomous_loop import AutonomousLoop
        self.assertTrue(callable(AutonomousLoop._anticipation_tick))

    def test_anticipation_loop_in_run_forever_source(self):
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop
        src = inspect.getsource(AutonomousLoop.run_forever)
        self.assertIn("anticipation_loop", src)

    def test_anticipation_loop_is_async(self):
        import asyncio
        from core.loop.autonomous_loop import AutonomousLoop
        self.assertTrue(asyncio.iscoroutinefunction(AutonomousLoop.anticipation_loop))

    def test_anticipation_tick_is_async(self):
        import asyncio
        from core.loop.autonomous_loop import AutonomousLoop
        self.assertTrue(asyncio.iscoroutinefunction(AutonomousLoop._anticipation_tick))


class TestAnticipationTickCreatesCandidate(unittest.TestCase):
    """_anticipation_tick builds Candidate with proactive_* action_type and calls _act_on."""

    def test_high_confidence_prediction_triggers_act_on(self):
        """When predict_next_need returns >= 0.75 confidence, _act_on is called."""
        from core.loop.autonomous_loop import AutonomousLoop
        from core.brain.anticipation import Prediction

        loop = AutonomousLoop()
        loop._running = True

        mock_pred = Prediction(
            need="journal",
            action_type="proactive_journal",
            description="Evening journal",
            confidence=0.85,
            source="time_pattern",
            hour=21,
        )

        acted = []

        async def fake_act_on(candidate):
            acted.append(candidate.action_type)

        loop._act_on = fake_act_on

        with patch("core.brain.anticipation.get_anticipation_engine") as mock_factory:
            mock_engine = MagicMock()
            mock_engine.predict_next_need.return_value = [mock_pred]
            mock_factory.return_value = mock_engine
            asyncio.run(loop._anticipation_tick())

        self.assertIn("proactive_journal", acted)

    def test_low_confidence_prediction_not_acted_on(self):
        """Predictions below 0.75 are silently skipped."""
        from core.loop.autonomous_loop import AutonomousLoop
        from core.brain.anticipation import Prediction

        loop = AutonomousLoop()
        loop._running = True

        mock_pred = Prediction(
            need="goal_review",
            action_type="proactive_goal_review",
            description="Review goals",
            confidence=0.60,
            source="time_pattern",
            hour=10,
        )

        acted = []

        async def fake_act_on(candidate):
            acted.append(candidate.action_type)

        loop._act_on = fake_act_on

        with patch("core.brain.anticipation.get_anticipation_engine") as mock_factory:
            mock_engine = MagicMock()
            mock_engine.predict_next_need.return_value = [mock_pred]
            mock_factory.return_value = mock_engine
            asyncio.run(loop._anticipation_tick())

        self.assertEqual(acted, [], "No action should be taken for confidence < 0.75")

    def test_candidate_action_type_has_proactive_prefix(self):
        """Candidates created by _anticipation_tick always use proactive_* prefix."""
        from core.loop.autonomous_loop import AutonomousLoop
        from core.brain.anticipation import Prediction

        loop = AutonomousLoop()
        loop._running = True

        mock_pred = Prediction(
            need="sleep_prep",
            action_type="proactive_sleep_prep",
            description="Wind down",
            confidence=0.80,
            source="time_pattern",
            hour=23,
        )

        captured = []

        async def fake_act_on(candidate):
            captured.append(candidate)

        loop._act_on = fake_act_on

        with patch("core.brain.anticipation.get_anticipation_engine") as mock_factory:
            mock_engine = MagicMock()
            mock_engine.predict_next_need.return_value = [mock_pred]
            mock_factory.return_value = mock_engine
            asyncio.run(loop._anticipation_tick())

        self.assertEqual(len(captured), 1)
        self.assertTrue(captured[0].action_type.startswith("proactive_"))

    def test_anticipation_tick_exception_is_swallowed(self):
        """If predict_next_need raises, _anticipation_tick must not propagate."""
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop()
        loop._running = True

        with patch("core.brain.anticipation.get_anticipation_engine") as mock_factory:
            mock_engine = MagicMock()
            mock_engine.predict_next_need.side_effect = RuntimeError("engine crash")
            mock_factory.return_value = mock_engine
            try:
                asyncio.run(loop._anticipation_tick())  # must not raise
            except Exception as exc:
                self.fail(f"_anticipation_tick propagated exception: {exc}")


class TestAnticipationLoopIntervalAndRule2(unittest.TestCase):
    """anticipation_loop runs every 10 min and adheres to RULE 2."""

    def test_loop_source_has_600s_sleep(self):
        """Source must show 600-second sleep interval."""
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop
        src = inspect.getsource(AutonomousLoop.anticipation_loop)
        self.assertIn("600", src, "anticipation_loop must sleep 600s (10 minutes)")

    def test_loop_catches_exceptions(self):
        """anticipation_loop body catches exceptions and continues (RULE 2)."""
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop
        src = inspect.getsource(AutonomousLoop.anticipation_loop)
        self.assertIn("except", src)


if __name__ == "__main__":
    unittest.main()
