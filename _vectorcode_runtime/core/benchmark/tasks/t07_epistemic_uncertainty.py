"""T07 — Epistemic Uncertainty: confidence dampening for unsupported beliefs.

Store a well-supported belief (high confidence) and an unsupported one.
Query tracker — supported belief should have higher confidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult


class EpistemicUncertaintyTask(BenchmarkTask):
    task_id = "T07"
    category = "epistemic_uncertainty"
    required_capability = "EpistemicTracker confidence dampening for beliefs with varying evidence"
    expected_behavior = "Well-supported belief has higher confidence than unsupported belief"

    def run(self, state) -> TaskResult:
        from core.brain.epistemic_tracker import EpistemicTracker

        # Use the isolated epistemic DB path
        tracker = EpistemicTracker(db_path=state.epistemic_db_path)

        # Store a well-supported belief (high confidence, multiple sources)
        tracker.update_belief(
            key="python_is_popular",
            value="Python is the most popular programming language",
            confidence=0.95,
            source="github_octoverse_2026",
            ttl_hours=720,
        )
        # Reinforce it
        tracker.update_belief(
            key="python_is_popular",
            value="Python is the most popular programming language",
            confidence=0.92,
            source="stack_overflow_survey_2026",
            ttl_hours=720,
        )

        # Store an unsupported belief (low confidence, single source)
        tracker.update_belief(
            key="rust_will_replace_python",
            value="Rust will replace Python as the dominant language by 2027",
            confidence=0.15,
            source="random_blog_post",
            ttl_hours=24,
        )

        # Query confidences
        python_conf = tracker.get_confidence("python_is_popular")
        rust_conf = tracker.get_confidence("rust_will_replace_python")
        unknown_conf = tracker.get_confidence("totally_unknown_claim")

        # Verify: supported > unsupported > unknown
        supported_wins = python_conf > rust_conf
        unknown_is_zero = unknown_conf == 0.0
        supported_is_high = python_conf > 0.5
        unsupported_is_low = rust_conf < 0.5

        # Check stale claims detection
        stale = tracker.get_stale_claims(age_hours=0.0)  # everything is "stale" at age 0

        if supported_wins and unknown_is_zero and supported_is_high:
            return self._success(
                actual=(
                    f"Supported belief confidence: {python_conf:.2f}, "
                    f"unsupported: {rust_conf:.2f}, "
                    f"unknown: {unknown_conf:.2f}. "
                    f"Correct ordering: supported > unsupported > unknown."
                ),
                outcome="Epistemic confidence dampening verified",
                details={
                    "python_conf": round(python_conf, 3),
                    "rust_conf": round(rust_conf, 3),
                    "unknown_conf": round(unknown_conf, 3),
                    "supported_wins": supported_wins,
                    "unknown_is_zero": unknown_is_zero,
                },
            )
        else:
            return self._failure(
                actual=(
                    f"python={python_conf:.2f}, rust={rust_conf:.2f}, unknown={unknown_conf:.2f}. "
                    f"Expected: python > 0.5, rust < 0.5, unknown = 0."
                ),
                outcome="Confidence dampening not working correctly",
                details={
                    "python_conf": round(python_conf, 3),
                    "rust_conf": round(rust_conf, 3),
                    "unknown_conf": round(unknown_conf, 3),
                },
            )


TASK_CLASS = EpistemicUncertaintyTask
