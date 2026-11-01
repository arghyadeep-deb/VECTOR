from __future__ import annotations

import datetime
import math
from collections import defaultdict
from typing import Any

from loguru import logger

from districts.health.metrics_store import MetricsStore


class TrendAnalyzer:
    def __init__(self, store: MetricsStore | None = None, anomaly_threshold: float = 2.0) -> None:
        self._store = store or MetricsStore()
        self._anomaly_threshold = anomaly_threshold

    def _fetch_values(self, metric_name: str, days: int) -> list[float]:
        rows = self._store.get_metrics(metric_name, days=days)
        return [r["value"] for r in rows if r["value"] is not None]

    def _stats(self, values: list[float]) -> dict[str, float]:
        if not values:
            return {"avg": 0.0, "min": 0.0, "max": 0.0, "std_dev": 0.0}
        n = len(values)
        avg = sum(values) / n
        variance = sum((v - avg) ** 2 for v in values) / n
        std_dev = math.sqrt(variance)
        return {"avg": avg, "min": min(values), "max": max(values), "std_dev": std_dev}

    def analyze(self, metric_name: str, days: int = 7) -> dict[str, Any]:
        values = self._fetch_values(metric_name, days)
        stats = self._stats(values)
        if len(values) < 2:
            return {
                "metric_name": metric_name,
                "direction": "stable",
                "change_pct": 0.0,
                "avg": round(stats["avg"], 2),
                "min": round(stats["min"], 2),
                "max": round(stats["max"], 2),
                "std_dev": round(stats["std_dev"], 2),
                "baseline_7d_mean": round(stats["avg"], 2),
                "baseline_7d_std": round(stats["std_dev"], 2),
                "baseline_30d_mean": 0.0,
                "baseline_30d_std": 0.0,
                "delta_7d_pct": 0.0,
                "delta_30d_pct": 0.0,
                "stability": "insufficient_data",
            }
        mid = len(values) // 2
        first_half = sum(values[:mid]) / mid if mid > 0 else stats["avg"]
        second_half = sum(values[mid:]) / (len(values) - mid) if (len(values) - mid) > 0 else stats["avg"]

        change_pct = 0.0
        if abs(first_half) > 0.001:
            change_pct = ((second_half - first_half) / abs(first_half)) * 100.0

        direction = "stable"
        if abs(change_pct) > 5.0:
            direction = "improving" if change_pct > 0 else "declining"

        stability = "stable"
        cv = stats["std_dev"] / abs(stats["avg"]) if abs(stats["avg"]) > 0.001 else 0.0
        if cv > 0.5:
            stability = "volatile"
        elif cv > 0.25:
            stability = "variable"

        vals_30d = self._fetch_values(metric_name, 30)
        stats_30d = self._stats(vals_30d) if vals_30d else stats

        delta_7d = 0.0
        if abs(stats_30d["avg"]) > 0.001:
            delta_7d = ((stats["avg"] - stats_30d["avg"]) / abs(stats_30d["avg"])) * 100.0

        vals_old_30d = self._fetch_values(metric_name, 60)
        delta_30d = 0.0
        if len(vals_old_30d) > 0 and abs(sum(vals_old_30d) / len(vals_old_30d)) > 0.001:
            old_avg = sum(vals_old_30d) / len(vals_old_30d)
            delta_30d = ((stats_30d["avg"] - old_avg) / abs(old_avg)) * 100.0

        return {
            "metric_name": metric_name,
            "direction": direction,
            "change_pct": round(change_pct, 2),
            "avg": round(stats["avg"], 2),
            "min": round(stats["min"], 2),
            "max": round(stats["max"], 2),
            "std_dev": round(stats["std_dev"], 2),
            "baseline_7d_mean": round(stats["avg"], 2),
            "baseline_7d_std": round(stats["std_dev"], 2),
            "baseline_30d_mean": round(stats_30d["avg"], 2),
            "baseline_30d_std": round(stats_30d["std_dev"], 2),
            "delta_7d_pct": round(delta_7d, 2),
            "delta_30d_pct": round(delta_30d, 2),
            "stability": stability,
        }

    def detect_anomalies(self, metric_name: str, values: list[float], threshold: float | None = None) -> list[dict[str, Any]]:
        threshold = self._anomaly_threshold if threshold is None else threshold
        if not values:
            return []
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance) if variance > 0 else 1.0
        anomalies: list[dict[str, Any]] = []
        for v in values:
            z = abs(v - mean) / std_dev
            if z > threshold:
                anomalies.append({
                    "metric_name": metric_name,
                    "expected": round(mean, 2),
                    "actual": v,
                    "deviation": round((v - mean) / abs(mean) * 100 if abs(mean) > 0.001 else 0.0, 2),
                    "severity": min(int(z / 5.0 * 10), 10),
                    "detected_at": datetime.datetime.now().isoformat(),
                    "trend_direction": "up" if v > mean else "down",
                    "probable_causes": [],
                })
        return anomalies

    def weekly_comparison(self, metric_name: str) -> dict[str, Any]:
        now = datetime.datetime.now()
        this_week_cutoff = (now - datetime.timedelta(days=7)).isoformat()
        last_week_cutoff = (now - datetime.timedelta(days=14)).isoformat()

        this_rows = self._store.get_metrics(metric_name, days=7)
        last_rows = self._store.get_metrics(metric_name, days=14)

        this_values = [r["value"] for r in this_rows if r["timestamp"] >= this_week_cutoff and r["value"] is not None]
        last_values = [r["value"] for r in last_rows if r["timestamp"] < this_week_cutoff and r["timestamp"] >= last_week_cutoff and r["value"] is not None]

        this_avg = sum(this_values) / len(this_values) if this_values else 0.0
        last_avg = sum(last_values) / len(last_values) if last_values else 0.0

        change_pct = 0.0
        if abs(last_avg) > 0.001:
            change_pct = ((this_avg - last_avg) / abs(last_avg)) * 100.0

        insight = ""
        if abs(change_pct) > 20:
            insight = f"Significant {abs(change_pct):.0f}% {'increase' if change_pct > 0 else 'decrease'} in {metric_name}"
        elif abs(change_pct) > 5:
            insight = f"Slight {'upward' if change_pct > 0 else 'downward'} trend in {metric_name}"
        else:
            insight = f"{metric_name} is stable week-over-week"

        return {
            "metric_name": metric_name,
            "this_week_avg": round(this_avg, 2),
            "last_week_avg": round(last_avg, 2),
            "change_pct": round(change_pct, 2),
            "insight": insight,
        }

    def detect_circadian_patterns(self, metric_name: str, days: int = 7) -> dict[str, Any]:
        rows = self._store.get_metrics(metric_name, days=days)
        hour_buckets: dict[int, list[float]] = defaultdict(list)
        for r in rows:
            try:
                ts = datetime.datetime.fromisoformat(r["timestamp"])
                hour_buckets[ts.hour].append(r["value"])
            except (ValueError, TypeError):
                continue
        if not hour_buckets:
            return {"metric_name": metric_name, "pattern": "unknown", "hourly_averages": {}}

        hourly_avg = {h: round(sum(vals) / len(vals), 2) for h, vals in hour_buckets.items()}
        all_vals = [v for vals in hour_buckets.values() for v in vals]
        global_avg = sum(all_vals) / len(all_vals) if all_vals else 0.0

        peak_hour = max(hourly_avg, key=hourly_avg.get)
        trough_hour = min(hourly_avg, key=hourly_avg.get)
        amplitude = hourly_avg[peak_hour] - hourly_avg[trough_hour]

        return {
            "metric_name": metric_name,
            "pattern": "circadian_detected" if amplitude > global_avg * 0.1 else "flat",
            "hourly_averages": hourly_avg,
            "peak_hour": peak_hour,
            "trough_hour": trough_hour,
            "amplitude": round(amplitude, 2),
        }

    def correlate(self, metric_a: str, metric_b: str) -> float:
        rows_a = self._store.get_metrics(metric_a, days=30)
        rows_b = self._store.get_metrics(metric_b, days=30)
        map_a = {r["timestamp"][:16]: r["value"] for r in rows_a if r["value"] is not None}
        map_b = {r["timestamp"][:16]: r["value"] for r in rows_b if r["value"] is not None}
        shared = [(map_a[k], map_b[k]) for k in map_a if k in map_b]
        if len(shared) < 3:
            return 0.0
        n = len(shared)
        sum_x = sum(p[0] for p in shared)
        sum_y = sum(p[1] for p in shared)
        sum_xy = sum(p[0] * p[1] for p in shared)
        sum_x2 = sum(p[0] ** 2 for p in shared)
        sum_y2 = sum(p[1] ** 2 for p in shared)
        num = n * sum_xy - sum_x * sum_y
        den = math.sqrt((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2))
        if den == 0:
            return 0.0
        return round(num / den, 4)

    def full_analysis(self, days: int = 7) -> dict[str, Any]:
        sources = self._store.get_sources()
        metric_names: set[str] = set()
        for src in sources:
            rows = self._store.get_metrics("", days=days)
            for r in rows:
                metric_names.add(r.get("metric_name", ""))
        metric_names.discard("")

        trends: dict[str, dict] = {}
        anomalies: dict[str, list[dict]] = {}
        weekly: dict[str, dict] = {}
        circadian: dict[str, dict] = {}
        correlations: list[dict[str, Any]] = []
        names_sorted = sorted(metric_names)

        for name in names_sorted:
            try:
                trends[name] = self.analyze(name, days=days)
                vals = self._fetch_values(name, days)
                detected = self.detect_anomalies(name, vals)
                if detected:
                    anomalies[name] = detected
                weekly[name] = self.weekly_comparison(name)
                circadian[name] = self.detect_circadian_patterns(name, days=days)
            except Exception as exc:
                logger.warning(f"[VECTOR][trend] skip {name}: {exc}")

        for i, a in enumerate(names_sorted):
            for b in names_sorted[i + 1:]:
                try:
                    corr = self.correlate(a, b)
                    if abs(corr) > 0.5:
                        correlations.append({"metrics": [a, b], "correlation": corr})
                except Exception as exc:
                    logger.warning(
                        "[VECTOR][trend] correlation failed for {} / {}: {}",
                        a,
                        b,
                        exc,
                    )

        return {
            "period_days": days,
            "generated_at": datetime.datetime.now().isoformat(),
            "trends": trends,
            "anomalies": anomalies,
            "weekly_comparisons": weekly,
            "circadian_patterns": circadian,
            "correlations": correlations,
        }

    def summarize_period(self, days: int = 7) -> dict[str, Any]:
        return self.full_analysis(days=days)
