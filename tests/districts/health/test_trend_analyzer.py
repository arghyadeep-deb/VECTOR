from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest

from districts.health.metrics_store import MetricsStore
from districts.health.trend_analyzer import TrendAnalyzer


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".db")
    ms = MetricsStore(db_path=tmp, retention_days=90)
    yield ms
    ms.close()
    Path(tmp).unlink(missing_ok=True)


@pytest.fixture
def populated_store(store: MetricsStore):
    now = datetime.datetime.now()
    for i in range(14):
        ts = (now - datetime.timedelta(hours=i * 2)).isoformat()
        store.store_metric("test_source", "heart_rate", 70.0 + (i % 5) * 2, timestamp=ts)
        store.store_metric("test_source", "steps", 6000 + i * 200, timestamp=ts)
        store.store_metric("test_source", "hrv", 40.0 + (i % 3) * 5, timestamp=ts)
    return store


class TestBaselineComputation:
    def test_analyze_returns_all_fields(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        result = analyzer.analyze("heart_rate", days=7)
        assert result["metric_name"] == "heart_rate"
        assert result["direction"] in ("improving", "declining", "stable")
        assert "baseline_7d_mean" in result
        assert "baseline_30d_mean" in result
        assert "delta_7d_pct" in result
        assert "stability" in result

    def test_analyze_empty_metric(self, store: MetricsStore):
        analyzer = TrendAnalyzer(store=store)
        result = analyzer.analyze("nonexistent", days=7)
        assert result["metric_name"] == "nonexistent"
        assert result["stability"] == "insufficient_data"

    def test_baseline_30d_falls_back(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        result = analyzer.analyze("heart_rate", days=7)
        assert result["baseline_30d_mean"] > 0


class TestAnomalyDetection:
    def test_detect_anomalies(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        vals = [70.0, 72.0, 71.0, 140.0, 69.0, 73.0]
        anomalies = analyzer.detect_anomalies("heart_rate", vals, threshold=2.0)
        assert len(anomalies) >= 1
        assert anomalies[0]["metric_name"] == "heart_rate"
        assert anomalies[0]["severity"] >= 1

    def test_no_anomalies(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        vals = [70.0, 71.0, 70.5, 70.8, 71.2, 69.8]
        anomalies = analyzer.detect_anomalies("heart_rate", vals, threshold=3.0)
        assert len(anomalies) == 0

    def test_empty_list(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        assert analyzer.detect_anomalies("heart_rate", []) == []


class TestCircadianPatterns:
    def test_circadian_pattern_detection(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        result = analyzer.detect_circadian_patterns("heart_rate", days=7)
        assert result["metric_name"] == "heart_rate"
        assert "hourly_averages" in result
        assert "peak_hour" in result
        assert "trough_hour" in result

    def test_circadian_no_data(self, store: MetricsStore):
        analyzer = TrendAnalyzer(store=store)
        result = analyzer.detect_circadian_patterns("nonexistent", days=7)
        assert result["pattern"] == "unknown"

    def test_weekly_comparison(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        result = analyzer.weekly_comparison("heart_rate")
        assert result["metric_name"] == "heart_rate"
        assert "this_week_avg" in result
        assert "insight" in result

    def test_correlation(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        corr = analyzer.correlate("heart_rate", "steps")
        assert isinstance(corr, float)

    def test_full_analysis(self, populated_store: MetricsStore):
        analyzer = TrendAnalyzer(store=populated_store)
        result = analyzer.full_analysis(days=7)
        assert "trends" in result
        assert "anomalies" in result
        assert "weekly_comparisons" in result
        assert "circadian_patterns" in result
        assert "correlations" in result
