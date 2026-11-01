"""Execute complete intent classification pipeline.

Runs: augment → train → integrate → test

Usage:
    python scripts/execute_intent_pipeline.py
"""
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def run_command(cmd: str, description: str) -> bool:
    """Run a command and report results."""
    print(f"\n{'=' * 70}")
    print(f"STEP: {description}")
    print(f"{'=' * 70}\n")
    print(f"Running: {cmd}\n")

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )

        print(result.stdout)

        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print(f"\n✅ {description} complete")
            return True
        else:
            print(f"\n❌ {description} failed (exit code {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n❌ {description} timed out (>1 hour)")
        return False
    except Exception as e:
        print(f"\n❌ {description} error: {e}")
        return False


def main():
    """Execute the complete pipeline."""
    print("\n" + "=" * 70)
    print("INTENT CLASSIFICATION PIPELINE")
    print("=" * 70)
    print("\nThis will:")
    print("1. Augment dataset (3000+ examples using qwen3:8b)")
    print("2. Fine-tune qwen3:8b with LoRA (1-2 hours)")
    print("3. Integrate into governor pipeline")
    print("4. Test accuracy")
    print("\nEstimated time: 2-3 hours total")
    print("=" * 70 + "\n")

    steps = [
        (
            "python scripts/augment_intent_dataset.py",
            "Augment dataset (generate 3000+ examples)",
        ),
        (
            "python core/city/intent_qwen3_8b.py --train",
            "Fine-tune qwen3:8b with LoRA",
        ),
        (
            "python scripts/integrate_intent_qwen3.py",
            "Integrate into governor pipeline",
        ),
        (
            "python core/city/intent_qwen3_8b.py --evaluate",
            "Evaluate accuracy",
        ),
        (
            "python scripts/diag_tier6.py",
            "Integration test (full pipeline)",
        ),
    ]

    results = []
    for cmd, description in steps:
        success = run_command(cmd, description)
        results.append((description, success))

        if not success:
            print(f"\n❌ Pipeline failed at: {description}")
            print("\nStopping execution. Fix the issue and re-run.")
            return False

    # Final report
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print("\nResults:")
    for description, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {description}")

    print("\n" + "=" * 70)
    print("SUCCESS! Intent classification integrated into VECTOR governor.")
    print("=" * 70)

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
