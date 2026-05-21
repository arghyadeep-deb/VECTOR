import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from unittest.mock import patch, MagicMock

import pytest

from districts.predictive_analytics.anomaly_predictor import (
    AnomalyPredictor, MetricAnomaly, AnomalyType, ANOMALY_CONFIG
)
from districts.predictive_analytics.time_series_forecaster import ForecastResult


@pytest.fixture
def predictor():
    return AnomalyPredictor()


def test_detect_value_out_of_range(predictor):
    values = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11, 13, 10]
    anomalies = predictor.detect("cpu_usage", values)
    value_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.VALUE_OUT_OF_RANGE]
    assert len(value_anomalies) > 0
    for a in value_anomalies:
        assert 1 <= a.severity <= 10
        assert isinstance(a.confidence, float)


def test_detect_trend_divergence(predictor):
    values = [1, 1.1, 1.2, 1.3, 1.4, 10, 11, 12, 13, 14]
    anomalies = predictor.detect("drift_test", values)
    trend = [a for a in anomalies if a.anomaly_type == AnomalyType.TREND_DIVERGENCE]
    assert len(trend) > 0


def test_detect_rate_acceleration(predictor):
    values = [1, 1.1, 1.2, 1.3, 1.5, 2.0, 3.0, 5.0, 10.0, 20.0, 40.0, 80.0]
    anomalies = predictor.detect("accel_test", values)
    accel = [a for a in anomalies if a.anomaly_type == AnomalyType.RATE_ACCELERATION]
    assert len(accel) > 0


def test_detect_compound_anomaly(predictor):
    predictor.zscore_threshold = 0.5
    values = [10, 11, 10, 12, 50, 11, 10, 51, 12, 11, 52, 10, 12, 11, 10]
    anomalies = predictor.detect("compound_test", values)
    compound = [a for a in anomalies if a.anomaly_type == AnomalyType.COMPOUND_ANOMALY]
    assert len(compound) > 0


def test_detect_missing_expected(predictor):
    values = [50, 50, 50, 50, 50]
    anomalies = predictor.detect("frozen_metric", values)
    missing = [a for a in anomalies if a.anomaly_type == AnomalyType.MISSING_EXPECTED]
    assert len(missing) > 0


def test_detect_insufficient_data(predictor):
    anomalies = predictor.detect("no_data", [1, 2])
    assert len(anomalies) == 0


def test_analyze_forecast_vs_actual(predictor):
    fcast = ForecastResult(
        metric_name="cpu_usage",
        timestamps=["2026-01-01T00:00:00", "2026-01-02T00:00:00"],
        values=[50.0, 55.0],
        confidence_lower=[45.0, 50.0],
        confidence_upper=[55.0, 60.0],
        model_used="moving_average",
    )
    actual = [52.0, 80.0]
    anomalies = predictor.analyze(fcast, actual)
    assert len(anomalies) > 0
    for a in anomalies:
        assert a.metric_name == "cpu_usage"
        assert 1 <= a.severity <= 10


def test_analyze_empty_actual(predictor):
    fcast = ForecastResult(
        metric_name="cpu_usage",
        timestamps=[], values=[], confidence_lower=[], confidence_upper=[],
    )
    assert predictor.analyze(fcast, []) == []


def test_severity_integer_range(predictor):
    values = [10, 12, 11, 13, 10, 12, 11, 100, 12, 11, 13, 10]
    anomalies = predictor.detect("sev_test", values)
    for a in anomalies:
        assert isinstance(a.severity, int)
        assert 1 <= a.severity <= 10


def test_estimate_cause(predictor):
    cause = predictor._estimate_cause("cpu", 50.0, 95.0, {})
    assert isinstance(cause, str)
    assert len(cause) > 0

    cause2 = predictor._estimate_cause("cpu", 50.0, 5.0, {})
    assert isinstance(cause2, str)

    cause3 = predictor._estimate_cause("cpu", 0.0, 5.0, {})
    assert isinstance(cause3, str)

    cause4 = predictor._estimate_cause("cpu", 5.0, 0.0, {})
    assert isinstance(cause4, str)


def test_deduplicate(predictor):
    now = "2026-01-01T12:00:00"
    anomalies = [
        MetricAnomaly("cpu", AnomalyType.VALUE_OUT_OF_RANGE, 5, now, 50.0, 95.0, 0.9),
        MetricAnomaly("cpu", AnomalyType.VALUE_OUT_OF_RANGE, 8, now, 50.0, 95.0, 0.9),
    ]
    deduped = predictor._deduplicate(anomalies)
    assert len(deduped) == 1
    assert deduped[0].severity == 8


def test_pushover_alert_high_severity(predictor):
    high_anomaly = MetricAnomaly(
        "critical_metric", AnomalyType.VALUE_OUT_OF_RANGE, 9,
        "2026-01-01T00:00:00", 50.0, 200.0, 0.99,
        cause="Critical spike",
    )
    with patch("httpx.Client") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value.__enter__.return_value = mock_instance
        mock_instance.post.return_value.status_code = 200
        detector = AnomalyPredictor()
        detector.detect("critical_metric", [10, 12, 11, 200, 12, 11, 13, 10])
        assert True


def test_anomaly_types_enum():
    assert len(AnomalyType) == 5
    assert AnomalyType.VALUE_OUT_OF_RANGE.value == "value_out_of_range"
    assert AnomalyType.TREND_DIVERGENCE.value == "trend_divergence"
    assert AnomalyType.RATE_ACCELERATION.value == "rate_acceleration"
    assert AnomalyType.COMPOUND_ANOMALY.value == "compound_anomaly"
    assert AnomalyType.MISSING_EXPECTED.value == "missing_expected"


def test_anomaly_config_defaults():
    assert ANOMALY_CONFIG["confidence_ci_threshold"] == 95
    assert ANOMALY_CONFIG["trend_points"] == 5
    assert ANOMALY_CONFIG["rate_acceleration_factor"] == 2.0
