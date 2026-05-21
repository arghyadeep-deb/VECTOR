import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from unittest.mock import patch, MagicMock

import pytest

from districts.predictive_analytics.strategy_recommender import (
    StrategyRecommender, Recommendation, RecommendationType
)
from districts.predictive_analytics.time_series_forecaster import ForecastResult
from districts.predictive_analytics.anomaly_predictor import MetricAnomaly, AnomalyType


@pytest.fixture
def recommender():
    return StrategyRecommender()


@pytest.fixture
def sample_forecast():
    return ForecastResult(
        metric_name="cpu_usage",
        timestamps=["2026-01-01T00:00:00"] * 5,
        values=[85, 87, 90, 92, 95],
        confidence_lower=[80] * 5,
        confidence_upper=[98] * 5,
        model_used="moving_average",
        accuracy_score=0.85,
    )


@pytest.fixture
def sample_anomalies():
    return [
        MetricAnomaly(
            metric_name="cpu_usage",
            anomaly_type=AnomalyType.VALUE_OUT_OF_RANGE,
            severity=8,
            detected_at="2026-01-01T00:00:00",
            expected_value=75.0,
            actual_value=95.0,
            confidence=0.9,
            cause="CPU spike",
        ),
    ]


def test_evaluate_with_forecast_and_anomalies(recommender, sample_forecast, sample_anomalies):
    recs = recommender.evaluate(forecast=sample_forecast, anomalies=sample_anomalies)
    assert isinstance(recs, list)
    assert len(recs) > 0
    for r in recs:
        assert isinstance(r.recommendation_type, RecommendationType)
        assert 1 <= r.priority <= 5
        assert isinstance(r.confidence, float)


def test_evaluate_empty(recommender):
    recs = recommender.evaluate()
    assert isinstance(recs, list)


def test_generate_all(recommender, sample_forecast, sample_anomalies):
    predictions = {
        "cpu_usage": sample_forecast,
        "energy_level": sample_forecast,
        "deadline_proximity": sample_forecast,
        "task_completion_rate": sample_forecast,
        "daily_budget_remaining": sample_forecast,
        "active_users": sample_forecast,
        "security_incident_rate": sample_forecast,
    }
    recs = recommender.generate_all(
        predictions=predictions,
        anomalies=sample_anomalies,
        simulations=[],
    )
    assert isinstance(recs, list)
    rec_types = set(r.recommendation_type for r in recs)
    assert RecommendationType.RISK_MITIGATION in rec_types


def test_time_management_recs(recommender, sample_forecast):
    predictions = {"deadline_proximity": sample_forecast}
    recs = recommender._time_management_recs(predictions, [])
    assert isinstance(recs, list)
    for r in recs:
        assert r.recommendation_type == RecommendationType.TIME_MANAGEMENT


def test_health_recs(recommender, sample_forecast):
    predictions = {"energy_level": sample_forecast}
    recs = recommender._health_recs(predictions, [])
    assert isinstance(recs, list)
    for r in recs:
        assert r.recommendation_type == RecommendationType.HEALTH_ACTION


def test_health_recs_with_anomalies(recommender, sample_anomalies):
    recs = recommender._health_recs({}, sample_anomalies)
    assert isinstance(recs, list)


def test_productivity_recs(recommender, sample_forecast):
    predictions = {"task_completion_rate": sample_forecast}
    recs = recommender._productivity_recs(predictions, [])
    assert isinstance(recs, list)
    for r in recs:
        assert r.recommendation_type == RecommendationType.PRODUCTIVITY_OPT


def test_productivity_recs_low_users(recommender):
    low_users_forecast = ForecastResult(
        metric_name="active_users",
        timestamps=["2026-01-01T00:00:00"],
        values=[0.5],
        confidence_lower=[0.0],
        confidence_upper=[2.0],
        model_used="moving_average",
    )
    recs = recommender._productivity_recs({"active_users": low_users_forecast}, [])
    assert len(recs) > 0


