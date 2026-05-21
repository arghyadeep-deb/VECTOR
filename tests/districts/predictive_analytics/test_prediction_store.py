import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import tempfile
import json
from datetime import datetime, timezone

import pytest

from districts.predictive_analytics.prediction_store import PredictionStore
from districts.predictive_analytics.time_series_forecaster import ForecastResult
from districts.predictive_analytics.anomaly_predictor import MetricAnomaly, AnomalyType
from districts.predictive_analytics.strategy_recommender import Recommendation, RecommendationType
from districts.predictive_analytics.causal_simulator import SimulationResult


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    ps = PredictionStore(db_path)
    yield ps
    ps.close()
    Path(db_path).unlink(missing_ok=True)


def test_store_forecast(store):
    fcast = ForecastResult(
        metric_name="cpu_usage",
        timestamps=["2026-01-01T00:00:00"],
        values=[85.0],
        confidence_lower=[80.0],
        confidence_upper=[90.0],
        model_used="moving_average",
        accuracy_score=0.9,
    )
    fid = store.store_forecast(fcast)
    assert isinstance(fid, str)
    assert len(fid) > 0


def test_store_anomaly(store):
    anom = MetricAnomaly(
        metric_name="memory_usage",
        anomaly_type=AnomalyType.VALUE_OUT_OF_RANGE,
        severity=7,
        detected_at="2026-01-01T00:00:00",
        expected_value=75.0,
        actual_value=95.0,
        confidence=0.9,
        cause="Memory spike",
    )
    aid = store.store_anomaly(anom)
    assert isinstance(aid, str)
    assert len(aid) > 0


def test_store_recommendation(store):
    rec = Recommendation(
        recommendation_type=RecommendationType.RISK_MITIGATION,
        title="Test recommendation",
        description="A test recommendation",
        priority=1,
        metric="cpu_usage",
        confidence=0.85,
        actions=["Action 1", "Action 2"],
        evidence=["Evidence 1"],
        source="test",
    )
    rid = store.store_recommendation(rec)
    assert isinstance(rid, str)

    pending = store.get_pending_recommendations()
    assert len(pending) >= 1
    assert pending[0]["title"] == "Test recommendation"


def test_store_simulation(store):
    sim = SimulationResult(
        scenario_name="test_scenario",
        iterations=500,
        outcomes=[{"_outcome": 50.0}, {"_outcome": 55.0}],
        mean_outcome=52.5,
        confidence_interval=(48.0, 57.0),
        risk_factors=[{"parameter": "demand", "correlation": 0.8, "impact": "high", "direction": "positive"}],
        converged=True,
    )
    sid = store.store_simulation(sim)
    assert isinstance(sid, str)

    recent = store.get_recent_simulations()
    assert len(recent) >= 1
    assert recent[0]["scenario_name"] == "test_scenario"


def test_store_accuracy(store):
    accuracy = {
        "forecast_id": "test-fid",
        "metric_name": "cpu_usage",
        "model_used": "moving_average",
        "rmse": 2.5,
        "mae": 1.8,
        "mape": 3.5,
        "actual_value": 85.0,
        "predicted_value": 83.0,
    }
    aid = store.store_accuracy(accuracy)
    assert isinstance(aid, str)


def test_check_accuracy(store):
    fcast = ForecastResult(
        metric_name="cpu_usage",
        timestamps=["2026-01-01T00:00:00"],
        values=[85.0],
        confidence_lower=[80.0],
        confidence_upper=[90.0],
        model_used="moving_average",
        accuracy_score=0.9,
    )
    fid = store.store_forecast(fcast)
    result = store.check_accuracy(fid, 83.0)
    assert isinstance(result, dict)
    assert "rmse" in result
    assert "mae" in result
    assert "mape" in result
    assert result["forecast_id"] == fid
    assert abs(result["rmse"] - 2.0) < 0.01


def test_check_accuracy_missing_forecast(store):
    result = store.check_accuracy("nonexistent-id", 50.0)
    assert result == {}


def test_leaderboard(store):
    for model in ("prophet", "arima", "moving_average"):
        fcast = ForecastResult(
            metric_name="cpu_usage",
            timestamps=["2026-01-01T00:00:00"],
            values=[85.0],
            confidence_lower=[80.0],
            confidence_upper=[90.0],
            model_used=model,
        )
        fid = store.store_forecast(fcast)
        store.check_accuracy(fid, 83.0)

    leaderboard = store.get_model_leaderboard("cpu_usage")
    assert isinstance(leaderboard, list)
    assert len(leaderboard) >= 1
    row = leaderboard[0]
    assert "model_used" in row
    assert "avg_rmse" in row


def test_get_recent_forecasts(store):
    fcast = ForecastResult(
        metric_name="cpu_usage",
        timestamps=["2026-01-01T00:00:00"],
        values=[85.0],
        confidence_lower=[80.0],
        confidence_upper=[90.0],
        model_used="moving_average",
    )
    store.store_forecast(fcast)
    forecasts = store.get_recent_forecasts(limit=10)
    assert isinstance(forecasts, list)
    assert len(forecasts) >= 1


def test_get_recent_anomalies(store):
    anom = MetricAnomaly(
        metric_name="cpu_usage",
        anomaly_type=AnomalyType.VALUE_OUT_OF_RANGE,
        severity=8,
        detected_at="2026-01-01T00:00:00",
        expected_value=75.0,
        actual_value=95.0,
        confidence=0.9,
    )
    store.store_anomaly(anom)
    anomalies = store.get_recent_anomalies(limit=10)
    assert isinstance(anomalies, list)
    assert len(anomalies) >= 1


def test_mark_recommendation_applied(store):
    rec = Recommendation(
        recommendation_type=RecommendationType.RISK_MITIGATION,
        title="Mark test",
        description="Test",
        priority=1,
        metric="cpu_usage",
        confidence=0.8,
    )
    rid = store.store_recommendation(rec)
    assert store.mark_recommendation_applied(rid) is True
    assert store.mark_recommendation_applied("nonexistent") is False


def test_prune_old_records(store):
    fcast = ForecastResult(
        metric_name="cpu_usage",
        timestamps=["2026-01-01T00:00:00"],
        values=[85.0],
        confidence_lower=[80.0],
        confidence_upper=[90.0],
        model_used="moving_average",
    )
    store.store_forecast(fcast)
    pruned = store.prune_old_records(days=0)
    assert isinstance(pruned, int)
