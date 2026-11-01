"""
AdsScorer — weighted ads performance scorer.

Converts raw campaign metrics (CTR, conversion rate, ROAS, quality score)
into a unified 0-100 score with letter grade (A/B/C/D).

Usage:
    scorer = AdsScorer()
    score = scorer.score({"ctr": 0.05, "conversion_rate": 0.03, "roas": 4.0, "quality_score": 8.0})
    grade = scorer.grade(score)
"""

import sys

# Ensure codebase root is first in sys.path so CONFIG resolves to the real dict,
# not vectorcode/src/core/config.py (VectorConfig).

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

class AdsScorer:
    """Weighted ads performance scorer — converts raw metrics to 0-100 score."""

    WEIGHTS = {
        "ctr": 0.25,
        "conversion_rate": 0.30,
        "roas": 0.25,
        "quality_score": 0.20,
    }

    def score(self, metrics: dict) -> float:
        """Returns 0-100 score for an ad campaign.

        Each metric is normalised against its benchmark (capped at 1.0),
        multiplied by its weight, and summed to produce the final score.

        Args:
            metrics: dict with any subset of ctr, conversion_rate, roas, quality_score.
                     Missing keys default to 0.0.

        Returns:
            float in [0.0, 100.0].
        """
        total = 0.0
        for metric, weight in self.WEIGHTS.items():
            val = float(metrics.get(metric, 0.0))
            if val < 0:
                logger.warning("[VECTOR][ads_scorer] negative value for '{}': {}", metric, val)
                val = 0.0
            normalized = min(val / self._benchmark(metric), 1.0)
            total += normalized * weight * 100
        result = round(total, 1)
        logger.debug("[VECTOR][ads_scorer] score={} metrics={}", result, metrics)
        return result

    def _benchmark(self, metric: str) -> float:
        """Return the industry-benchmark value for a metric (denominator for normalisation)."""
        benchmarks = {
            "ctr": 0.05,              # 5% CTR is excellent
            "conversion_rate": 0.03,  # 3% CVR is excellent
            "roas": 4.0,              # 4x ROAS is excellent
            "quality_score": 8.0,     # Google Quality Score 8/10 is excellent
        }
        return benchmarks.get(metric, 1.0)

    def grade(self, score: float) -> str:
        """Convert a 0-100 numeric score to a letter grade (A/B/C/D)."""
        if score >= 80:
            return "A"
        if score >= 60:
            return "B"
        if score >= 40:
            return "C"
        return "D"

    def score_and_grade(self, metrics: dict) -> dict:
        """Convenience method — returns both score and grade in one call."""
        s = self.score(metrics)
        return {"score": s, "grade": self.grade(s)}

if __name__ == "__main__":
    s = AdsScorer()
    test_metrics = {"ctr": 0.03, "conversion_rate": 0.02, "roas": 3.0, "quality_score": 7.0}
    result = s.score(test_metrics)
    grade = s.grade(result)
    print(f"AdsScorer OK: score={result} grade={grade}")
    assert 0.0 <= result <= 100.0, f"Score out of range: {result}"
    assert grade in ("A", "B", "C", "D"), f"Invalid grade: {grade}"
    # Verify perfect metrics → 100.0
    perfect = {"ctr": 0.05, "conversion_rate": 0.03, "roas": 4.0, "quality_score": 8.0}
    assert s.score(perfect) == 100.0, f"Perfect score should be 100.0, got {s.score(perfect)}"
    # Verify zero metrics → 0.0
    assert s.score({}) == 0.0, "Empty metrics should score 0.0"
    print("All assertions passed.")
