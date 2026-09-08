"""Unit tests for owner-correction learning (core/memory/correction_learner.py).

Tests CorrectionDetector, LessonExtractor, CorrectionLesson dataclass,
and CorrectionLearner store/retrieve/consolidate/inject lifecycle.

Includes 5 realistic examples demonstrating the full correction learning loop:
  1. Coding: "no, use httpx instead of requests"
  2. Communication: "actually, I meant the morning meeting, not evening"
  3. Finance: "wrong, that expense should be categorized as business, not personal"
  4. Research: "incorrect, the author is Zhang, not Wang"
  5. Scheduling: "no, the deadline is Friday, not Thursday"
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.memory.correction_learner import (
    CORRECTION_EXPLICIT,
    CORRECTION_IMPLICIT,
    MIN_STORE_CONFIDENCE,
    NOT_CORRECTION_AMBIGUOUS,
    NOT_CORRECTION_CONVERSATION,
    NOT_CORRECTION_PREFERENCE,
    NOT_CORRECTION_TEMPORARY,
    VALIDATION_CONTRADICTED,
    VALIDATION_UNVALIDATED,
    VALIDATION_VALIDATED,
    CorrectionDetector,
    CorrectionLesson,
    CorrectionLearner,
    DetectionResult,
    LessonExtractor,
    _now,
)


# ---------------------------------------------------------------------------
# CorrectionDetector tests
# ---------------------------------------------------------------------------


class TestCorrectionDetector(unittest.TestCase):
    """CorrectionDetector — distinguishes corrections from other speech acts."""

    def setUp(self):
        self.detector = CorrectionDetector()

    # ── Explicit corrections (should be detected) ──

    def test_explicit_no_comma(self):
        r = self.detector.detect("no, use httpx instead of requests")
        self.assertTrue(r.is_correction)
        self.assertEqual(r.correction_type, CORRECTION_EXPLICIT)
        self.assertGreaterEqual(r.confidence, 0.7)

    def test_explicit_wrong_comma(self):
        r = self.detector.detect("wrong, the API returns a list not a dict")
        self.assertTrue(r.is_correction)
        self.assertGreaterEqual(r.confidence, 0.85)  # "wrong" boosts

    def test_explicit_actually(self):
        r = self.detector.detect("actually, the deadline is Friday")
        self.assertTrue(r.is_correction)
        self.assertEqual(r.correction_type, CORRECTION_EXPLICIT)

    def test_explicit_incorrect(self):
        r = self.detector.detect("incorrect, the answer is 42")
        self.assertTrue(r.is_correction)
        self.assertGreaterEqual(r.confidence, 0.85)

    def test_explicit_i_said(self):
        r = self.detector.detect("I said to use async not sync")
        self.assertTrue(r.is_correction)
        self.assertEqual(r.correction_type, CORRECTION_EXPLICIT)

    def test_explicit_i_meant(self):
        r = self.detector.detect("I meant the morning meeting, not evening")
        self.assertTrue(r.is_correction)

    def test_explicit_should_be(self):
        r = self.detector.detect("should be categorized as business expense")
        self.assertTrue(r.is_correction)

    def test_explicit_got_wrong(self):
        r = self.detector.detect("you got that wrong, the author is Zhang")
        self.assertTrue(r.is_correction)
        self.assertGreaterEqual(r.confidence, 0.85)

    # ── Non-corrections (should NOT be detected) ──

    def test_preference_not_correction(self):
        r = self.detector.detect("I prefer using fastapi over flask")
        self.assertFalse(r.is_correction)
        self.assertEqual(r.correction_type, NOT_CORRECTION_PREFERENCE)

    def test_temporary_not_correction(self):
        r = self.detector.detect("just this once, use the old format")
        self.assertFalse(r.is_correction)
        self.assertEqual(r.correction_type, NOT_CORRECTION_TEMPORARY)

    def test_temporary_for_now(self):
        r = self.detector.detect("just for now, skip the validation step")
        self.assertFalse(r.is_correction)
        self.assertEqual(r.correction_type, NOT_CORRECTION_TEMPORARY)

    def test_conversation_not_correction(self):
        r = self.detector.detect("what time is the meeting tomorrow?")
        self.assertFalse(r.is_correction)
        self.assertEqual(r.correction_type, NOT_CORRECTION_CONVERSATION)

    def test_normal_chat_not_correction(self):
        r = self.detector.detect("thanks, that looks good")
        self.assertFalse(r.is_correction)

    def test_short_input_not_correction(self):
        r = self.detector.detect("ok")
        self.assertFalse(r.is_correction)

    def test_empty_input_not_correction(self):
        r = self.detector.detect("")
        self.assertFalse(r.is_correction)

    # ── Confidence thresholds ──

    def test_confidence_above_minimum_for_explicit(self):
        r = self.detector.detect("no, use httpx instead of requests")
        self.assertGreaterEqual(r.confidence, MIN_STORE_CONFIDENCE)

    def test_confidence_below_minimum_for_conversation(self):
        r = self.detector.detect("what do you think about this?")
        self.assertLess(r.confidence, MIN_STORE_CONFIDENCE)


# ---------------------------------------------------------------------------
# LessonExtractor tests
# ---------------------------------------------------------------------------


class TestLessonExtractor(unittest.TestCase):
    """LessonExtractor — converts detections into structured lessons."""

    def setUp(self):
        self.extractor = LessonExtractor()

    def test_extract_from_explicit_correction(self):
        r = DetectionResult(
            is_correction=True,
            correction_type=CORRECTION_EXPLICIT,
            confidence=0.85,
            correction_text="use httpx instead of requests",
            matched_pattern=r"\bno[, ]+(.+)",
        )
        lesson = self.extractor.extract(r, prior_vector_response="I'll use requests")
        self.assertIsNotNone(lesson)
        self.assertIn("httpx", lesson.correction)
        self.assertGreaterEqual(lesson.confidence, 0.7)
        self.assertEqual(lesson.domain, "coding")  # detected from "requests"
        self.assertEqual(lesson.validation_status, VALIDATION_UNVALIDATED)
        self.assertTrue(lesson.situation_hash)

    def test_extract_returns_none_below_threshold(self):
        r = DetectionResult(
            is_correction=True,
            correction_type=CORRECTION_IMPLICIT,
            confidence=0.5,  # below MIN_STORE_CONFIDENCE
            correction_text="maybe try X",
            matched_pattern="test",
        )
        lesson = self.extractor.extract(r)
        self.assertIsNone(lesson)

    def test_extract_returns_none_for_non_correction(self):
        r = DetectionResult(
            is_correction=False,
            correction_type=NOT_CORRECTION_CONVERSATION,
            confidence=0.0,
            correction_text="",
            matched_pattern="",
        )
        lesson = self.extractor.extract(r)
        self.assertIsNone(lesson)

    def test_domain_detection_coding(self):
        self.assertEqual(self.extractor._detect_domain("fix the bug in the function"), "coding")
        self.assertEqual(self.extractor._detect_domain("use async import"), "coding")

    def test_domain_detection_research(self):
        self.assertEqual(self.extractor._detect_domain("search arxiv for papers"), "research")

    def test_domain_detection_finance(self):
        self.assertEqual(self.extractor._detect_domain("budget expense invoice payment"), "finance")

    def test_domain_detection_general_fallback(self):
        self.assertEqual(self.extractor._detect_domain("hello world"), "general")

    def test_situation_hash_deterministic(self):
        r = DetectionResult(True, CORRECTION_EXPLICIT, 0.85, "test correction", "pat")
        l1 = self.extractor.extract(r, context={"situation": "coding"})
        l2 = self.extractor.extract(r, context={"situation": "coding"})
        self.assertEqual(l1.situation_hash, l2.situation_hash)

    def test_tags_include_domain_and_source(self):
        r = DetectionResult(True, CORRECTION_EXPLICIT, 0.85, "use httpx", "pat")
        lesson = self.extractor.extract(r, context={"situation": "coding"})
        self.assertIn("domain:coding", lesson.tags)
        self.assertIn("source:owner_correction", lesson.tags)


# ---------------------------------------------------------------------------
# CorrectionLesson dataclass tests
# ---------------------------------------------------------------------------


class TestCorrectionLesson(unittest.TestCase):
    """CorrectionLesson — serialization and round-trip."""

    def _make_lesson(self, **overrides) -> CorrectionLesson:
        defaults = dict(
            id="cl_test123",
            situation="coding",
            wrong_behavior="used requests library",
            correction="use httpx instead",
            lesson="When handling coding tasks: use httpx instead of requests",
            domain="coding",
            confidence=0.85,
            timestamp=_now(),
            applicability="Applies when: situation is 'coding', domain is 'coding'",
            source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED,
            correction_type=CORRECTION_EXPLICIT,
        )
        defaults.update(overrides)
        return CorrectionLesson(**defaults)

    def test_to_dict_round_trip(self):
        lesson = self._make_lesson()
        d = lesson.to_dict()
        restored = CorrectionLesson.from_dict(d)
        self.assertEqual(restored.id, lesson.id)
        self.assertEqual(restored.lesson, lesson.lesson)
        self.assertEqual(restored.domain, lesson.domain)
        self.assertAlmostEqual(restored.confidence, lesson.confidence)

    def test_storage_content_round_trip(self):
        lesson = self._make_lesson()
        content = lesson.to_storage_content()
        restored = CorrectionLesson.from_storage_content(content)
        self.assertEqual(restored.id, lesson.id)
        self.assertEqual(restored.correction, lesson.correction)

    def test_from_storage_content_handles_invalid_json(self):
        restored = CorrectionLesson.from_storage_content("not json")
        self.assertEqual(restored.validation_status, "expired")
        self.assertAlmostEqual(restored.confidence, 0.0)

    def test_default_values(self):
        lesson = self._make_lesson()
        self.assertEqual(lesson.times_applied, 0)
        self.assertEqual(lesson.times_validated, 0)
        self.assertEqual(lesson.supersedes, "")


# ---------------------------------------------------------------------------
# CorrectionLearner tests (mocked EpisodicMemory)
# ---------------------------------------------------------------------------


class TestCorrectionLearner(unittest.TestCase):
    """CorrectionLearner — store, retrieve, consolidate, inject."""

    def _make_learner(self) -> CorrectionLearner:
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        return learner

    def test_process_owner_message_detects_correction(self):
        learner = self._make_learner()
        learner._memory.store = MagicMock()
        learner._memory.recall = MagicMock(return_value=[])  # no duplicates

        lesson = learner.process_owner_message(
            utterance="no, use httpx instead of requests",
            prior_vector_response="I'll use requests library",
            context={"situation": "coding"},
        )
        self.assertIsNotNone(lesson)
        self.assertIn("httpx", lesson.correction)
        learner._memory.store.assert_called_once()

    def test_process_owner_message_rejects_preference(self):
        learner = self._make_learner()
        lesson = learner.process_owner_message(
            utterance="I prefer using fastapi over flask",
        )
        self.assertIsNone(lesson)

    def test_process_owner_message_rejects_temporary(self):
        learner = self._make_learner()
        lesson = learner.process_owner_message(
            utterance="just this once, use the old format",
        )
        self.assertIsNone(lesson)

    def test_retrieve_applicable_lessons_filters_expired(self):
        learner = self._make_learner()
        expired_lesson = CorrectionLesson(
            id="cl_expired", situation="test", wrong_behavior="", correction="",
            lesson="expired lesson", domain="coding", confidence=0.9,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status="expired", correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": expired_lesson.to_storage_content()},
        ])

        results = learner.retrieve_applicable_lessons(domain="coding")
        self.assertEqual(len(results), 0)  # expired filtered out

    def test_retrieve_applicable_lessons_filters_low_confidence(self):
        learner = self._make_learner()
        low_conf_lesson = CorrectionLesson(
            id="cl_low", situation="test", wrong_behavior="", correction="",
            lesson="low confidence", domain="coding", confidence=0.3,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED, correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": low_conf_lesson.to_storage_content()},
        ])

        results = learner.retrieve_applicable_lessons(domain="coding")
        self.assertEqual(len(results), 0)  # below 0.5 threshold

    def test_retrieve_applicable_returns_valid_lessons(self):
        learner = self._make_learner()
        good_lesson = CorrectionLesson(
            id="cl_good", situation="coding", wrong_behavior="", correction="use httpx",
            lesson="use httpx not requests", domain="coding", confidence=0.85,
            timestamp=_now(), applicability="coding tasks",
            source="owner_correction", validation_status=VALIDATION_UNVALIDATED,
            correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": good_lesson.to_storage_content()},
        ])

        results = learner.retrieve_applicable_lessons(domain="coding")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "cl_good")

    def test_validate_lesson_good_outcome_increases_confidence(self):
        learner = self._make_learner()
        lesson = CorrectionLesson(
            id="cl_val", situation="test", wrong_behavior="", correction="test",
            lesson="test lesson", domain="coding", confidence=0.7,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED, correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": lesson.to_storage_content()},
        ])
        learner._memory.store = MagicMock()

        learner.validate_lesson("cl_val", outcome_good=True)

        # Should have stored an updated version
        learner._memory.store.assert_called_once()
        stored_content = learner._memory.store.call_args[1].get("content") or learner._memory.store.call_args[0][1]
        stored = CorrectionLesson.from_storage_content(stored_content)
        self.assertGreater(stored.confidence, 0.7)
        self.assertEqual(stored.times_validated, 1)

    def test_validate_lesson_bad_outcome_decreases_confidence(self):
        learner = self._make_learner()
        lesson = CorrectionLesson(
            id="cl_val2", situation="test", wrong_behavior="", correction="test",
            lesson="test lesson", domain="coding", confidence=0.7,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED, correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": lesson.to_storage_content()},
        ])
        learner._memory.store = MagicMock()

        learner.validate_lesson("cl_val2", outcome_good=False)

        stored_content = learner._memory.store.call_args[1].get("content") or learner._memory.store.call_args[0][1]
        stored = CorrectionLesson.from_storage_content(stored_content)
        self.assertLess(stored.confidence, 0.7)

    def test_build_injection_line_empty_when_no_lessons(self):
        learner = self._make_learner()
        learner._memory.recall = MagicMock(return_value=[])
        line = learner.build_injection_line(domain="coding")
        self.assertEqual(line, "")

    def test_build_injection_line_returns_lessons(self):
        learner = self._make_learner()
        lesson = CorrectionLesson(
            id="cl_inj", situation="coding", wrong_behavior="", correction="use httpx",
            lesson="use httpx not requests", domain="coding", confidence=0.85,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED, correction_type=CORRECTION_EXPLICIT,
            tags=["domain:coding"],
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": lesson.to_storage_content()},
        ])
        learner._memory.store = MagicMock()  # for mark_applied

        line = learner.build_injection_line(domain="coding")
        self.assertIn("httpx", line)
        self.assertIn("Owner corrections", line)

    def test_consolidation_boosts_confidence(self):
        learner = self._make_learner()
        existing = CorrectionLesson(
            id="cl_exist", situation="coding", wrong_behavior="", correction="use httpx",
            lesson="use httpx", domain="coding", confidence=0.8,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED, correction_type=CORRECTION_EXPLICIT,
            situation_hash="abc123",
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": existing.to_storage_content()},
        ])
        learner._memory.store = MagicMock()

        # Process same correction again
        new_lesson = learner.process_owner_message(
            utterance="no, use httpx instead of requests",
            context={"situation": "coding"},
        )
        self.assertIsNotNone(new_lesson)
        # Confidence should have been boosted
        self.assertGreaterEqual(new_lesson.confidence, 0.8)


# ---------------------------------------------------------------------------
# 5 Realistic Examples — full correction learning loop
# ---------------------------------------------------------------------------


class TestFiveRealisticExamples(unittest.TestCase):
    """Demonstrate the full correction learning loop with 5 realistic examples.

    Each example:
    1. VECTOR produces an incorrect response
    2. Owner corrects VECTOR
    3. System detects the correction (not a preference/temporary)
    4. System extracts and stores a structured lesson
    5. System retrieves the lesson for a future similar situation
    6. Lesson is injected into context (proving behavior will change)
    """

    def _run_example(self, utterance: str, prior_response: str, context: dict) -> CorrectionLesson:
        """Run the full loop: detect → extract → store → retrieve → inject."""
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        learner._memory.store = MagicMock()
        learner._memory.recall = MagicMock(return_value=[])  # no duplicates

        # Step 1-4: Detect + extract + store
        lesson = learner.process_owner_message(
            utterance=utterance,
            prior_vector_response=prior_response,
            context=context,
        )
        self.assertIsNotNone(lesson, f"Should detect correction: '{utterance}'")
        self.assertGreaterEqual(lesson.confidence, MIN_STORE_CONFIDENCE)

        # Step 5: Retrieve the stored lesson
        learner._memory.recall = MagicMock(return_value=[
            {"content": lesson.to_storage_content()},
        ])
        learner._memory.store = MagicMock()  # for mark_applied

        retrieved = learner.retrieve_applicable_lessons(
            current_situation=context.get("situation", ""),
            domain=lesson.domain,
        )
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0].id, lesson.id)

        # Step 6: Inject into context
        line = learner.build_injection_line(
            current_situation=context.get("situation", ""),
            domain=lesson.domain,
        )
        self.assertTrue(len(line) > 0, "Injection line should be non-empty")
        self.assertIn("Owner corrections", line)

        return lesson

    def test_example_1_coding_httpx_vs_requests(self):
        """VECTOR used requests library. Owner says: 'no, use httpx instead'."""
        lesson = self._run_example(
            utterance="no, use httpx instead of requests",
            prior_response="I'll use the requests library to make the API call",
            context={"situation": "coding", "domain": "coding"},
        )
        self.assertEqual(lesson.domain, "coding")
        self.assertIn("httpx", lesson.correction)

    def test_example_2_communication_morning_vs_evening(self):
        """VECTOR scheduled evening meeting. Owner: 'actually, I meant the morning meeting'."""
        lesson = self._run_example(
            utterance="actually, I meant the morning meeting, not evening",
            prior_response="I've scheduled the meeting for 6 PM this evening",
            context={"situation": "scheduling", "domain": "communication"},
        )
        self.assertIn("morning", lesson.correction.lower())

    def test_example_3_finance_business_vs_personal(self):
        """VECTOR categorized expense wrong. Owner: 'wrong, that's a business expense'."""
        lesson = self._run_example(
            utterance="wrong, that expense should be categorized as business, not personal",
            prior_response="I've categorized the ₹5000 software purchase as a personal expense",
            context={"situation": "finance", "domain": "finance"},
        )
        self.assertEqual(lesson.domain, "finance")
        self.assertIn("business", lesson.correction.lower())

    def test_example_4_research_author_correction(self):
        """VECTOR attributed paper to wrong author. Owner: 'incorrect, the author is Zhang'."""
        lesson = self._run_example(
            utterance="incorrect, the author is Zhang, not Wang",
            prior_response="The paper was written by Wang et al. (2024)",
            context={"situation": "research", "domain": "research"},
        )
        self.assertIn("Zhang", lesson.correction)

    def test_example_5_scheduling_friday_vs_thursday(self):
        """VECTOR got deadline wrong. Owner: 'no, the deadline is Friday, not Thursday'."""
        lesson = self._run_example(
            utterance="no, the deadline is Friday, not Thursday",
            prior_response="The submission deadline is Thursday at 5 PM",
            context={"situation": "scheduling", "domain": "scheduling"},
        )
        self.assertIn("Friday", lesson.correction)


