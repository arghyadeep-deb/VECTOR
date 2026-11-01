"""Automated retraining pipeline for intent classification.

Monitors accuracy and triggers retraining when degradation detected.

Usage:
    python scripts/auto_retrain_intent.py
    python scripts/auto_retrain_intent.py --check-only
    python scripts/auto_retrain_intent.py --threshold 0.90
"""
import os
import sys
import argparse
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from core.city.intent_monitor import IntentMonitor


def check_accuracy(threshold: float = 0.90) -> dict:
    """Check current accuracy and determine if retraining needed.

    Args:
        threshold: Minimum acceptable accuracy.

    Returns:
        Dict with status and recommendations.
    """
    monitor = IntentMonitor()
    stats = monitor.get_stats()

    accuracy = stats["accuracy"]
    total = stats["total_classifications"]
    misclassified_count = stats["misclassified_count"]

    result = {
        "accuracy": accuracy,
        "total_classifications": total,
        "misclassified_count": misclassified_count,
        "needs_retraining": False,
        "recommendation": "No action needed",
    }

    if total < 100:
        result["recommendation"] = f"Not enough data ({total} classifications). Need at least 100 to assess accuracy."
        return result

    if accuracy < threshold:
        result["needs_retraining"] = True
        result["recommendation"] = f"Accuracy {accuracy:.2%} below threshold {threshold:.2%}. Retraining recommended."

    return result


def export_misclassified_examples() -> int:
    """Export misclassified examples for retraining.

    Returns:
        Number of examples exported.
    """
    monitor = IntentMonitor()
    count = monitor.export_for_retraining(
        output_path="data/misclassified_for_retraining.jsonl"
    )
    return count


def merge_datasets():
    """Merge original dataset with misclassified examples.

    Creates combined dataset for retraining.
    """
    original_path = Path("data/golden_intent_dataset_district_only.jsonl")
    misclassified_path = Path("data/misclassified_for_retraining.jsonl")
    combined_path = Path("data/golden_intent_dataset_combined.jsonl")

    if not original_path.exists():
        logger.error(f"[AutoRetrain] Original dataset not found: {original_path}")
        return False

    # Read original dataset
    original_examples = []
    with open(original_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                original_examples.append(line.strip())

    # Read misclassified examples if they exist
    misclassified_examples = []
    if misclassified_path.exists():
        with open(misclassified_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    misclassified_examples.append(line.strip())

    # Combine (deduplicate by text)
    seen_texts = set()
    combined_examples = []

    for example in original_examples + misclassified_examples:
        import json
        try:
            data = json.loads(example)
            text = data.get("text", "")
            if text not in seen_texts:
                seen_texts.add(text)
                combined_examples.append(example)
        except Exception as e:
            logger.warning(f"[AutoRetrain] Failed to parse example: {e}")
            continue

    # Write combined dataset
    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=combined_path.parent,
            prefix=f".{combined_path.name}.", suffix=".tmp", delete=False,
        ) as f:
            tmp_name = f.name
            f.write("\n".join(combined_examples) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, combined_path)
        tmp_name = None
    finally:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)

    logger.info(f"[AutoRetrain] Combined dataset: {len(combined_examples)} examples ({len(original_examples)} original + {len(misclassified_examples)} misclassified)")
    return True


def retrain_model(dataset_path: str = "data/golden_intent_dataset_combined.jsonl"):
    """Trigger model retraining.

    Args:
        dataset_path: Path to training dataset.

    Returns:
        True if training succeeded.
    """
    logger.info(f"[AutoRetrain] Starting retraining with dataset: {dataset_path}")

    # Set environment variable for real training
    os.environ["VECTOR_TRAINING_REAL"] = "1"

    try:
        from core.city.intent_qwen3_8b import IntentQwen3_8B

        classifier = IntentQwen3_8B()
        classifier.train(dataset_path=dataset_path)

        logger.info("[AutoRetrain] Retraining complete")
        return True

    except Exception as e:
        logger.error(f"[AutoRetrain] Retraining failed: {e}")
        return False


def reset_monitor():
    """Reset monitor stats after successful retraining."""
    monitor = IntentMonitor()
    monitor.reset()
    logger.info("[AutoRetrain] Monitor stats reset")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Automated intent classification retraining")
    parser.add_argument("--check-only", action="store_true", help="Only check accuracy, don't retrain")
    parser.add_argument("--threshold", type=float, default=0.90, help="Accuracy threshold (default: 0.90)")
    parser.add_argument("--force-retrain", action="store_true", help="Force retraining regardless of accuracy")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("AUTOMATED INTENT CLASSIFICATION RETRAINING PIPELINE")
    print("=" * 70 + "\n")

    # Step 1: Check accuracy
    print("Step 1: Checking accuracy...")
    status = check_accuracy(threshold=args.threshold)
    print(f"  Current accuracy: {status['accuracy']:.2%}")
    print(f"  Total classifications: {status['total_classifications']}")
    print(f"  Misclassified examples: {status['misclassified_count']}")
    print(f"  Recommendation: {status['recommendation']}")
    print()

    if args.check_only:
        print("Check-only mode. Exiting.")
        return 0

    # Step 2: Determine if retraining needed
    needs_retrain = status["needs_retraining"] or args.force_retrain

    if not needs_retrain:
        print("✅ Accuracy is acceptable. No retraining needed.")
        return 0

    print("⚠️  Retraining recommended. Proceeding with pipeline...")
    print()

    # Step 3: Export misclassified examples
    print("Step 2: Exporting misclassified examples...")
    exported_count = export_misclassified_examples()
    print(f"  Exported {exported_count} misclassified examples")
    print()

    if exported_count == 0:
        print("No misclassified examples to retrain on. Using original dataset only.")
        dataset_path = "data/golden_intent_dataset_district_only.jsonl"
    else:
        # Step 4: Merge datasets
        print("Step 3: Merging datasets...")
        if not merge_datasets():
            print("❌ Failed to merge datasets")
            return 1
        dataset_path = "data/golden_intent_dataset_combined.jsonl"
        print()

    # Step 5: Retrain model
    print("Step 4: Retraining model...")
    print(f"  Dataset: {dataset_path}")
    print(f"  Expected time: 30-60 minutes")
    print()

    if not retrain_model(dataset_path=dataset_path):
        print("❌ Retraining failed")
        return 1

    print("✅ Retraining complete")
    print()

    # Step 6: Reset monitor
    print("Step 5: Resetting monitor stats...")
    reset_monitor()
    print()

    print("=" * 70)
    print("✅ RETRAINING PIPELINE COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Evaluate accuracy: python core/city/intent_qwen3_8b.py --evaluate")
    print("2. Test integration: python scripts/diag_tier6.py")
    print("3. Monitor will start collecting new statistics")

    return 0


if __name__ == "__main__":
    success = main()
    sys.exit(success)
