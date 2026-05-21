import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from districts.predictive_analytics.time_series_forecaster import (
    TimeSeriesForecaster, ForecastResult, FORECAST_METRICS
)


@pytest.fixture
def forecaster():
    return TimeSeriesForecaster()


@pytest.fixture
def sample_data():
    return [10 + i + (i % 3) * 2 for i in range(30)]


def test_forecast_empty_data(forecaster):
    result = forecaster.forecast("cpu_usage", [])
    assert result.metric_name == "cpu_usage"
    assert len(result.values) == 0
    assert result.model_used == "none"


def test_forecast_insufficient_data(forecaster):
    result = forecaster.forecast("cpu_usage", [1, 2])
    assert len(result.values) == 0
    assert result.model_used == "none"


def test_forecast_moving_average(forecaster, sample_data):
    with (
        patch.object(forecaster, "_prophet_available", False),
        patch.object(forecaster, "_arima_available", False),
    ):
        result = forecaster.forecast("cpu_usage", sample_data, periods=5)
    assert result.metric_name == "cpu_usage"
    assert len(result.values) == 5
    assert len(result.confidence_lower) == 5
    assert len(result.confidence_upper) == 5
    assert result.model_used in ("moving_average", "naive")


def test_forecast_arima(forecaster, sample_data):
    if forecaster._arima_available:
        with patch.object(forecaster, "_prophet_available", False):
            result = forecaster.forecast("cpu_usage", sample_data, periods=5)
        assert len(result.values) == 5
        assert result.model_used in ("arima", "moving_average")


def test_prophet_forecast(forecaster, sample_data):
    if forecaster._prophet_available:
        with patch.object(forecaster, "_arima_available", False):
            result = forecaster.forecast("cpu_usage", sample_data, periods=5)
        assert len(result.values) == 5
        assert result.model_used in ("prophet", "moving_average")
    else:
        pytest.skip("Prophet not installed")


def test_ensemble_forecast(forecaster, sample_data):
    if forecaster._prophet_available and forecaster._arima_available:
        result = forecaster.forecast("cpu_usage", sample_data, periods=5)
        assert len(result.values) == 5
        assert result.model_used in ("ensemble", "moving_average")
    else:
        pytest.skip("Prophet and ARIMA both needed")


def test_fallback_chain_on_failure(forecaster, sample_data):
    with (
        patch.object(forecaster, "_Prophet", None),
        patch.object(forecaster, "_ARIMA", None),
    ):
        result = forecaster.forecast("cpu_usage", sample_data, periods=3)
    assert len(result.values) == 3
    assert result.model_used in ("moving_average", "naive")


def test_naive_fallback(forecaster):
    with (
        patch.object(forecaster, "_prophet_available", False),
        patch.object(forecaster, "_arima_available", False),
        patch.object(forecaster, "_moving_average_forecast", side_effect=Exception("MA failed")),
    ):
        result = forecaster.forecast("cpu_usage", [5.0, 6.0, 7.0], periods=3)
    assert len(result.values) == 3
    assert result.model_used == "naive"


def test_forecast_all(forecaster):
    results = forecaster.forecast_all()
    assert isinstance(results, dict)
    assert len(results) >= 14
    if results:
        key = list(results.keys())[0]
        assert isinstance(results[key], ForecastResult)


def test_compute_confidence_intervals(forecaster):
    values = [10.0, 20.0, 30.0]
    ci = forecaster.compute_confidence_intervals(values, ci_80=True, ci_95=True)
    assert "ci_80_lower" in ci
    assert "ci_80_upper" in ci
    assert "ci_95_lower" in ci
    assert "ci_95_upper" in ci
    assert len(ci["ci_80_lower"]) == 3
    assert len(ci["ci_95_lower"]) == 3


def test_compute_confidence_intervals_empty(forecaster):
    ci = forecaster.compute_confidence_intervals([])
    assert len(ci["ci_80_lower"]) == 0


def test_calculate_accuracy(forecaster, sample_data):
    acc = forecaster.calculate_accuracy(sample_data[:5], sample_data[5:10])
    assert isinstance(acc, float)
    assert acc >= 0.0


def test_calculate_accuracy_empty(forecaster):
    assert forecaster.calculate_accuracy([], []) == 0.0


def test_calculate_accuracy_perfect(forecaster):
    assert forecaster.calculate_accuracy([10, 20, 30], [10, 20, 30]) > 50.0


def test_collect_history_empty(forecaster):
    history = forecaster._collect_history("nonexistent_metric", days=1)
    assert isinstance(history, list)


def test_synthetic_history(forecaster):
    synth = forecaster._synthetic_history("cpu_usage")
    assert isinstance(synth, list)
    assert len(synth) == 14


def test_forecast_result_dataclass():
    fr = ForecastResult(
        metric_name="test",
        timestamps=["2026-01-01"],
        values=[50.0],
        confidence_lower=[45.0],
        confidence_upper=[55.0],
        model_used="test_model",
        accuracy_score=0.9,
    )
    assert fr.metric_name == "test"
    assert fr.model_used == "test_model"
    assert fr.accuracy_score == 0.9


def test_forecast_metrics_complete():
    assert len(FORECAST_METRICS) >= 14
    expected = {
        "cpu_usage", "memory_usage", "response_time", "error_rate",
        "throughput", "memory_curator_hit_rate", "token_usage", "active_users",
        "task_completion_rate", "inference_latency", "energy_level",
        "daily_budget_remaining", "deadline_proximity", "security_incident_rate",
    }
    assert set(FORECAST_METRICS.keys()) == expected
