"""Intent classification performance monitor.

Tracks accuracy over time, detects degradation, collects misclassified examples.

Usage:
    from core.city.intent_monitor import IntentMonitor
    monitor = IntentMonitor()
    monitor.log_classification(text, predicted, actual, confidence)
    stats = monitor.get_stats()
"""
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from loguru import logger

__all__ = ["IntentMonitor"]


class IntentMonitor:
    """Monitor intent classification performance."""

    def __init__(self, stats_path: str = "data/intent_classification_stats.json"):
        """Initialize monitor.

        Args:
            stats_path: Path to stats file.
        """
        self._stats_path = Path(stats_path)
        self._stats = self._load_stats()

    def _load_stats(self) -> dict:
        """Load stats from file."""
        if self._stats_path.exists():
            try:
                return json.loads(self._stats_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"[IntentMonitor] Failed to load stats: {e}")

        return {
            "total_classifications": 0,
            "correct_classifications": 0,
            "incorrect_classifications": 0,
            "accuracy_history": [],  # List of (timestamp, accuracy) tuples
            "district_counts": defaultdict(int),
            "misclassified_examples": [],  # List of {text, predicted, actual, timestamp}
            "last_updated": None,
        }

    def _save_stats(self) -> None:
        """Save stats to file."""
        try:
            self._stats_path.parent.mkdir(parents=True, exist_ok=True)
            self._stats["last_updated"] = datetime.now().isoformat()
            self._stats_path.write_text(
                json.dumps(self._stats, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"[IntentMonitor] Failed to save stats: {e}")

    def log_classification(
        self,
        text: str,
        predicted_district: str,
        actual_district: Optional[str],
        confidence: float,
        source: str = "unknown"
    ) -> None:
        """Log a classification result.

        Args:
            text: User query text.
            predicted_district: Predicted district.
            actual_district: Actual district (if known, None otherwise).
            confidence: Classification confidence (0-1).
            source: Classification source (regex, embedding, qwen3, llm).
        """
        self._stats["total_classifications"] += 1
        self._stats["district_counts"][predicted_district] += 1

        # If we know the actual district, check correctness
        if actual_district is not None:
            if predicted_district == actual_district:
                self._stats["correct_classifications"] += 1
            else:
                self._stats["incorrect_classifications"] += 1

                # Log misclassified example
                self._stats["misclassified_examples"].append({
                    "text": text,
                    "predicted": predicted_district,
                    "actual": actual_district,
                    "confidence": confidence,
                    "source": source,
                    "timestamp": datetime.now().isoformat(),
                })

                # Keep only last 1000 misclassified examples
                if len(self._stats["misclassified_examples"]) > 1000:
                    self._stats["misclassified_examples"] = self._stats["misclassified_examples"][-1000:]

        # Update accuracy history (every 100 classifications)
        if self._stats["total_classifications"] % 100 == 0:
            accuracy = self.get_accuracy()
            self._stats["accuracy_history"].append({
                "timestamp": datetime.now().isoformat(),
                "accuracy": accuracy,
                "total": self._stats["total_classifications"],
            })

            # Keep only last 1000 history entries
            if len(self._stats["accuracy_history"]) > 1000:
                self._stats["accuracy_history"] = self._stats["accuracy_history"][-1000:]

        self._save_stats()

    def get_accuracy(self) -> float:
        """Get current accuracy.

        Returns:
            Accuracy (0-1), or 0.0 if no classifications with known actual.
        """
        total = self._stats["correct_classifications"] + self._stats["incorrect_classifications"]
        if total == 0:
            return 0.0
        return self._stats["correct_classifications"] / total

    def get_stats(self) -> dict:
        """Get comprehensive stats.

        Returns:
            Dict with all statistics.
        """
        return {
            "total_classifications": self._stats["total_classifications"],
            "correct": self._stats["correct_classifications"],
            "incorrect": self._stats["incorrect_classifications"],
            "accuracy": self.get_accuracy(),
            "accuracy_history": self._stats["accuracy_history"][-10:],  # Last 10 entries
            "district_counts": dict(self._stats["district_counts"]),
            "misclassified_count": len(self._stats["misclassified_examples"]),
            "last_updated": self._stats["last_updated"],
        }

    def check_degradation(self, threshold: float = 0.90) -> bool:
        """Check if accuracy has degraded below threshold.

        Args:
            threshold: Minimum acceptable accuracy.

        Returns:
            True if accuracy is below threshold (needs retraining).
        """
        accuracy = self.get_accuracy()
        if accuracy == 0.0:
            return False  # Not enough data
        return accuracy < threshold

    def get_misclassified_examples(self, limit: int = 100) -> list[dict]:
        """Get recent misclassified examples.

        Args:
            limit: Maximum number of examples to return.

        Returns:
            List of misclassified examples.
        """
        return self._stats["misclassified_examples"][-limit:]

    def export_for_retraining(self, output_path: str = "data/misclassified_for_retraining.jsonl") -> int:
        """Export misclassified examples for retraining.

        Args:
            output_path: Output file path.

        Returns:
            Number of examples exported.
        """
        examples = self._stats["misclassified_examples"]
        if not examples:
            logger.info("[IntentMonitor] No misclassified examples to export")
            return 0

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps({
                    "text": ex["text"],
                    "district": ex["actual"],  # Use actual district for training
                }, ensure_ascii=False) + "\n")

        logger.info(f"[IntentMonitor] Exported {len(examples)} misclassified examples to {output_path}")
        return len(examples)

    def reset(self) -> None:
        """Reset all stats."""
        self._stats = {
            "total_classifications": 0,
            "correct_classifications": 0,
            "incorrect_classifications": 0,
            "accuracy_history": [],
            "district_counts": defaultdict(int),
            "misclassified_examples": [],
            "last_updated": None,
        }
        self._save_stats()
        logger.info("[IntentMonitor] Stats reset")


if __name__ == "__main__":
    """Test IntentMonitor."""
    print("\n=== IntentMonitor Test ===\n")

    monitor = IntentMonitor()

    # Log some classifications
    monitor.log_classification("quiz me on french", "languages", "languages", 0.95, "embedding")
    monitor.log_classification("help me scope startup", "startups", "startups", 0.88, "qwen3")
    monitor.log_classification("review my code", "coding", "coding", 0.92, "regex")
    monitor.log_classification("what are my goals", "brain", "brain", 0.90, "embedding")

    # Log a misclassification
    monitor.log_classification("track my sleep", "health", "health", 0.75, "llm")
    monitor.log_classification("track my sleep", "reflection", "health", 0.65, "embedding")  # Wrong!

    # Get stats
    stats = monitor.get_stats()
    print(f"Total classifications: {stats['total_classifications']}")
    print(f"Accuracy: {stats['accuracy']:.2%}")
    print(f"Correct: {stats['correct']}")
    print(f"Incorrect: {stats['incorrect']}")
    print(f"Misclassified: {stats['misclassified_count']}")

    # Check degradation
    needs_retrain = monitor.check_degradation(threshold=0.90)
    print(f"\nNeeds retraining (accuracy < 90%): {needs_retrain}")

    # Get misclassified examples
    misclassified = monitor.get_misclassified_examples(limit=5)
    print(f"\nRecent misclassified examples:")
    for ex in misclassified:
        print(f"  - '{ex['text']}' -> predicted: {ex['predicted']}, actual: {ex['actual']}")

    print("\n✅ IntentMonitor test complete")