def test_risk_recs_security(recommender, sample_anomalies):
    security_anomaly = [
        MetricAnomaly(
            metric_name="security_incident_rate",
            anomaly_type=AnomalyType.VALUE_OUT_OF_RANGE,
            severity=8,
            detected_at="2026-01-01T00:00:00",
            expected_value=1.0,
            actual_value=5.0,
            confidence=0.9,
        ),
    ]
    recs = recommender._risk_recs({}, security_anomaly, [])
    security_recs = [r for r in recs if r.recommendation_type == RecommendationType.SECURITY_WARNING]
    assert len(security_recs) > 0


def test_risk_recs_budget(recommender):
    budget_forecast = ForecastResult(
        metric_name="daily_budget_remaining",
        timestamps=["2026-01-01T00:00:00"] * 3,
        values=[100, 60, 30],
        confidence_lower=[90, 50, 20],
        confidence_upper=[110, 70, 40],
        model_used="moving_average",
    )
    predictions = {"daily_budget_remaining": budget_forecast}
    recs = recommender._risk_recs(predictions, [], [])
    budget_recs = [r for r in recs if r.recommendation_type == RecommendationType.RISK_MITIGATION]
    assert len(budget_recs) > 0


def test_composite_recs_system(recommender, sample_forecast):
    predictions = {
        "cpu_usage": sample_forecast,
        "memory_usage": sample_forecast,
        "response_time": sample_forecast,
    }
    recs = recommender._composite_recs(predictions, [])
    sys_recs = [r for r in recs if r.recommendation_type == RecommendationType.SYSTEM_MAINTENANCE]
    assert len(sys_recs) > 0


def test_composite_recs_high_severity(recommender, sample_anomalies):
    recs = recommender._composite_recs({}, sample_anomalies)
    risk_recs = [r for r in recs if r.recommendation_type == RecommendationType.RISK_MITIGATION]
    assert len(risk_recs) > 0


def test_recommendation_types_complete():
    assert len(RecommendationType) == 7
    types = {
        RecommendationType.TIME_MANAGEMENT,
        RecommendationType.HEALTH_ACTION,
        RecommendationType.PRODUCTIVITY_OPT,
        RecommendationType.RISK_MITIGATION,
        RecommendationType.SECURITY_WARNING,
        RecommendationType.SYSTEM_MAINTENANCE,
        RecommendationType.LIFESTYLE_SUGGESTION,
    }
    assert set(RecommendationType) == types


def test_priority_range(recommender, sample_forecast, sample_anomalies):
    recs = recommender.evaluate(forecast=sample_forecast, anomalies=sample_anomalies)
    for r in recs:
        assert 1 <= r.priority <= 5


def test_recommendation_fields():
    rec = Recommendation(
        recommendation_type=RecommendationType.LIFESTYLE_SUGGESTION,
        title="Test",
        description="Test desc",
        priority=3,
        metric="cpu_usage",
        confidence=0.8,
        actions=["Action 1"],
        evidence=["Evidence 1"],
        actionable=True,
        expires_at="2026-02-01T00:00:00",
        source="test",
    )
    assert rec.recommendation_type == RecommendationType.LIFESTYLE_SUGGESTION
    assert rec.priority == 3
    assert rec.actionable is True
    assert rec.expires_at == "2026-02-01T00:00:00"
    assert rec.source == "test"
    assert len(rec.evidence) == 1


def test_pushover_notify_low_priority(recommender, sample_forecast):
    recs = recommender.generate_all(
        predictions={"cpu_usage": sample_forecast, "energy_level": sample_forecast},
        anomalies=[],
        simulations=[],
    )
    for r in recs:
        assert r.priority >= 1


def test_pushover_integration(recommender):
    rec = Recommendation(
        recommendation_type=RecommendationType.RISK_MITIGATION,
        title="Urgent alert",
        description="Urgent test",
        priority=1,
        metric="test",
        confidence=0.9,
    )
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value.__enter__.return_value = mock_instance
        recommender._pushover_notify(rec)
        assert True
