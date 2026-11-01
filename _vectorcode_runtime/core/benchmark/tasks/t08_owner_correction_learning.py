"""T08 — Owner Correction Learning: detect correction, store lesson, retrieve it.

Simulate VECTOR giving wrong answer, owner correcting it.
Verify CorrectionLearner detects the correction, stores a lesson,
and the lesson is retrievable for similar future situations.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult


class OwnerCorrectionLearningTask(BenchmarkTask):
    task_id = "T08"
    category = "owner_correction_learning"
    required_capability = "CorrectionDetector + CorrectionLearner: detect, store, retrieve correction lessons"
    expected_behavior = "Owner correction detected, lesson stored, retrievable for similar situations"

    def run(self, state) -> TaskResult:
        from core.memory.correction_learner import CorrectionDetector, CorrectionLearner

        detector = CorrectionDetector()
        learner = CorrectionLearner()

        # Simulate: VECTOR gave wrong answer, owner corrects
        prior_response = "I'll use threading for the concurrent task."
        correction_utterance = "No, don't use threading — use asyncio. We never use threading in VECTOR, it's against the rules."

        # Step 1: Detect the correction
        detection = detector.detect(correction_utterance, prior_response)
        is_correction = detection.is_correction

        if not is_correction:
            return self._failure(
                actual="CorrectionDetector failed to detect the correction",
                outcome="Detection failed — cannot learn from correction",
            )

        # Step 2: Process through learner — should store a lesson
        context = {"situation": "coding", "person_id": "owner"}
        lesson = learner.process_owner_message(
            utterance=correction_utterance,
            prior_vector_response=prior_response,
            context=context,
        )

        if lesson is None:
            return self._failure(
                actual="CorrectionLearner.process_owner_message returned None — lesson not stored",
                outcome="Learning failed — no lesson extracted",
                recovery_attempts=0,
            )

        # Step 3: Retrieve the lesson for a similar situation
        try:
            applicable = learner.retrieve_applicable_lessons(
                current_situation="concurrent coding task",
                domain="coding",
                limit=5,
            )
        except Exception as e:
            return self._failure(
                actual=f"retrieve_applicable_lessons failed: {e}",
                outcome="Lesson stored but retrieval broken",
            )

        lesson_found = len(applicable) > 0

        # Step 4: Build injection line for context engine
        injection = learner.build_injection_line(
            current_situation="concurrent coding task",
            domain="coding",
        )

        injection_works = len(injection) > 0

        if lesson_found and injection_works:
            return self._success(
                actual=(
                    f"Correction detected → lesson stored (domain={lesson.domain}) → "
                    f"retrieved {len(applicable)} applicable lesson(s) → "
                    f"injection line: {len(injection)} chars"
                ),
                outcome="Full correction learning loop verified",
                details={
                    "lesson_domain": lesson.domain,
                    "lesson_text": lesson.lesson[:80],
                    "applicable_count": len(applicable),
                    "injection_length": len(injection),
                },
            )
        else:
            return self._failure(
                actual=f"Lesson stored but retrieval={lesson_found}, injection={injection_works}",
                outcome="Learning stored but retrieval broken",
                details={
                    "lesson_domain": getattr(lesson, "domain", "unknown"),
                    "lesson_found": lesson_found,
                    "injection_works": injection_works,
                },
            )


TASK_CLASS = OwnerCorrectionLearningTask