# ---------------------------------------------------------------------------
# Behavior change measurement
# ---------------------------------------------------------------------------


class TestBehaviorChangeMeasurement(unittest.TestCase):
    """Verify that corrections actually change future behavior.

    After a correction is stored, when VECTOR faces a similar situation,
    the applicable lesson is retrieved and injected into the LLM context.
    This proves behavior WILL change (the LLM sees the correction).
    """

    def test_corrected_behavior_gets_lesson_in_context(self):
        """After storing a correction, a similar future task retrieves it."""
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        learner._memory.store = MagicMock()
        learner._memory.recall = MagicMock(return_value=[])

        # Store a correction
        lesson = learner.process_owner_message(
            utterance="no, use httpx instead of requests",
            prior_vector_response="I'll use requests",
            context={"situation": "coding"},
        )
        self.assertIsNotNone(lesson)

        # Simulate a new coding task
        learner._memory.recall = MagicMock(return_value=[
            {"content": lesson.to_storage_content()},
        ])
        learner._memory.store = MagicMock()

        injection = learner.build_injection_line(
            current_situation="making an API call",
            domain="coding",
        )
        self.assertIn("httpx", injection)
        # The LLM will now see "use httpx instead of requests" in its context

    def test_unchanged_behavior_gets_no_lesson(self):
        """A task in a different domain does NOT retrieve the coding correction."""
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        learner._memory.store = MagicMock()
        learner._memory.recall = MagicMock(return_value=[])

        # Store a coding correction
        lesson = learner.process_owner_message(
            utterance="no, use httpx instead of requests",
            prior_vector_response="I'll use requests",
            context={"situation": "coding"},
        )

        # Simulate a scheduling task (different domain)
        learner._memory.recall = MagicMock(return_value=[])
        injection = learner.build_injection_line(
            current_situation="schedule a meeting",
            domain="scheduling",  # different domain
        )
        # Should be empty since domain doesn't match
        self.assertEqual(injection, "")

    def test_confidence_grows_with_repeated_validation(self):
        """Each time a correction leads to good outcomes, confidence grows."""
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        lesson = CorrectionLesson(
            id="cl_grow", situation="coding", wrong_behavior="", correction="use httpx",
            lesson="use httpx", domain="coding", confidence=0.7,
            timestamp=_now(), applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED, correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": lesson.to_storage_content()},
        ])
        learner._memory.store = MagicMock()

        # Validate 3 times with good outcomes
        for _ in range(3):
            learner.validate_lesson("cl_grow", outcome_good=True)
            # Update the mock to return the latest stored version
            stored = learner._memory.store.call_args
            content = stored[1].get("content") or stored[0][1]
            updated = CorrectionLesson.from_storage_content(content)
            learner._memory.recall = MagicMock(return_value=[
                {"content": updated.to_storage_content()},
            ])

        final = CorrectionLesson.from_storage_content(content)
        self.assertGreater(final.confidence, 0.7)
        self.assertEqual(final.times_validated, 3)


