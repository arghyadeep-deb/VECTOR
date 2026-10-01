"""Audit phase 3: districts/predictive_analytics — failures must not read as success."""
import math
import os
from pathlib import Path

import pytest
from loguru import logger

from districts.predictive_analytics.anomaly_predictor import AnomalyPredictor, AnomalyType
from districts.predictive_analytics.causal_simulator import CausalSimulator
from districts.predictive_analytics.prediction_store import PredictionStore
from districts.predictive_analytics.strategy_recommender import StrategyRecommender
from districts.predictive_analytics.time_series_forecaster import ForecastResult, TimeSeriesForecaster

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolated_episodic_db(tmp_path):
    import core.memory.episodic as episodic

    original = os.environ.get("VECTOR_DB_PATH")
    os.environ["VECTOR_DB_PATH"] = str(tmp_path / "audit_predictive.db")
    episodic.close_db_connection()
    try:
        yield
    finally:
        episodic.close_db_connection()
        if original is None:
            os.environ.pop("VECTOR_DB_PATH", None)
        else:
            os.environ["VECTOR_DB_PATH"] = original
        episodic.close_db_connection()


@pytest.fixture
def forecaster():
    tf = TimeSeriesForecaster()
    tf._prophet_available = False
    tf._arima_available = False
    return tf


def _capture_warnings():
    msgs: list[str] = []
    hid = logger.add(lambda m: msgs.append(m.record["message"]), level="WARNING")
    return msgs, hid


# ---- time_series_forecaster -------------------------------------------------

def test_forecast_drops_nonfinite_points(forecaster):
    data = [10.0, 11.0, float("nan"), 12.0, float("inf"), 13.0, 12.5, 11.5]
    res = forecaster.forecast("cpu_usage", data, periods=3)
    assert len(res.values) == 3
    assert all(math.isfinite(v) for v in res.values + res.confidence_lower + res.confidence_upper)


def test_forecast_mostly_nan_is_insufficient_not_a_number(forecaster):
    res = forecaster.forecast("cpu_usage", [1.0, float("nan"), float("nan"), 2.0], periods=3)
    assert res.values == [] and res.model_used == "none"


def test_forecast_all_marks_synthetic_history(forecaster, monkeypatch):
    monkeypatch.setattr(forecaster, "_collect_history", lambda metric, days=30: [])
    results = forecaster.forecast_all()
    assert results
    assert all("synthetic_history" in r.model_used for r in results.values())


def test_forecast_all_real_history_not_marked(forecaster, monkeypatch):
    monkeypatch.setattr(forecaster, "_collect_history", lambda metric, days=30: [10.0 + i for i in range(14)])
    results = forecaster.forecast_all()
    assert all("synthetic" not in r.model_used for r in results.values())


