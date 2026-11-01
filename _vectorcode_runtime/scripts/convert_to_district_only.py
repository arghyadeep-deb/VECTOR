"""Convert golden dataset to district-only format for qwen3:8b training.

Simplifies from (district, task_type) pairs to district-only (38 classes).
This avoids the 148-class problem that caused BERT to fail.

Usage:
    python scripts/convert_to_district_only.py
"""
import sys
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def convert_dataset():
    """Convert to district-only format."""
    input_path = Path("data/golden_intent_dataset.jsonl")
    output_path = Path("data/golden_intent_dataset_district_only.jsonl")

    if not input_path.exists():
        logger.error(f"Input dataset not found: {input_path}")
        return False

    # Read input
    examples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            examples.append(json.loads(line))

    logger.info(f"Loaded {len(examples)} examples")

    if not examples:
        logger.error(f"Input dataset is empty: {input_path}")
        return False

    # Convert to district-only
    district_examples = []
    district_counts = defaultdict(int)

    for ex in examples:
        district_examples.append({
            "text": ex["text"],
            "district": ex["district"],
        })
        district_counts[ex["district"]] += 1

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        for ex in district_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    logger.info(f"✅ Converted dataset saved to {output_path}")
    logger.info(f"Total examples: {len(district_examples)}")
    logger.info(f"Unique districts: {len(district_counts)}")
    logger.info(f"Average per district: {len(district_examples) / len(district_counts):.1f}")

    # Show distribution
    print(f"\n{'=' * 70}")
    print("DISTRICT DISTRIBUTION")
    print(f"{'=' * 70}")
    for district in sorted(district_counts.keys()):
        print(f"  {district}: {district_counts[district]} examples")

    return True


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("CONVERT TO DISTRICT-ONLY FORMAT")
    print("=" * 70 + "\n")

    success = convert_dataset()

    if success:
        print("\n" + "=" * 70)
        print("✅ Conversion complete!")
        print("=" * 70)
        print("\nNext: Train qwen3:8b with district-only format")
        print("Command: python core/city/intent_qwen3_8b.py --train --dataset data/golden_intent_dataset_district_only.jsonl")
    else:
        print("\n❌ Conversion failed")
        sys.exit(1)
