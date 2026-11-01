"""Calibrate intent matcher similarity threshold.

Tests different thresholds (0.80-0.90) against the eval dataset to find
the optimal balance between precision and recall.

Usage:
    python scripts/calibrate_intent_threshold.py
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.intent_matcher import IntentMatcher


# Test queries with expected districts (from diag_tier6.py)
TEST_QUERIES = [
    {"text": "quiz me on french vocabulary", "district": "languages", "task_type": "quiz_vocabulary"},
    {"text": "help me scope a startup idea", "district": "startups", "task_type": "idea_validation"},
    {"text": "what are my current goals", "district": "brain", "task_type": "goal_summary"},
    {"text": "study transformers with me for 30 minutes", "district": "karpathy_lab", "task_type": "study_session"},
    {"text": "sketch a settings screen layout", "district": "design", "task_type": "sketch_layout"},
    {"text": "generate a performance report", "district": "data_analytics", "task_type": "generate_report"},
    {"text": "analyze my habit patterns", "district": "pattern_detective", "task_type": "habit_analysis"},
    {"text": "do a weekly review", "district": "reflection", "task_type": "weekly_review"},
    {"text": "check if everything is running smoothly", "district": "ops", "task_type": "system_status"},
    {"text": "track my sleep last night", "district": "health", "task_type": "track_sleep"},
]

# Generalization queries (novel, not in training set)
GENERALIZATION_QUERIES = [
    {"text": "help me practice spanish", "district": "languages", "task_type": "quiz_vocabulary"},
    {"text": "validate my saas idea", "district": "startups", "task_type": "idea_validation"},
    {"text": "whats my main goal right now", "district": "brain", "task_type": "goal_summary"},
    {"text": "lets study neural networks", "district": "karpathy_lab", "task_type": "study_session"},
    {"text": "design a login page mockup", "district": "design", "task_type": "sketch_layout"},
]


async def calibrate_threshold(matcher: IntentMatcher, threshold: float, queries: list[dict]) -> dict:
    """Test a specific threshold against queries.

    Returns:
        {"correct": int, "total": int, "accuracy": float, "results": list}
    """
    matcher.set_threshold(threshold)
    correct = 0
    results = []

    for query in queries:
        result = await matcher.match(query["text"])
        matched = (
            result is not None
            and result["district"] == query["district"]
            and result["type"] == query["task_type"]
        )
        if matched:
            correct += 1
        results.append({
            "query": query["text"],
            "expected": f"{query['district']}/{query['task_type']}",
            "got": f"{result['district']}/{result['type']}" if result else "None",
            "confidence": result["confidence"] if result else 0.0,
            "correct": matched,
        })

    return {
        "correct": correct,
        "total": len(queries),
        "accuracy": correct / len(queries) if queries else 0.0,
        "results": results,
    }


async def main():
    """Run calibration across multiple thresholds."""
    print("\n" + "=" * 70)
    print("INTENT MATCHER THRESHOLD CALIBRATION")
    print("=" * 70 + "\n")

    matcher = IntentMatcher("data/intent_examples.json")
    thresholds = [0.80, 0.82, 0.85, 0.87, 0.90]

    print(f"Loaded {len(matcher._examples)} example queries\n")
    print(f"Testing {len(TEST_QUERIES)} original eval queries")
    print(f"Testing {len(GENERALIZATION_QUERIES)} generalization queries\n")

    # Test original eval set
    print("ORIGINAL EVAL SET:")
    print("-" * 70)
    for threshold in thresholds:
        result = await calibrate_threshold(matcher, threshold, TEST_QUERIES)
        print(f"  Threshold {threshold:.2f}: {result['correct']}/{result['total']} "
              f"({result['accuracy']:.1%})")

    print("\nGENERALIZATION SET:")
    print("-" * 70)
    for threshold in thresholds:
        result = await calibrate_threshold(matcher, threshold, GENERALIZATION_QUERIES)
        print(f"  Threshold {threshold:.2f}: {result['correct']}/{result['total']} "
              f"({result['accuracy']:.1%})")

    # Combined analysis
    print("\nCOMBINED ANALYSIS:")
    print("-" * 70)
    all_queries = TEST_QUERIES + GENERALIZATION_QUERIES
    for threshold in thresholds:
        result = await calibrate_threshold(matcher, threshold, all_queries)
        print(f"  Threshold {threshold:.2f}: {result['correct']}/{result['total']} "
              f"({result['accuracy']:.1%})")

    # Recommendation
    print("\nRECOMMENDATION:")
    print("-" * 70)
    print("  Threshold 0.85 is the default — good balance of precision/recall.")
    print("  Lower (0.80-0.82): More matches, but risk of false positives.")
    print("  Higher (0.87-0.90): Fewer false positives, but may miss valid matches.")
    print("  Adjust based on observed false positive rate in production.")

    # Detailed results for optimal threshold
    print("\nDETAILED RESULTS (threshold=0.85):")
    print("-" * 70)
    matcher.set_threshold(0.85)
    for query in all_queries:
        result = await matcher.match(query["text"])
        expected = f"{query['district']}/{query['task_type']}"
        got = f"{result['district']}/{result['type']}" if result else "None"
        conf = result["confidence"] if result else 0.0
        status = "OK" if result and result["district"] == query["district"] else "FAIL"
        print(f"  {status} {query['text']!r}")
        print(f"     Expected: {expected} | Got: {got} (conf={conf:.3f})")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
