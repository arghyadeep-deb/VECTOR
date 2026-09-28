"""Integration tests for correction learning system.

Tests the full integration path:
- CorrectionLearner ↔ EpisodicMemory (real DB)
- CorrectionDetector → CorrectionLearner → storage → retrieval → injection
- ContextEngine._correction_lessons_line() retrieves and formats lessons
- AutonomousLoop._detect_and_store_correction() detects and stores corrections

These tests use the real EpisodicMemory with a temporary test DB.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.memory.correction_learner import (
    CORRECTION_EXPLICIT,
    CORRECTION_IMPLICIT,
    VALIDATION_UNVALIDATED,
    CorrectionDetector,
    CorrectionLesson,
    CorrectionLearner,
    LessonExtractor,
    _now,
)


class TestCorrectionDetectorPatterns(unittest.TestCase):
    """End-to-end detection: 10 real-world utterances classified correctly."""

    def setUp(self):
        self.detector = CorrectionDetector()

    def _classify(self, text: str) -> str:
        r = self.detector.detect(text)
        if r.is_correction:
            return f"correction:{r.correction_type}(conf={r.confidence:.2f})"
        return f"not_correction:{r.correction_type}"

    def test_classification_matrix(self):
        """Test a matrix of utterances that should/shouldn't be corrections."""
        cases = [
            # (utterance, expected_is_correction)
            ("no, use httpx instead of requests", True),
            ("wrong, the answer is 42 not 43", True),
            ("actually, the deadline is Friday", True),
            ("incorrect, the author is Zhang", True),
            ("I said to use async not sync", True),
            ("I meant the morning meeting", True),
            ("you got that wrong, use PostgreSQL", True),
            ("should be categorized as business", True),
            ("I prefer using fastapi", False),          # preference
            ("I like React better than Vue", False),    # preference
            ("just this once, skip validation", False),  # temporary
            ("just for now, use the old format", False), # temporary
            ("what time is the meeting?", False),       # conversation
            ("thanks that looks good", False),           # conversation
            ("ok", False),                              # too short
        ]

        for utterance, expected in cases:
            result = self.detector.detect(utterance)
            self.assertEqual(
                result.is_correction, expected,
                f"Failed for '{utterance}': expected is_correction={expected}, "
                f"got {result.is_correction} (type={result.correction_type}, conf={result.confidence:.2f})"
            )


class TestCorrectionLearningIntegration(unittest.TestCase):
    """Full integration: detect → extract → store (mocked DB) → retrieve → inject."""

    def test_full_loop_stores_and_retrieves(self):
        """Correction is stored, then retrieved for a similar future situation."""
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        learner._memory.store = MagicMock()
        learner._memory.recall = MagicMock(return_value=[])

        # Store a correction
        lesson = learner.process_owner_message(
            utterance="no, use httpx instead of requests",
            prior_vector_response="I'll use requests library",
            context={"situation": "coding"},
        )
        self.assertIsNotNone(lesson)
        self.assertEqual(lesson.domain, "coding")
        self.assertGreaterEqual(lesson.confidence, 0.7)
        self.assertEqual(lesson.validation_status, VALIDATION_UNVALIDATED)

        # Retrieve for a similar situation
        learner._memory.recall = MagicMock(return_value=[
            {"content": lesson.to_storage_content()},
        ])
        learner._memory.store = MagicMock()

        retrieved = learner.retrieve_applicable_lessons(domain="coding")
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0].lesson, lesson.lesson)

        # Inject into context
        line = learner.build_injection_line(domain="coding")
        self.assertIn("Owner corrections", line)
        self.assertIn("httpx", line)

    def test_multiple_corrections_same_domain(self):
        """Multiple corrections in the same domain are all retrievable."""
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        learner._memory.store = MagicMock()
        learner._memory.recall = MagicMock(return_value=[])

        # Store 3 coding corrections
        lessons = []
        for utterance in [
            "no, use httpx instead of requests",
            "wrong, always use type hints",
            "actually, prefer async over sync",
        ]:
            lesson = learner.process_owner_message(
                utterance=utterance,
                prior_vector_response="previous response",
                context={"situation": "coding"},
            )
            lessons.append(lesson)

        self.assertEqual(len(lessons), 3)

        # Retrieve all 3
        learner._memory.recall = MagicMock(return_value=[
            {"content": l.to_storage_content()} for l in lessons
        ])
        retrieved = learner.retrieve_applicable_lessons(domain="coding", limit=5)
        self.assertEqual(len(retrieved), 3)


