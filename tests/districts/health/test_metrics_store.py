from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

import pytest
from loguru import logger

from districts.health.metrics_store import MetricsStore


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".db")
    ms = MetricsStore(db_path=tmp, retention_days=30)
    yield ms
    ms.close()
    Path(tmp).unlink(missing_ok=True)


class TestMetricsStoreTables:
    def test_health_metrics_crud(self, store: MetricsStore):
        rid = store.store_metric("test", "heart_rate", 72.0, "bpm")
        assert rid is not None
        rows = store.get_metrics("heart_rate", days=1)
        assert len(rows) == 1
        assert rows[0]["value"] == 72.0

    def test_wearable_metrics(self, store: MetricsStore):
        data = {"heart_rate": 75.0, "hrv": 42.0, "steps": 5000, "timestamp": datetime.datetime.now().isoformat()}
        rid = store.store_wearable("test_phone", data)
        assert rid is not None
        latest = store.get_latest_wearable("test_phone")
        assert latest is not None
        assert latest["heart_rate"] == 75.0

    def test_metric_trends(self, store: MetricsStore):
        trend = {"metric_name": "heart_rate", "direction": "improving", "change_pct": 5.0, "avg": 72.0, "min": 60.0, "max": 85.0, "std_dev": 5.0, "baseline_7d_mean": 70.0, "baseline_7d_std": 3.0, "baseline_30d_mean": 71.0, "baseline_30d_std": 4.0, "delta_7d_pct": 2.5, "delta_30d_pct": 1.0, "stability": "stable"}
        rid = store.store_trend(trend)
        assert rid is not None
        trends = store.get_trends("heart_rate")
        assert len(trends) >= 1

    def test_health_anomalies(self, store: MetricsStore):
        anomaly = {"metric_name": "heart_rate", "expected": 72.0, "actual": 140.0, "deviation": 94.4, "severity": 8, "detected_at": datetime.datetime.now().isoformat(), "trend_direction": "up", "probable_causes": ["stress", "exercise"]}
        rid = store.store_anomaly(anomaly)
        assert rid is not None
        anom = store.get_anomalies(unresolved_only=True)
        assert len(anom) >= 1
        store.acknowledge_anomaly(rid)
        anom2 = store.get_anomalies(unresolved_only=True)
        assert len(anom2) == 0

    def test_health_recommendations(self, store: MetricsStore):
        rec = {"type": "SLEEP_HYGIENE", "title": "Test rec", "description": "Test", "priority": 1, "metric_source": "sleep", "actionable": True}
        rid = store.store_recommendation(rec)
        assert rid is not None
        recs = store.get_recommendations(priority_min=2)
        assert len(recs) >= 1

    def test_emergency_events(self, store: MetricsStore):
        event = {"event_type": "sustained_high_hr", "value": 150.0, "threshold": ">120 bpm", "severity": 8, "message": "High HR", "detected_at": datetime.datetime.now().isoformat()}
        rid = store.store_emergency_event(event)
        assert rid is not None
        evs = store.get_emergency_events(unresolved_only=True)
        assert len(evs) >= 1
        store.resolve_emergency(rid)
        evs2 = store.get_emergency_events(unresolved_only=True)
        assert len(evs2) == 0

    def test_daily_summaries(self, store: MetricsStore):
        summary = {"summary_date": datetime.date.today().isoformat(), "avg_heart_rate": 72.0, "avg_hrv": 45.0, "total_steps": 8000, "total_sleep_h": 7.5, "avg_spo2": 97.0, "avg_stress": 0.3, "anomaly_count": 0, "rec_count": 2}
        rid = store.store_daily_summary(summary)
        assert rid is not None
        summaries = store.get_daily_summaries(days=7)
        assert len(summaries) >= 1

    def test_prune_old_data(self, store: MetricsStore):
        old_ts = (datetime.datetime.now() - datetime.timedelta(days=60)).isoformat()
        store.store_metric("test", "heart_rate", 70.0, timestamp=old_ts)
        fresh_ts = datetime.datetime.now().isoformat()
        store.store_metric("test", "heart_rate", 72.0, timestamp=fresh_ts)
        counts = store.prune_old_data(retention_days=30)
        assert sum(counts.values()) >= 1
        remaining = store.get_metrics("heart_rate", days=365)
        assert len(remaining) == 1
        assert remaining[0]["value"] == 72.0
