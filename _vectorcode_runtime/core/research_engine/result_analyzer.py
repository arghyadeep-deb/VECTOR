"""Result analyzer — statistical analysis and plot generation for experiments."""

import math
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger

from .models import ExperimentResult, AnalysisResult


class ResultAnalyzer:
    def __init__(self, plot_dir: Optional[Path] = None):
        self.plot_dir = plot_dir
        self._scipy: Optional[object] = None
        self._numpy: Optional[object] = None
        self._matplotlib: Optional[object] = None
        self._load_libraries()

    def _load_libraries(self) -> None:
        try:
            import numpy
            self._numpy = numpy
        except ImportError:
            logger.warning("numpy not available — stats will be limited")
        try:
            import scipy.stats as sp_stats
            self._scipy = sp_stats
        except ImportError:
            logger.warning("scipy not available — using numpy-based stats")
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            self._matplotlib = plt
        except Exception as exc:
            logger.warning("matplotlib not available - plots disabled: {}", exc)

    def analyze(self, experiment_result: ExperimentResult) -> AnalysisResult:
        exp_id = experiment_result.experiment_id
        logger.info("Analyzing experiment {}", exp_id)

        data = self._flatten_data(experiment_result.raw_data)
        stats = self._basic_stats(data)
        tests = []

        significance = 0.0
        effect_size = 0.0

        if len(data) >= 4:
            t_result = self._ttest(data)
            if t_result:
                tests.append(t_result)
                significance = t_result.get("p_value", 1.0)
                effect_size = t_result.get("effect_size", 0.0)

            corr_result = self._correlation(data)
            if corr_result:
                tests.append(corr_result)
        else:
            logger.info("Insufficient data points ({}) for statistical tests", len(data))

        interpretation = self._interpret(significance, effect_size, len(tests))
        supports_hypothesis = significance < 0.05 and effect_size >= 0.2

        plots = self._generate_plots(experiment_result, data)

        return AnalysisResult(
            experiment_id=exp_id,
            statistical_tests=tests,
            significance=significance,
            effect_size=effect_size,
            interpretation=interpretation,
            supports_hypothesis=supports_hypothesis,
        )

    def _flatten_data(self, raw_data: list[dict]) -> list[float]:
        values: list[float] = []
        for record in raw_data:
            self._extract_numeric(record, values)
        return values

    def _extract_numeric(self, obj: object, acc: list[float]) -> None:
        if isinstance(obj, (int, float)):
            acc.append(float(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                self._extract_numeric(v, acc)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                self._extract_numeric(item, acc)
        elif isinstance(obj, str):
            try:
                acc.append(float(obj))
            except (ValueError, TypeError):
                logger.warning("[VECTOR] suppressed exception", exc_info=True)

    def _basic_stats(self, data: list[float]) -> dict:
        if not data:
            return {"mean": 0, "std": 0, "min": 0, "max": 0, "count": 0, "median": 0}
        n = len(data)
        mean = sum(data) / n
        variance = sum((x - mean) ** 2 for x in data) / n
        std = math.sqrt(variance)
        sorted_data = sorted(data)
        median = sorted_data[n // 2] if n % 2 else (sorted_data[n // 2 - 1] + sorted_data[n // 2]) / 2
        return {
            "mean": round(mean, 6),
            "std": round(std, 6),
            "min": round(min(data), 6),
            "max": round(max(data), 6),
            "count": n,
            "median": round(median, 6),
        }

    def _ttest(self, data: list[float]) -> Optional[dict]:
        if len(data) < 4:
            return None
        try:
            mid = len(data) // 2
            group_a = data[:mid]
            group_b = data[mid:]
            n1, n2 = len(group_a), len(group_b)
            mean_a = sum(group_a) / n1
            mean_b = sum(group_b) / n2
            s1 = self._stddev(group_a)
            s2 = self._stddev(group_b)
            pooled = math.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2)) if n1 + n2 > 2 else 0

            if self._scipy:
                raw = self._scipy.ttest_ind(group_a, group_b)
                t_stat = getattr(raw, "statistic", raw[0] if isinstance(raw, tuple) else raw)
                p_val = getattr(raw, "pvalue", raw[1] if isinstance(raw, tuple) and len(raw) > 1 else 1.0)
            else:
                denom = pooled * math.sqrt(1 / n1 + 1 / n2)
                t_stat = 0.0 if denom == 0 else (mean_a - mean_b) / denom
                # Normal approximation keeps the fallback deterministic without scipy.
                p_val = math.erfc(abs(float(t_stat)) / math.sqrt(2))

            cohens_d = 0.0 if pooled == 0 else abs(mean_b - mean_a) / pooled
            return {
                "test": "independent_t_test",
                "t_statistic": round(float(t_stat), 6),
                "p_value": round(float(p_val), 6),
                "effect_size": round(float(cohens_d), 6),
                "df": n1 + n2 - 2,
            }
        except Exception as exc:
            logger.warning("t-test failed: {}", exc)
        return None

    def _stddev(self, data: list[float]) -> float:
        if len(data) < 2:
            return 0.0
        if self._numpy:
            return float(self._numpy.std(data, ddof=1))
        mean = sum(data) / len(data)
        return math.sqrt(sum((x - mean) ** 2 for x in data) / (len(data) - 1))

    def _correlation(self, data: list[float]) -> Optional[dict]:
        if self._scipy and len(data) >= 6:
            try:
                x = list(range(len(data)))
                r, p = self._scipy.pearsonr(x, data)
                return {
                    "test": "pearson_correlation",
                    "r": round(float(r), 6),
                    "p_value": round(float(p), 6),
                    "n": len(data),
                }
            except Exception as exc:
                logger.warning("correlation failed: {}", exc)
        return None

    def _interpret(self, significance: float, effect_size: float, num_tests: int) -> str:
        parts = []
        if significance < 0.001:
            parts.append("Highly significant result (p < 0.001)")
        elif significance < 0.01:
            parts.append("Very significant result (p < 0.01)")
        elif significance < 0.05:
            parts.append("Significant result (p < 0.05)")
        else:
            parts.append(f"Not statistically significant (p = {significance:.4f})")

        if effect_size >= 0.8:
            parts.append("Large effect size")
        elif effect_size >= 0.5:
            parts.append("Medium effect size")
        elif effect_size >= 0.2:
            parts.append("Small effect size")
        else:
            parts.append("Negligible effect size")

        parts.append(f"Based on {num_tests} statistical test(s)")
        return " — ".join(parts)

    def _generate_plots(self, result: ExperimentResult, data: list[float]) -> list[str]:
        if self._matplotlib is None:
            return result.plots or []

        plt = self._matplotlib
        plot_dir = self.plot_dir or Path(tempfile.mkdtemp(prefix="vector_plots_"))
        plot_dir.mkdir(parents=True, exist_ok=True)

        generated: list[str] = []

        if data:
            try:
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.hist(data, bins=min(30, max(10, len(data) // 5)), edgecolor="black", alpha=0.7)
                ax.set_xlabel("Value")
                ax.set_ylabel("Frequency")
                ax.set_title(f"Histogram — {result.experiment_id}")
                path = str(plot_dir / "histogram.png")
                fig.savefig(path, dpi=100, bbox_inches="tight")
                plt.close(fig)
                generated.append(path)
            except Exception as exc:
                logger.warning("Histogram generation failed: {}", exc)

        if len(data) >= 4:
            try:
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.boxplot(data, vert=True)
                ax.set_ylabel("Value")
                ax.set_title(f"Box Plot — {result.experiment_id}")
                path = str(plot_dir / "boxplot.png")
                fig.savefig(path, dpi=100, bbox_inches="tight")
                plt.close(fig)
                generated.append(path)
            except Exception as exc:
                logger.warning("Box plot generation failed: {}", exc)

        if len(data) >= 6:
            try:
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.scatter(list(range(len(data))), data, alpha=0.6)
                ax.set_xlabel("Index")
                ax.set_ylabel("Value")
                ax.set_title(f"Scatter Plot — {result.experiment_id}")
                path = str(plot_dir / "scatter.png")
                fig.savefig(path, dpi=100, bbox_inches="tight")
                plt.close(fig)
                generated.append(path)
            except Exception as exc:
                logger.warning("Scatter plot generation failed: {}", exc)

        return generated
