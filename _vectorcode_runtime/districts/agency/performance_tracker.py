import sys
import os
import shutil
import uuid
import json
import re
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory


class PerformanceTracker(AgentBase):
    """
    Tracks metrics over time, detects trends, and alerts on anomalies.
    Used for monitoring performance across various dimensions.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "PerformanceTracker", "agency")
        self.capabilities = ["acknowledge_alert", "active_alerts", "agency", "alert_anomaly", "get_comparison", "get_metric_summary", "get_trend", "performance", "remove_metric", "track_metric", "tracking"]
        if ghost:
            self.inherit_ghost(ghost)

        self._metrics: dict[str, list[dict]] = {}
        self._alerts: list[dict] = []
        self._thresholds: dict[str, float] = {}
        self._episodic = EpisodicMemory()
        from core.runtime_paths import data_path

        self._data_file = data_path("performance_metrics.json")
        self._load_data()
        logger.info(f"[VECTOR][performance_tracker] PerformanceTracker initialized")

    def _load_data(self) -> None:
        """Load metrics from persistent storage."""
        if self._data_file.exists():
            try:
                with open(self._data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._metrics = data.get("metrics", {})
                    self._alerts = data.get("alerts", [])
                    self._thresholds = data.get("thresholds", {})
                logger.info(f"[VECTOR][performance_tracker] Loaded {len(self._metrics)} metric streams")
            except Exception as e:
                logger.error(f"[VECTOR][performance_tracker] Failed to load data: {e}")
                # Starting empty means the next save would overwrite the unreadable file -- keep a copy.
                try:
                    shutil.copy2(self._data_file, self._data_file.with_name(self._data_file.name + ".corrupt"))
                except OSError as copy_err:
                    logger.error(f"[VECTOR][performance_tracker] Could not back up unreadable metrics file: {copy_err}")

    def _save_data(self) -> bool:
        """Save metrics to persistent storage."""
        try:
            self._data_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._data_file.with_name(self._data_file.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "metrics": self._metrics,
                    "alerts": self._alerts[-500:],
                    "thresholds": self._thresholds
                }, f, indent=2)
            os.replace(tmp, self._data_file)  # atomic: a crash never leaves a truncated file
            return True
        except Exception as e:
            logger.error(f"[VECTOR][performance_tracker] Failed to save data: {e}")
            return False

    def track_metric(self, name: str, value: float, tags: dict | None = None) -> dict:
        """
        Log a metric value with timestamp.
        Automatically checks for anomalies if threshold is set.
        """
        name = name.strip().lower().replace(" ", "_")

        if name not in self._metrics:
            self._metrics[name] = []

        entry = {
            "id": str(uuid.uuid4()),
            "value": float(value),
            "timestamp": self._get_timestamp(),
            "tags": tags or {}
        }

        self._metrics[name].append(entry)

        if len(self._metrics[name]) > 10000:
            self._metrics[name] = self._metrics[name][-5000:]

        alert_triggered = self._check_threshold(name, value)
        if alert_triggered:
            entry["alert_triggered"] = True

        self._episodic.store(
            event_type="metric_tracked",
            content=f"{name}: {value}",
            tags=["performance", name, "tracked"],
            source="performance_tracker"
        )

        self._save_data()
        self.award_points(1, f"metric_tracked_{name}")

        return {
            "status": "success",
            "metric": name,
            "value": value,
            "alert": alert_triggered
        }

    def _check_threshold(self, metric_name: str, value: float) -> Optional[dict]:
        """Check if value exceeds threshold and create alert."""
        if metric_name not in self._thresholds:
            return None

        threshold = self._thresholds[metric_name]
        exceeded = False
        direction = "above"

        if "above" in threshold:
            if value > threshold["above"]:
                exceeded = True
            direction = "above"
        elif "below" in threshold:
            if value < threshold["below"]:
                exceeded = True
            direction = "below"

        if exceeded:
            alert = {
                "id": str(uuid.uuid4()),
                "metric": metric_name,
                "value": value,
                "threshold": threshold,
                "direction": direction,
                "timestamp": self._get_timestamp(),
                "acknowledged": False
            }
            self._alerts.append(alert)
            self.deduct_points(10, f"anomaly_detected_{metric_name}")
            logger.warning(f"[VECTOR][performance_tracker] ALERT: {metric_name} {direction} threshold")
            return alert

        return None

    def get_trend(self, metric_name: str, days: int = 7) -> dict:
        """
        Get trend data for a metric over specified days.
        Returns statistical summary and data points.
        """
        metric_name = metric_name.strip().lower().replace(" ", "_")

        if metric_name not in self._metrics:
            return {
                "metric": metric_name,
                "data_points": 0,
                "error": "Metric not found"
            }

        cutoff = self._get_cutoff_timestamp(days)
        data_points = [
            p for p in self._metrics[metric_name]
            if p["timestamp"] >= cutoff
        ]

        if not data_points:
            return {
                "metric": metric_name,
                "data_points": 0,
                "trend": "insufficient_data"
            }

        values = [p["value"] for p in data_points]
        values_sorted = sorted(values)
        n = len(values)

        stats = {
            "metric": metric_name,
            "data_points": n,
            "period_days": days,
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / n,
            "median": values_sorted[n // 2] if n % 2 else (values_sorted[n // 2 - 1] + values_sorted[n // 2]) / 2,
            "std_dev": self._calculate_std_dev(values),
            "first_value": values[0],
            "last_value": values[-1],
            "change": values[-1] - values[0],
            "change_percent": ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0,
            "trend": self._determine_trend(values),
            "data": data_points[-100:]
        }

        return stats

    def _calculate_std_dev(self, values: list[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return variance ** 0.5

    def _determine_trend(self, values: list[float]) -> str:
        """Determine trend direction from values."""
        if len(values) < 3:
            return "stable"

        first_third = values[:len(values) // 3]
        last_third = values[-len(values) // 3:]

        avg_first = sum(first_third) / len(first_third)
        avg_last = sum(last_third) / len(last_third)

        change_pct = ((avg_last - avg_first) / avg_first * 100) if avg_first != 0 else 0

        if change_pct > 10:
            return "increasing"
        elif change_pct < -10:
            return "decreasing"
        return "stable"

    def alert_anomaly(self, metric_name: str, threshold: float, direction: str = "above") -> bool:
        """
        Set an alert threshold for a metric.
        Direction: 'above', 'below', or 'both'
        """
        metric_name = metric_name.strip().lower().replace(" ", "_")

        if direction == "above":
            self._thresholds[metric_name] = {"above": threshold}
        elif direction == "below":
            self._thresholds[metric_name] = {"below": threshold}
        elif direction == "both":
            self._thresholds[metric_name] = {"above": threshold, "below": threshold}
        else:
            return False

        self._save_data()
        self.award_points(5, f"alert_set_{metric_name}")
        logger.info(f"[VECTOR][performance_tracker] Alert set for {metric_name}: {direction} {threshold}")
        return True

    def get_active_alerts(self) -> list[dict]:
        """Get all unacknowledged alerts."""
        return [a for a in self._alerts if not a.get("acknowledged")]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self._alerts:
            if alert.get("id") == alert_id:
                alert["acknowledged"] = True
                alert["acknowledged_at"] = self._get_timestamp()
                self._save_data()
                self.award_points(5, "alert_acknowledged")
                return True
        return False

    def clear_alert(self, alert_id: str) -> bool:
        """Clear/delete an alert."""
        initial_len = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.get("id") != alert_id]
        return len(self._alerts) < initial_len

    def get_all_metrics(self) -> list[str]:
        """Get list of all tracked metrics."""
        return list(self._metrics.keys())

    def get_metric_summary(self) -> dict:
        """Get summary of all tracked metrics."""
        summary = {
            "total_metrics": len(self._metrics),
            "total_data_points": sum(len(v) for v in self._metrics.values()),
            "active_alerts": len(self.get_active_alerts()),
            "metrics": {}
        }

        for metric_name, data_points in self._metrics.items():
            if data_points:
                values = [p["value"] for p in data_points]
                summary["metrics"][metric_name] = {
                    "data_points": len(values),
                    "latest": values[-1],
                    "latest_time": data_points[-1]["timestamp"]
                }

        return summary

    def _metrics_named_in_query(self, query: str) -> list[str]:
        """Return all persisted metrics explicitly referenced by a query."""
        normalized = " ".join(re.findall(r"[a-z0-9]+", query.casefold()))
        query_terms = set(normalized.split())
        exact_matches = []
        for metric_name in self._metrics:
            readable_name = " ".join(re.findall(r"[a-z0-9]+", metric_name.casefold()))
            if re.search(rf"(?<!\w){re.escape(readable_name)}(?!\w)", normalized):
                exact_matches.append(metric_name)

        if exact_matches:
            return exact_matches

        descriptive_matches = []
        for metric_name in self._metrics:
            readable_name = " ".join(re.findall(r"[a-z0-9]+", metric_name.casefold()))
            # Units are often omitted in natural language (for example,
            # "response time" for ``response_time_ms``).  Match all of the
            # descriptive metric terms. A result may remain ambiguous.
            metric_terms = [
                term for term in readable_name.split()
                if not re.fullmatch(r"(?:ms|s|sec(?:onds)?|p\d+)", term)
            ]
            if len(metric_terms) > 1 and all(term in query_terms for term in metric_terms):
                descriptive_matches.append(metric_name)
        return descriptive_matches

    def answer_performance_question(self, query: str) -> Optional[dict]:
        """Resolve supported free-text questions through existing read methods.

        Unknown metrics remain visibly unknown rather than being guessed from
        the language in the request.  The response is therefore evidence from
        this tracker's persisted metrics and alerts, not an LLM assertion.
        """
        normalized = " ".join(query.casefold().split())
        if re.search(r"\b(?:add|create|delete|remove|clear|acknowledge|configure|update|change|set|track|log|record)\b", normalized):
            return None

        has_question_shape = normalized.endswith("?") or bool(re.match(
            r"(?:how|which|what|are there|do we have|can you|could you|would you|show me|list|give me|tell me|any)\b",
            normalized,
        ))
        asks_alerts = bool(re.search(r"\b(?:active\s+)?alerts?\b|\banomal(?:y|ies)\b", normalized))
        asks_trend = bool(re.search(r"\b(?:trend|trending)\b", normalized))
        asks_summary = bool(re.search(
            r"\b(?:how many|number of|count of|total)\s+metrics?\b|\bmetric\s+(?:summary|overview)\b",
            normalized,
        ))
        metric_matches = self._metrics_named_in_query(query) if asks_trend else []

        if not has_question_shape or not (asks_alerts or asks_summary or (asks_trend and metric_matches)):
            return None

        if len(metric_matches) > 1:
            return {
                "status": "error",
                "query": query,
                "error": "ambiguous metric reference",
                "matching_metrics": metric_matches,
            }

        result = {
            "status": "ok",
            "query": query,
            "summary": self.get_metric_summary(),
        }
        if asks_alerts:
            result["alerts"] = self.get_active_alerts()
        if asks_trend and metric_matches:
            # A trend question combined with an alert/summary cue but no named metric (e.g. "show
            # active alerts and trend?") reaches here with asks_trend True and metric_matches empty --
            # the guard above only requires asks_alerts/asks_summary, not a named metric. Skip the trend
            # branch rather than indexing an empty list (Codex T9-review-cycle finding, verified real).
            metric_name = metric_matches[0]
            result["metric"] = metric_name
            result["trend"] = self.get_trend(metric_name)
        return result

    def get_comparison(self, metric_a: str, metric_b: str, days: int = 7) -> dict:
        """Compare trends between two metrics."""
        trend_a = self.get_trend(metric_a, days)
        trend_b = self.get_trend(metric_b, days)

        return {
            "metric_a": metric_a,
            "metric_b": metric_b,
            "period_days": days,
            "stats_a": {k: v for k, v in trend_a.items() if k not in ["data", "metric"]},
            "stats_b": {k: v for k, v in trend_b.items() if k not in ["data", "metric"]},
            "correlation": self._calculate_correlation(
                [p["value"] for p in trend_a.get("data", [])],
                [p["value"] for p in trend_b.get("data", [])]
            )
        }

    def _calculate_correlation(self, values_a: list[float], values_b: list[float]) -> float:
        """Calculate Pearson correlation between two value lists."""
        if len(values_a) != len(values_b) or len(values_a) < 2:
            return 0.0

        n = len(values_a)
        mean_a = sum(values_a) / n
        mean_b = sum(values_b) / n

        numerator = sum((a - mean_a) * (b - mean_b) for a, b in zip(values_a, values_b))
        denom_a = sum((a - mean_a) ** 2 for a in values_a) ** 0.5
        denom_b = sum((b - mean_b) ** 2 for b in values_b) ** 0.5

        if denom_a * denom_b == 0:
            return 0.0

        return numerator / (denom_a * denom_b)

    def remove_metric(self, metric_name: str) -> bool:
        """Remove a metric and all its data."""
        if metric_name in self._metrics:
            del self._metrics[metric_name]
            if metric_name in self._thresholds:
                del self._thresholds[metric_name]
            self._save_data()
            return True
        return False

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        return datetime.now(timezone.utc).isoformat()

    def _get_cutoff_timestamp(self, days: int) -> str:
        """Get timestamp cutoff for specified days."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return cutoff.isoformat()


    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = [
            "track_metric", "get_trend", "alert_anomaly", "active_alerts",
            "acknowledge_alert", "get_metric_summary", "get_comparison", "remove_metric",
        ]

        if task_type == "track_metric":
            r = self.track_metric(p.get("metric", ""), float(p.get("value", 0)), p.get("tags"))
            return {**r, "status": "ok" if r.get("status") == "success" else "error"}
        if task_type == "get_trend":
            trend = self.get_trend(p.get("metric", "engagement"), p.get("days", 7))
            # get_trend reports an unknown metric via an "error" key; don't mask it as ok.
            return {**trend, "status": "error" if "error" in trend else "ok"}
        if task_type == "alert_anomaly":
            return {"status": "ok", "set": self.alert_anomaly(p.get("metric", ""), float(p.get("threshold", 0)), p.get("direction", "above"))}
        if task_type == "active_alerts":
            return {"status": "ok", "alerts": self.get_active_alerts()}
        if task_type == "acknowledge_alert":
            return {"status": "ok", "acknowledged": self.acknowledge_alert(p.get("alert_id", ""))}
        if task_type == "get_metric_summary":
            return {"status": "ok", **self.get_metric_summary()}
        if task_type == "get_comparison":
            cmp = self.get_comparison(p.get("metric_a", ""), p.get("metric_b", ""), p.get("days", 7))
            unknown = [k for k in ("stats_a", "stats_b") if "error" in cmp[k]]
            if unknown:
                return {**cmp, "status": "error", "error": "Metric not found"}
            return {"status": "ok", **cmp}
        if task_type == "remove_metric":
            return {"status": "ok", "removed": self.remove_metric(p.get("metric", ""))}

        query = p.get("query") or p.get("content") or ""
        if isinstance(query, str):
            answer = self.answer_performance_question(query)
            if answer is not None:
                return answer

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    tracker = PerformanceTracker()

    tracker.track_metric("cpu_usage", 75.5)
    tracker.track_metric("memory_usage", 60.2)
    tracker.track_metric("response_time_ms", 150.0)

    tracker.alert_anomaly("cpu_usage", 90, "above")

    for i in range(5):
        tracker.track_metric("requests_per_min", 100 + i * 10)

    trend = tracker.get_trend("requests_per_min", 1)
    print(f"Trend: {trend['trend']}, Change: {trend['change_percent']:.1f}%")

    alerts = tracker.get_active_alerts()
    print(f"Active alerts: {len(alerts)}")

    summary = tracker.get_metric_summary()
    print(f"Total metrics: {summary['total_metrics']}")

    print("✅ performance_tracker.py OK")
