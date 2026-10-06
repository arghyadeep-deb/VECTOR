"""Run real LoRA training for intent classification.

Sets VECTOR_TRAINING_REAL=1 to enable actual training (not simulation).

Usage:
    python scripts/train_intent_real.py
"""
import os
import sys
from pathlib import Path

# Enable real training
os.environ["VECTOR_TRAINING_REAL"] = "1"

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def train_real():
    """Run real LoRA training."""
    print("\n" + "=" * 70)
    print("REAL LORA TRAINING FOR INTENT CLASSIFICATION")
    print("=" * 70 + "\n")

    # Check prerequisites
    try:
        import torch
        print(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"GPU: {torch.cuda.get_device_name(0)}")
    except ImportError:
        print("ERROR: torch not installed")
        return False

    try:
        import peft
        print(f"PEFT version: {peft.__version__}")
    except ImportError:
        print("ERROR: PEFT not installed. Run: pip install peft transformers")
        return False

    try:
        import transformers
        print(f"Transformers version: {transformers.__version__}")
    except ImportError:
        print("ERROR: transformers not installed. Run: pip install transformers")
        return False

    print("\n" + "=" * 70)
    print("Starting real training...")
    print("=" * 70 + "\n")

    # Import and train
    from core.city.intent_qwen3_8b import IntentQwen3_8B

    classifier = IntentQwen3_8B()
    dataset_path = Path(__file__).resolve().parent.parent / "data" / "golden_intent_dataset_district_only.jsonl"
    classifier.train(dataset_path=str(dataset_path))

    print("\n" + "=" * 70)
    print("Training complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Evaluate: python core/city/intent_qwen3_8b.py --evaluate")
    print("2. Integrate: python scripts/integrate_intent_qwen3.py")
    print("3. Test: python scripts/diag_tier6.py")

    return True


if __name__ == "__main__":
    success = train_real()
    sys.exit(0 if success else 1)