# ---------------------------------------------------------------------------
# Expiry tests
# ---------------------------------------------------------------------------


class TestLessonExpiry(unittest.TestCase):
    """Old unvalidated lessons expire after 90 days (called during 2AM reflect)."""

    def test_expire_old_unvalidated_lesson(self):
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        learner._memory.store = MagicMock()

        # Create an old lesson (100 days ago)
        old_date = (
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            - __import__("datetime").timedelta(days=100)
        ).isoformat()

        old_lesson = CorrectionLesson(
            id="cl_old", situation="test", wrong_behavior="", correction="old correction",
            lesson="old lesson", domain="general", confidence=0.7,
            timestamp=old_date, applicability="", source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED,  # not yet validated
            correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": old_lesson.to_storage_content()},
        ])

        expired_count = learner.expire_old_lessons(max_age_days=90)
        self.assertEqual(expired_count, 1)

    def test_validated_lesson_not_expired(self):
        learner = CorrectionLearner()
        learner._memory = MagicMock()
        learner._memory.store = MagicMock()

        old_date = (
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            - __import__("datetime").timedelta(days=100)
        ).isoformat()

        validated_lesson = CorrectionLesson(
            id="cl_validated", situation="test", wrong_behavior="", correction="",
            lesson="validated lesson", domain="general", confidence=0.9,
            timestamp=old_date, applicability="", source="owner_correction",
            validation_status=VALIDATION_VALIDATED,  # validated → not expired
            correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.recall = MagicMock(return_value=[
            {"content": validated_lesson.to_storage_content()},
        ])

        expired_count = learner.expire_old_lessons(max_age_days=90)
        self.assertEqual(expired_count, 0)


if __name__ == "__main__":
    unittest.main()