def test_collect_history_failure_is_logged_not_swallowed(forecaster, monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(PredictionStore, "__init__", boom)
    msgs, hid = _capture_warnings()
    try:
        assert forecaster._collect_history("cpu_usage") == []
    finally:
        logger.remove(hid)
    assert any("history read failed" in m and "disk gone" in m for m in msgs)


def test_ensemble_does_not_blend_failed_submodel(forecaster):
    ma = ForecastResult("m", ["t"] * 3, [1.0] * 3, [0.0] * 3, [2.0] * 3, model_used="moving_average")
    ar = ForecastResult("m", ["t"] * 3, [9.0] * 3, [8.0] * 3, [10.0] * 3, model_used="arima")
    forecaster._prophet_forecast = lambda *a, **k: ma  # prophet failed -> internal MA fallback
    forecaster._arima_forecast = lambda *a, **k: ar
    res = forecaster._ensemble_forecast("m", [1.0] * 12, 3)
    assert res.model_used == "arima" and res.values == [9.0] * 3


def test_prophet_timestamps_are_iso_strings():
    pd = pytest.importorskip("pandas")
    tf = TimeSeriesForecaster()

    class FakeProphet:
        def __init__(self, **k): ...
        def fit(self, df):
            self.df = df
        def make_future_dataframe(self, periods, freq):
            return pd.DataFrame({"ds": pd.date_range("2026-01-01", periods=periods, freq="D")})
        def predict(self, fut):
            fut = fut.copy()
            fut["yhat"] = 1.0
            fut["yhat_lower"] = 0.5
            fut["yhat_upper"] = 1.5
            return fut

    tf._Prophet = FakeProphet
    res = tf._prophet_forecast("m", [1.0] * 12, periods=3)
    assert res.model_used == "prophet"
    assert all(isinstance(t, str) for t in res.timestamps)


# ---- anomaly_predictor ------------------------------------------------------

def test_detect_nan_reading_is_reported_not_clean():
    anoms = AnomalyPredictor().detect("cpu_usage", [10, 11, 12, float("nan"), 11, 10, 12, 11])
    assert any(a.anomaly_type == AnomalyType.MISSING_EXPECTED and "non-finite" in a.cause for a in anoms)


def test_detect_still_finds_spike_beside_nan():
    vals = [10, 11, 10, float("nan"), 11, 10, 11, 10, 11, 10, 90, 11]
    anoms = AnomalyPredictor().detect("cpu_usage", vals)
    assert any(a.anomaly_type == AnomalyType.VALUE_OUT_OF_RANGE and a.actual_value == 90 for a in anoms)


# ---- causal_simulator -------------------------------------------------------

def test_unknown_distribution_fails_instead_of_confident_result():
    res = CausalSimulator().run_monte_carlo(
        "x", {"base_value": 50.0, "parameters": {"p": {"distribution": "gaussian", "mean": 5}}}, iterations=50
    )
    assert res.iterations == 0 and res.outcomes == []


@pytest.mark.parametrize("name", ["../traversal_probe_xyz", "a/b", "..\\x", "", "x.yaml/../../y", None])
def test_load_scenario_rejects_unsafe_names(name):
    escaped = REPO / "data" / "predictive" / "traversal_probe_xyz.yaml"
    try:
        assert CausalSimulator().load_scenario(name) is None
        assert not escaped.exists()
    finally:
        escaped.unlink(missing_ok=True)


# ---- prediction_store -------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    ps = PredictionStore(str(tmp_path / "ps.db"))
    yield ps
    ps.close()


def test_store_returns_empty_id_on_failure(store):
    fc = ForecastResult("cpu_usage", ["t"], [1.0], [0.5], [1.5], model_used="moving_average")
    assert store.store_forecast(fc)
    store._conn.close()
    assert store.store_forecast(fc) == ""


def test_check_accuracy_zero_actual_has_no_bogus_mape(store):
    fid = store.store_forecast(ForecastResult("m", ["t"], [5.0], [4.0], [6.0], model_used="moving_average"))
    acc = store.check_accuracy(fid, 0.0)
    assert acc and acc["mape"] is None
    board = store.get_model_leaderboard("m")
    assert board[0]["avg_mape"] is None


def test_check_accuracy_rejects_nonfinite_actual(store):
    fid = store.store_forecast(ForecastResult("m", ["t"], [5.0], [4.0], [6.0], model_used="moving_average"))
    assert store.check_accuracy(fid, float("nan")) == {}
    assert store.get_model_leaderboard("m") == []


# ---- strategy_recommender.run / generate_all -------------------------------

async def test_run_forecast_insufficient_data_is_not_ok():
    res = await StrategyRecommender().run({"type": "forecast", "params": {"metric_name": "cpu_usage", "historical_data": [1.0, 2.0]}})
    assert res["status"] == "insufficient_data"


async def test_run_detect_anomalies_too_few_values_is_not_ok():
    res = await StrategyRecommender().run({"type": "detect_anomalies", "params": {"metric_name": "cpu_usage", "values": [1.0, 2.0]}})
    assert res["status"] == "insufficient_data"
    assert "anomalies" not in res


async def test_run_simulate_failure_is_error():
    res = await StrategyRecommender().run({
        "type": "simulate",
        "params": {"metric_name": "x", "iterations": 20,
                   "scenario_params": {"base_value": 1.0, "parameters": {"p": {"distribution": "bogus"}}}},
    })
    assert res["status"] == "error"


def test_generate_all_ignores_synthetic_forecasts():
    sr = StrategyRecommender()
    low = [10.0] * 5
    synth = ForecastResult("energy_level", ["t"] * 5, low, low, low, model_used="moving_average+synthetic_history")
    real = ForecastResult("energy_level", ["t"] * 5, low, low, low, model_used="moving_average")
    assert sr.generate_all({"energy_level": synth}, [], []) == []
    assert any(r.metric == "energy_level" for r in sr.generate_all({"energy_level": real}, [], []))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