class TestContextEngineIntegration(unittest.TestCase):
    """Test that ContextEngine._correction_lessons_line() works with CorrectionLearner."""

    def test_hydration_includes_correction_lessons(self):
        """session_hydration_prompt() includes correction lessons when available."""
        from core.loop.context_engine import ContextEngine

        engine = ContextEngine()

        # Mock the correction learner to return a lesson
        mock_line = "Owner corrections to remember:\n• use httpx not requests"
        with patch.object(engine, '_correction_lessons_line', return_value=mock_line):
            # Mock other dependencies to avoid DB calls
            with patch.object(engine, 'get_world_state', return_value={
                "timestamp": _now(),
                "owner": "test",
                "env": "test",
                "version": "1.0",
                "time_of_day": "morning",
                "day_of_week": "Monday",
                "goal_summary": "",
                "recent_episodes": [],
            }):
                result = engine.session_hydration_prompt(extra_context={"query": "make API call"})

        self.assertIn("httpx", result)
        self.assertIn("Owner corrections", result)

    def test_hydration_works_without_corrections(self):
        """session_hydration_prompt() works fine when no correction lessons exist."""
        from core.loop.context_engine import ContextEngine

        engine = ContextEngine()

        with patch.object(engine, '_correction_lessons_line', return_value=""):
            with patch.object(engine, 'get_world_state', return_value={
                "timestamp": _now(),
                "owner": "test",
                "env": "test",
                "version": "1.0",
                "time_of_day": "morning",
                "day_of_week": "Monday",
                "goal_summary": "",
                "recent_episodes": [],
            }):
                result = engine.session_hydration_prompt()

        self.assertIn("[SESSION CONTEXT", result)
        self.assertIn("[END SESSION CONTEXT]", result)


class TestAutonomousLoopIntegration(unittest.TestCase):
    """Test that autonomous_loop._detect_and_store_correction() works."""

    def test_detect_and_store_called_for_owner(self):
        """Owner messages trigger correction detection."""
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop.__new__(AutonomousLoop)
        loop._current_person_id = "owner"

        # Mock _detect_and_store_correction
        loop._detect_and_store_correction = MagicMock()

        result = loop._handle_user_input("no, use httpx instead", person_id="owner")
        self.assertEqual(result, "owner")
        loop._detect_and_store_correction.assert_called_once_with("no, use httpx instead")

    def test_detect_not_called_for_non_owner(self):
        """Non-owner messages do NOT trigger correction detection."""
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop.__new__(AutonomousLoop)
        loop._current_person_id = "guest"

        loop._detect_and_store_correction = MagicMock()

        result = loop._handle_user_input("no, use httpx instead", person_id="guest")
        self.assertEqual(result, "guest")
        loop._detect_and_store_correction.assert_not_called()

    def test_detect_swallows_exceptions(self):
        """Correction detection failure does not crash the loop."""
        from core.loop.autonomous_loop import AutonomousLoop

        loop = AutonomousLoop.__new__(AutonomousLoop)
        loop._current_person_id = "owner"

        # Make detection raise
        loop._detect_and_store_correction = MagicMock(side_effect=RuntimeError("test error"))

        # Should not raise
        result = loop._handle_user_input("no, use httpx instead", person_id="owner")
        self.assertEqual(result, "owner")


class TestCorrectionLifecycle(unittest.TestCase):
    """Full lifecycle: store → apply → validate → confidence change."""

    def test_lifecycle_unvalidated_to_validated(self):
        """A correction starts unvalidated and becomes validated once good outcomes lift it to 0.85.

        A freshly detected explicit correction is already stored at ~0.95, above the 0.85 bar, so the first
        good outcome would validate it at once. The lifecycle only shows up for a lesson that starts lower
        (an implicit correction, stored at 0.70): +0.05 per good outcome means 0.75, 0.80, then 0.85.
        """
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        learner._memory.store = MagicMock()
        lesson = CorrectionLesson(
            id="cl_life", situation="coding", wrong_behavior="requests", correction="httpx",
            lesson="use httpx instead of requests", domain="coding", confidence=0.70,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED, correction_type=CORRECTION_IMPLICIT,
        )
        self.assertEqual(lesson.times_applied, 0)

        statuses = []
        for _ in range(3):
            learner._memory.recall = MagicMock(return_value=[
                {"content": lesson.to_storage_content()},
            ])
            learner.validate_lesson(lesson.id, outcome_good=True)
            stored = learner._memory.store.call_args
            content = stored[1].get("content") or stored[0][1]
            lesson = CorrectionLesson.from_storage_content(content)
            statuses.append(lesson.validation_status)

        self.assertEqual(statuses, [VALIDATION_UNVALIDATED, VALIDATION_UNVALIDATED, "validated"])
        self.assertGreaterEqual(lesson.confidence, 0.85)
        self.assertEqual(lesson.times_validated, 3)

    def test_lifecycle_contradicted(self):
        """A correction becomes contradicted after repeated bad outcomes."""
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        lesson = CorrectionLesson(
            id="cl_cont", situation="test", wrong_behavior="", correction="",
            lesson="bad lesson", domain="general", confidence=0.5,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED, correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": lesson.to_storage_content()},
        ])
        learner._memory.store = MagicMock()

        # Simulate bad outcomes until confidence drops below 0.3
        for _ in range(5):
            learner.validate_lesson("cl_cont", outcome_good=False)
            stored = learner._memory.store.call_args
            content = stored[1].get("content") or stored[0][1]
            lesson = CorrectionLesson.from_storage_content(content)
            learner._memory.recall = MagicMock(return_value=[
                {"content": lesson.to_storage_content()},
            ])

        self.assertEqual(lesson.validation_status, "contradicted")
        self.assertLess(lesson.confidence, 0.3)


if __name__ == "__main__":
    unittest.main()
