import tempfile
from pathlib import Path

import unittest
from datetime import datetime, timezone, timedelta

from districts.predictive_analytics.prediction_store import PredictionStore
from districts.predictive_analytics.time_series_forecaster import (
    TimeSeriesForecaster, ForecastResult, FORECAST_METRICS,
)
from districts.predictive_analytics.anomaly_predictor import (
    AnomalyPredictor, MetricAnomaly, AnomalyType,
)
from districts.predictive_analytics.strategy_recommender import (
    StrategyRecommender, Recommendation, RecommendationType,
)
from districts.predictive_analytics.causal_simulator import (
    CausalSimulator, SimulationResult,
)


def _make_forecast(metric_name="cpu_usage", model="moving_average", values=None):
    if values is None:
        values = [80.0, 82.0, 84.0, 86.0, 88.0, 90.0, 92.0]
    n = len(values)
    now = datetime.now(timezone.utc)
    timestamps = [(now + timedelta(days=i + 1)).isoformat() for i in range(n)]
    return ForecastResult(
        metric_name=metric_name,
        timestamps=timestamps,
        values=values,
        confidence_lower=[v - 5 for v in values],
        confidence_upper=[v + 5 for v in values],
        model_used=model,
        accuracy_score=0.9,
    )


def _make_anomaly(metric_name="cpu_usage", severity=7, atype=AnomalyType.VALUE_OUT_OF_RANGE):
    return MetricAnomaly(
        metric_name=metric_name,
        anomaly_type=atype,
        severity=severity,
        detected_at=datetime.now(timezone.utc).isoformat(),
        expected_value=50.0,
        actual_value=90.0,
        confidence=0.8,
        cause="Test anomaly",
    )


def _make_recommendation(metric="cpu_usage", priority=2, rtype=RecommendationType.RISK_MITIGATION):
    return Recommendation(
        recommendation_type=rtype,
        title="Test recommendation",
        description="Test description",
        priority=priority,
        metric=metric,
        confidence=0.8,
        actions=["Action 1", "Action 2"],
        evidence=["Evidence 1"],
    )


def _make_simulation(scenario_name="test_scenario"):
    return SimulationResult(
        scenario_name=scenario_name,
        iterations=100,
        outcomes=[{"_outcome": 50.0}, {"_outcome": 60.0}],
        mean_outcome=55.0,
        confidence_interval=(45.0, 65.0),
        converged=True,
    )


# ─────────────────────────────────────────────────────────────
# TestPredictionStore
# ─────────────────────────────────────────────────────────────
class TestPredictionStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.store = PredictionStore(self._tmp.name)

    def tearDown(self):
        self.store.close()
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_init_creates_forecasts_table(self):
        rows = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='forecasts'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_init_creates_anomalies_table(self):
        rows = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='anomalies'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_init_creates_recommendations_table(self):
        rows = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recommendations'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_init_creates_simulations_table(self):
        rows = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='simulations'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_init_creates_prediction_accuracy_table(self):
        rows = self.store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_accuracy'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_store_forecast_returns_string(self):
        fid = self.store.store_forecast(_make_forecast())
        self.assertIsInstance(fid, str)
        self.assertGreater(len(fid), 10)

    def test_store_forecast_persisted_metric_name(self):
        fid = self.store.store_forecast(_make_forecast(metric_name="memory_usage"))
        row = self.store._conn.execute(
            "SELECT metric_name FROM forecasts WHERE id=?", (fid,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "memory_usage")

    def test_store_anomaly_returns_string(self):
        aid = self.store.store_anomaly(_make_anomaly())
        self.assertIsInstance(aid, str)
        self.assertGreater(len(aid), 10)

    def test_store_anomaly_persisted_severity(self):
        aid = self.store.store_anomaly(_make_anomaly(severity=9))
        row = self.store._conn.execute(
            "SELECT severity FROM anomalies WHERE id=?", (aid,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 9)

    def test_store_recommendation_returns_string(self):
        rid = self.store.store_recommendation(_make_recommendation())
        self.assertIsInstance(rid, str)
        self.assertGreater(len(rid), 10)

    def test_store_recommendation_persisted_priority(self):
        rid = self.store.store_recommendation(_make_recommendation(priority=1))
        row = self.store._conn.execute(
            "SELECT priority FROM recommendations WHERE id=?", (rid,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)

    def test_store_simulation_returns_string(self):
        sid = self.store.store_simulation(_make_simulation())
        self.assertIsInstance(sid, str)
        self.assertGreater(len(sid), 10)

    def test_store_simulation_persisted_scenario_name(self):
        sid = self.store.store_simulation(_make_simulation("budget_scenario"))
        row = self.store._conn.execute(
            "SELECT scenario_name FROM simulations WHERE id=?", (sid,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "budget_scenario")

    def test_store_accuracy_returns_string(self):
        aid = self.store.store_accuracy({
            "forecast_id": "test-fid", "metric_name": "cpu_usage",
            "model_used": "moving_average", "rmse": 1.5, "mae": 1.2,
            "mape": 2.0, "actual_value": 80.0, "predicted_value": 82.0,
        })
        self.assertIsInstance(aid, str)

    def test_check_accuracy_has_rmse_mae_mape(self):
        fid = self.store.store_forecast(_make_forecast(values=[85.0, 86.0, 87.0]))
        result = self.store.check_accuracy(fid, 83.0)
        self.assertIsInstance(result, dict)
        self.assertIn("rmse", result)
        self.assertIn("mae", result)
        self.assertIn("mape", result)

    def test_check_accuracy_nonexistent_returns_empty(self):
        result = self.store.check_accuracy("nonexistent-xyz", 50.0)
        self.assertEqual(result, {})

    def test_get_model_leaderboard_returns_list(self):
        result = self.store.get_model_leaderboard("cpu_usage")
        self.assertIsInstance(result, list)

    def test_get_model_leaderboard_populated_after_check(self):
        fid = self.store.store_forecast(_make_forecast())
        self.store.check_accuracy(fid, 82.0)
        leaderboard = self.store.get_model_leaderboard("cpu_usage")
        self.assertGreaterEqual(len(leaderboard), 1)
        self.assertIn("model_used", leaderboard[0])
        self.assertIn("avg_rmse", leaderboard[0])

    def test_get_accuracy_trend_returns_list(self):
        result = self.store.get_accuracy_trend("cpu_usage", days=30)
        self.assertIsInstance(result, list)

    def test_get_recent_anomalies_initially_empty(self):
        result = self.store.get_recent_anomalies(limit=10)
        self.assertEqual(len(result), 0)

    def test_get_recent_anomalies_obeys_limit(self):
        for i in range(5):
            self.store.store_anomaly(_make_anomaly(severity=i + 1))
        result = self.store.get_recent_anomalies(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_pending_recommendations_excludes_applied(self):
        rid = self.store.store_recommendation(_make_recommendation())
        before = len(self.store.get_pending_recommendations())
        self.store.mark_recommendation_applied(rid)
        after = len(self.store.get_pending_recommendations())
        self.assertEqual(after, before - 1)

    def test_mark_recommendation_applied_returns_true(self):
        rid = self.store.store_recommendation(_make_recommendation())
        self.assertTrue(self.store.mark_recommendation_applied(rid))

    def test_mark_recommendation_applied_nonexistent_returns_false(self):
        self.assertFalse(self.store.mark_recommendation_applied("nonexistent-xyz"))

    def test_get_recent_forecasts_obeys_limit(self):
        for _ in range(5):
            self.store.store_forecast(_make_forecast())
        result = self.store.get_recent_forecasts(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_recent_simulations_obeys_limit(self):
        for _ in range(5):
            self.store.store_simulation(_make_simulation())
        result = self.store.get_recent_simulations(limit=3)
        self.assertEqual(len(result), 3)

    def test_prune_old_records_returns_int(self):
        result = self.store.prune_old_records(days=90)
        self.assertIsInstance(result, int)

    def test_prune_with_days_zero_removes_all(self):
        self.store.store_forecast(_make_forecast())
        self.store.store_anomaly(_make_anomaly())
        pruned = self.store.prune_old_records(days=0)
        self.assertGreater(pruned, 0)
        self.assertEqual(len(self.store.get_recent_forecasts(limit=100)), 0)


# ─────────────────────────────────────────────────────────────
# TestTimeSeriesForecaster
# ─────────────────────────────────────────────────────────────
class TestTimeSeriesForecaster(unittest.TestCase):
    def setUp(self):
        self.forecaster = TimeSeriesForecaster()

    def test_forecast_empty_data_returns_none_model(self):
        result = self.forecaster.forecast("cpu_usage", [])
        self.assertIsInstance(result, ForecastResult)
        self.assertEqual(len(result.values), 0)
        self.assertEqual(result.model_used, "none")

    def test_forecast_one_point_returns_empty(self):
        result = self.forecaster.forecast("memory_usage", [50.0])
        self.assertEqual(len(result.values), 0)

    def test_forecast_two_points_returns_empty(self):
        result = self.forecaster.forecast("error_rate", [1.0, 2.0])
        self.assertEqual(len(result.values), 0)

    def test_forecast_three_points_returns_values(self):
        result = self.forecaster.forecast("cpu_usage", [50.0, 55.0, 60.0], periods=3)
        self.assertIsInstance(result, ForecastResult)
        self.assertGreater(len(result.values), 0)

    def test_forecast_returns_correct_periods_count(self):
        data = list(range(10, 20))
        result = self.forecaster.forecast("cpu_usage", data, periods=5)
        self.assertEqual(len(result.values), 5)

    def test_forecast_timestamps_length_matches_periods(self):
        data = list(range(5, 15))
        result = self.forecaster.forecast("memory_usage", data, periods=7)
        self.assertEqual(len(result.timestamps), 7)

    def test_forecast_confidence_bounds_same_length_as_values(self):
        data = [50 + i * 0.5 for i in range(10)]
        result = self.forecaster.forecast("cpu_usage", data, periods=5)
        self.assertEqual(len(result.confidence_lower), len(result.values))
        self.assertEqual(len(result.confidence_upper), len(result.values))

    def test_forecast_model_used_in_valid_set(self):
        valid_models = {"prophet", "arima", "ensemble", "moving_average", "naive", "none"}
        data = [30 + i for i in range(10)]
        result = self.forecaster.forecast("cpu_usage", data, periods=5)
        self.assertIn(result.model_used, valid_models)

    def test_forecast_metric_name_preserved(self):
        result = self.forecaster.forecast("error_rate", [1.0, 2.0, 3.0, 4.0, 5.0], periods=3)
        self.assertEqual(result.metric_name, "error_rate")

    def test_forecast_all_returns_14_metrics(self):
        results = self.forecaster.forecast_all()
        self.assertEqual(len(results), 14)

    def test_forecast_all_keys_match_forecast_metrics(self):
        results = self.forecaster.forecast_all()
        for key in FORECAST_METRICS:
            self.assertIn(key, results)

    def test_forecast_all_values_are_forecast_result(self):
        results = self.forecaster.forecast_all()
        for metric_name, result in results.items():
            self.assertIsInstance(result, ForecastResult, f"{metric_name} must be ForecastResult")

    def test_compute_confidence_intervals_ci80_only(self):
        result = self.forecaster.compute_confidence_intervals([10.0, 20.0, 30.0], ci_80=True, ci_95=False)
        self.assertIn("ci_80_lower", result)
        self.assertIn("ci_80_upper", result)
        self.assertNotIn("ci_95_lower", result)

    def test_compute_confidence_intervals_ci95_only(self):
        result = self.forecaster.compute_confidence_intervals([10.0, 20.0, 30.0], ci_80=False, ci_95=True)
        self.assertIn("ci_95_lower", result)
        self.assertIn("ci_95_upper", result)
        self.assertNotIn("ci_80_lower", result)

    def test_compute_confidence_intervals_both(self):
        result = self.forecaster.compute_confidence_intervals([5.0, 10.0, 15.0, 20.0])
        self.assertIn("ci_80_lower", result)
        self.assertIn("ci_95_lower", result)

    def test_compute_confidence_intervals_length_matches_input(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = self.forecaster.compute_confidence_intervals(values)
        self.assertEqual(len(result["ci_80_lower"]), 5)
        self.assertEqual(len(result["ci_95_upper"]), 5)

    def test_compute_confidence_intervals_empty_returns_empty_lists(self):
        result = self.forecaster.compute_confidence_intervals([])
        self.assertEqual(result["ci_80_lower"], [])
        self.assertEqual(result["ci_95_upper"], [])

    def test_calculate_accuracy_returns_float(self):
        actual = [10.0, 20.0, 30.0, 40.0, 50.0]
        predicted = [11.0, 19.0, 31.0, 39.0, 51.0]
        result = self.forecaster.calculate_accuracy(actual, predicted)
        self.assertIsInstance(result, float)

    def test_calculate_accuracy_empty_returns_zero(self):
        self.assertEqual(self.forecaster.calculate_accuracy([], []), 0.0)

    def test_calculate_accuracy_non_negative(self):
        actual = [50.0, 60.0, 70.0]
        predicted = [45.0, 65.0, 68.0]
        result = self.forecaster.calculate_accuracy(actual, predicted)
        self.assertGreaterEqual(result, 0.0)

    def test_forecast_metrics_dict_has_14_entries(self):
        self.assertEqual(len(FORECAST_METRICS), 14)

    def test_forecast_metrics_contains_key_metrics(self):
        for key in ("cpu_usage", "energy_level", "security_incident_rate", "daily_budget_remaining"):
            self.assertIn(key, FORECAST_METRICS)


# ─────────────────────────────────────────────────────────────
# TestAnomalyPredictor
# ─────────────────────────────────────────────────────────────
class TestAnomalyPredictor(unittest.TestCase):
    def setUp(self):
        self.predictor = AnomalyPredictor()

    def test_detect_one_point_returns_empty(self):
        self.assertEqual(self.predictor.detect("cpu", [50.0]), [])

    def test_detect_two_points_returns_empty(self):
        self.assertEqual(self.predictor.detect("cpu", [50.0, 51.0]), [])

    def test_detect_spike_returns_anomalies(self):
        values = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11, 13, 10]
        result = self.predictor.detect("cpu_usage", values)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_detect_all_are_metric_anomaly_instances(self):
        values = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11]
        result = self.predictor.detect("cpu_usage", values)
        for a in result:
            self.assertIsInstance(a, MetricAnomaly)

    def test_detect_anomaly_types_are_enum(self):
        values = [10, 12, 11, 50, 11, 12, 10, 13, 11]
        result = self.predictor.detect("cpu_usage", values)
        for a in result:
            self.assertIsInstance(a.anomaly_type, AnomalyType)

    def test_detect_severity_in_1_to_10(self):
        values = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11]
        result = self.predictor.detect("cpu_usage", values)
        for a in result:
            self.assertGreaterEqual(a.severity, 1)
            self.assertLessEqual(a.severity, 10)

    def test_detect_sorted_highest_severity_first(self):
        values = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11, 10, 12]
        result = self.predictor.detect("cpu_usage", values)
        if len(result) >= 2:
            self.assertGreaterEqual(result[0].severity, result[-1].severity)

    def test_detect_frozen_values_triggers_missing_expected(self):
        values = [50.0, 50.0, 50.0, 50.0, 50.0]
        result = self.predictor.detect("frozen_metric", values)
        types = [a.anomaly_type for a in result]
        self.assertIn(AnomalyType.MISSING_EXPECTED, types)

    def test_detect_trend_divergence_detected(self):
        values = [1, 1.1, 1.2, 1.3, 1.4, 10, 11, 12, 13, 14]
        result = self.predictor.detect("drift_test", values)
        self.assertGreater(len(result), 0)

    def test_detect_confidence_in_0_to_1(self):
        values = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11]
        result = self.predictor.detect("cpu_usage", values)
        for a in result:
            self.assertGreaterEqual(a.confidence, 0.0)
            self.assertLessEqual(a.confidence, 1.0)

    def test_detect_with_explicit_timestamps(self):
        values = [10, 12, 11, 13, 10, 12, 11, 50, 12]
        now = datetime.now(timezone.utc)
        timestamps = [(now - timedelta(hours=i)).isoformat() for i in range(len(values))]
        result = self.predictor.detect("cpu_usage", values, timestamps=timestamps)
        self.assertIsInstance(result, list)

    def test_analyze_large_deviation_returns_anomaly(self):
        forecast = _make_forecast(values=[50.0, 50.0, 50.0])
        actual = [100.0, 100.0, 100.0]
        result = self.predictor.analyze(forecast, actual)
        self.assertGreater(len(result), 0)

    def test_analyze_empty_actual_returns_empty(self):
        self.assertEqual(self.predictor.analyze(_make_forecast(), []), [])

    def test_analyze_within_threshold_returns_empty(self):
        forecast = _make_forecast(values=[50.0, 51.0, 52.0])
        actual = [50.5, 51.5, 52.5]  # <1% deviation, well under 30% threshold
        result = self.predictor.analyze(forecast, actual)
        self.assertEqual(len(result), 0)

    def test_estimate_cause_returns_non_empty_string(self):
        result = self.predictor._estimate_cause("cpu", 50.0, 100.0, {})
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_estimate_cause_extreme_deviation_in_message(self):
        result = self.predictor._estimate_cause("cpu", 10.0, 100.0, {})
        self.assertIn("extreme", result.lower())

    def test_estimate_cause_rise_in_message(self):
        result = self.predictor._estimate_cause("cpu", 40.0, 80.0, {})
        self.assertIn("rise", result.lower())

    def test_estimate_cause_drop_in_message(self):
        result = self.predictor._estimate_cause("cpu", 80.0, 20.0, {})
        self.assertIn("drop", result.lower())

    def test_anomaly_type_enum_values(self):
        self.assertEqual(AnomalyType.VALUE_OUT_OF_RANGE.value, "value_out_of_range")
        self.assertEqual(AnomalyType.TREND_DIVERGENCE.value, "trend_divergence")
        self.assertEqual(AnomalyType.COMPOUND_ANOMALY.value, "compound_anomaly")
        self.assertEqual(AnomalyType.MISSING_EXPECTED.value, "missing_expected")


# ─────────────────────────────────────────────────────────────
# TestStrategyRecommender
# ─────────────────────────────────────────────────────────────
class TestStrategyRecommender(unittest.TestCase):
    def setUp(self):
        self.recommender = StrategyRecommender()

    def test_evaluate_no_args_returns_list(self):
        result = self.recommender.evaluate()
        self.assertIsInstance(result, list)

    def test_evaluate_severe_anomaly_generates_recommendation(self):
        result = self.recommender.evaluate(anomalies=[_make_anomaly(severity=8)])
        self.assertGreater(len(result), 0)

    def test_evaluate_returns_recommendation_instances(self):
        result = self.recommender.evaluate(anomalies=[_make_anomaly(severity=7)])
        for r in result:
            self.assertIsInstance(r, Recommendation)

    def test_evaluate_sorted_by_priority_ascending(self):
        forecast = _make_forecast(values=[95.0] * 7)
        result = self.recommender.evaluate(forecast=forecast, anomalies=[_make_anomaly(severity=9)])
        if len(result) >= 2:
            priorities = [r.priority for r in result]
            self.assertEqual(priorities, sorted(priorities))

    def test_evaluate_priority_in_1_to_5(self):
        result = self.recommender.evaluate(anomalies=[_make_anomaly(severity=7)])
        for r in result:
            self.assertGreaterEqual(r.priority, 1)
            self.assertLessEqual(r.priority, 5)

    def test_evaluate_recommendation_type_is_enum(self):
        result = self.recommender.evaluate(anomalies=[_make_anomaly(severity=8)])
        for r in result:
            self.assertIsInstance(r.recommendation_type, RecommendationType)

    def test_evaluate_cpu_near_critical_triggers_threshold_rec(self):
        # CPU critical_high=90; values ≥ 81 (90*0.9) trigger approaching_critical
        forecast = _make_forecast(metric_name="cpu_usage",
                                  values=[85.0, 87.0, 89.0, 91.0, 93.0, 95.0, 97.0])
        result = self.recommender.evaluate(forecast=forecast)
        self.assertGreater(len(result), 0)
        titles = [r.title for r in result]
        self.assertTrue(any("cpu_usage" in t for t in titles))

    def test_evaluate_security_anomaly_generates_security_warning(self):
        anomaly = _make_anomaly(metric_name="security_incident_rate", severity=8)
        result = self.recommender.evaluate(anomalies=[anomaly])
        types = [r.recommendation_type for r in result]
        self.assertIn(RecommendationType.SECURITY_WARNING, types)

    def test_generate_all_returns_list(self):
        result = self.recommender.generate_all({}, [], [])
        self.assertIsInstance(result, list)

    def test_generate_all_sorted_by_priority_ascending(self):
        forecast = _make_forecast("cpu_usage")
        result = self.recommender.generate_all(
            {"cpu_usage": forecast}, [_make_anomaly(severity=8)], []
        )
        if len(result) >= 2:
            priorities = [r.priority for r in result]
            self.assertEqual(priorities, sorted(priorities))

    def test_generate_all_deadline_forecast_adds_time_management(self):
        forecast = _make_forecast("deadline_proximity",
                                  values=[12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0])
        result = self.recommender.generate_all({"deadline_proximity": forecast}, [], [])
        types = [r.recommendation_type for r in result]
        self.assertIn(RecommendationType.TIME_MANAGEMENT, types)

    def test_generate_all_low_energy_adds_health_action(self):
        forecast = _make_forecast("energy_level",
                                  values=[30.0, 28.0, 25.0, 22.0, 20.0, 18.0, 15.0])
        result = self.recommender.generate_all({"energy_level": forecast}, [], [])
        types = [r.recommendation_type for r in result]
        self.assertIn(RecommendationType.HEALTH_ACTION, types)

    def test_generate_all_low_budget_adds_risk_mitigation(self):
        forecast = _make_forecast("daily_budget_remaining",
                                  values=[40.0, 35.0, 30.0, 25.0, 20.0, 15.0, 10.0])
        result = self.recommender.generate_all({"daily_budget_remaining": forecast}, [], [])
        types = [r.recommendation_type for r in result]
        self.assertIn(RecommendationType.RISK_MITIGATION, types)

    def test_generate_all_high_severity_anomaly_adds_risk_or_maintenance(self):
        result = self.recommender.generate_all(
            {"cpu_usage": _make_forecast("cpu_usage")}, [_make_anomaly(severity=8)], []
        )
        self.assertGreater(len(result), 0)
        types = [r.recommendation_type for r in result]
        self.assertTrue(
            RecommendationType.RISK_MITIGATION in types or
            RecommendationType.SYSTEM_MAINTENANCE in types
        )

    def test_recommendation_dataclass_required_fields(self):
        rec = _make_recommendation()
        self.assertIsInstance(rec.recommendation_type, RecommendationType)
        self.assertIsInstance(rec.title, str)
        self.assertIsInstance(rec.description, str)
        self.assertIsInstance(rec.priority, int)
        self.assertIsInstance(rec.metric, str)
        self.assertIsInstance(rec.confidence, float)
        self.assertIsInstance(rec.actions, list)

    def test_recommendation_type_enum_string_values(self):
        self.assertEqual(RecommendationType.TIME_MANAGEMENT.value, "time_management")
        self.assertEqual(RecommendationType.SECURITY_WARNING.value, "security_warning")
        self.assertEqual(RecommendationType.LIFESTYLE_SUGGESTION.value, "lifestyle_suggestion")


# ─────────────────────────────────────────────────────────────
# TestCausalSimulator
# ─────────────────────────────────────────────────────────────
class TestCausalSimulator(unittest.TestCase):
    def setUp(self):
        self.simulator = CausalSimulator()

    def _params(self):
        return {
            "base_value": 100.0,
            "parameters": {
                "demand": {"distribution": "normal", "mean": 5.0, "std": 2.0, "weight": 1.0},
                "cost": {"distribution": "uniform", "low": -3.0, "high": 1.0, "weight": 0.5},
            },
        }

    def test_run_monte_carlo_returns_simulation_result(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=100)
        self.assertIsInstance(result, SimulationResult)

    def test_run_monte_carlo_scenario_name_preserved(self):
        result = self.simulator.run_monte_carlo("my_metric", self._params(), iterations=50)
        self.assertEqual(result.scenario_name, "my_metric")

    def test_run_monte_carlo_iterations_bounded(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=200)
        self.assertGreater(result.iterations, 0)
        self.assertLessEqual(result.iterations, 200)

    def test_run_monte_carlo_mean_is_float(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=100)
        self.assertIsInstance(result.mean_outcome, float)

    def test_run_monte_carlo_confidence_interval_is_2_tuple(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=100)
        self.assertIsInstance(result.confidence_interval, tuple)
        self.assertEqual(len(result.confidence_interval), 2)

    def test_run_monte_carlo_ci_lower_le_upper(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=200)
        lo, hi = result.confidence_interval
        self.assertLessEqual(lo, hi)

    def test_run_monte_carlo_risk_factors_list(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=100)
        self.assertIsInstance(result.risk_factors, list)

    def test_run_monte_carlo_outcomes_have_outcome_key(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=50)
        for outcome in result.outcomes[:5]:
            self.assertIn("_outcome", outcome)

    def test_run_monte_carlo_triangular_distribution(self):
        params = {
            "base_value": 50.0,
            "parameters": {
                "x": {"distribution": "triangular", "mode": 2.0, "low": -1.0, "high": 5.0, "weight": 1.0},
            },
        }
        result = self.simulator.run_monte_carlo("triangular_test", params, iterations=100)
        self.assertIsInstance(result, SimulationResult)
        self.assertGreater(result.iterations, 0)

    def test_evaluate_risk_returns_float(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=200)
        risk = self.simulator.evaluate_risk(result, threshold=110.0)
        self.assertIsInstance(risk, float)

    def test_evaluate_risk_probability_in_0_to_1(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=200)
        risk = self.simulator.evaluate_risk(result, threshold=110.0)
        self.assertGreaterEqual(risk, 0.0)
        self.assertLessEqual(risk, 1.0)

    def test_evaluate_risk_very_high_threshold_near_zero(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=200)
        risk = self.simulator.evaluate_risk(result, threshold=1e9)
        self.assertAlmostEqual(risk, 0.0, places=3)

    def test_evaluate_risk_very_low_threshold_is_one(self):
        result = self.simulator.run_monte_carlo("test", self._params(), iterations=200)
        risk = self.simulator.evaluate_risk(result, threshold=-1e9)
        self.assertAlmostEqual(risk, 1.0, places=3)

    def test_evaluate_risk_empty_result_returns_zero(self):
        empty = SimulationResult(scenario_name="empty", iterations=0, outcomes=[])
        risk = self.simulator.evaluate_risk(empty, threshold=50.0)
        self.assertEqual(risk, 0.0)

    def test_suggest_scenarios_returns_at_least_3(self):
        result = self.simulator.suggest_scenarios()
        self.assertGreaterEqual(len(result), 3)

    def test_suggest_scenarios_all_have_name_and_parameters(self):
        result = self.simulator.suggest_scenarios()
        for scenario in result:
            self.assertIn("name", scenario)
            self.assertIn("parameters", scenario)

    def test_suggest_scenarios_includes_high_load(self):
        names = [s["name"] for s in self.simulator.suggest_scenarios()]
        self.assertIn("high_load", names)

    def test_run_custom_scenario_basic(self):
        result = self.simulator.run_custom_scenario("custom_test", {
            "base_value": 100.0,
            "parameters": {"x": {"distribution": "normal", "mean": 0.0, "std": 1.0, "weight": 1.0}},
            "iterations": 50,
        })
        self.assertIsInstance(result, SimulationResult)
        self.assertGreater(result.iterations, 0)

    def test_load_scenario_nonexistent_creates_template(self):
        result = self.simulator.load_scenario("test_nonexistent_scenario_spec10")
        self.assertIsNotNone(result)
        self.assertIn("name", result)
        self.assertIn("parameters", result)

    def test_normal_outcome_returns_float(self):
        self.assertIsInstance(self.simulator._normal_outcome(10.0, 2.0), float)

    def test_uniform_outcome_in_range(self):
        val = self.simulator._uniform_outcome(0.0, 10.0)
        self.assertIsInstance(val, float)
        self.assertGreaterEqual(val, 0.0)
        self.assertLessEqual(val, 10.0)

    def test_triangular_outcome_in_range(self):
        val = self.simulator._triangular_outcome(5.0, 0.0, 10.0)
        self.assertIsInstance(val, float)
        self.assertGreaterEqual(val, 0.0)
        self.assertLessEqual(val, 10.0)

    def test_simulation_result_dataclass_fields(self):
        sim = _make_simulation()
        self.assertIsInstance(sim.scenario_name, str)
        self.assertIsInstance(sim.iterations, int)
        self.assertIsInstance(sim.mean_outcome, float)
        self.assertIsInstance(sim.confidence_interval, tuple)
        self.assertIsInstance(sim.outcomes, list)
        self.assertIsInstance(sim.risk_factors, list)
        self.assertIsInstance(sim.converged, bool)


# ─────────────────────────────────────────────────────────────
# TestPredictiveIntegration
# ─────────────────────────────────────────────────────────────
class TestPredictiveIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.store = PredictionStore(self._tmp.name)
        self.forecaster = TimeSeriesForecaster()
        self.predictor = AnomalyPredictor()
        self.recommender = StrategyRecommender()
        self.simulator = CausalSimulator()

    def tearDown(self):
        self.store.close()
        Path(self._tmp.name).unlink(missing_ok=True)

    def test_forecast_store_retrieve_cycle(self):
        data = [50 + i * 2 for i in range(10)]
        forecast = self.forecaster.forecast("cpu_usage", data, periods=5)
        self.store.store_forecast(forecast)
        retrieved = self.store.get_recent_forecasts(limit=1)
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["metric_name"], "cpu_usage")

    def test_anomaly_store_retrieve_count(self):
        values = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11]
        anomalies = self.predictor.detect("cpu_usage", values)
        for a in anomalies:
            self.store.store_anomaly(a)
        retrieved = self.store.get_recent_anomalies(limit=20)
        self.assertEqual(len(retrieved), len(anomalies))

    def test_check_accuracy_after_forecast_store(self):
        data = [80 + i for i in range(10)]
        forecast = self.forecaster.forecast("cpu_usage", data, periods=5)
        fid = self.store.store_forecast(forecast)
        acc = self.store.check_accuracy(fid, 85.0)
        self.assertIn("rmse", acc)
        self.assertIn("mae", acc)

    def test_recommendation_appears_in_pending(self):
        rid = self.store.store_recommendation(_make_recommendation())
        pending_ids = [r["id"] for r in self.store.get_pending_recommendations()]
        self.assertIn(rid, pending_ids)

    def test_applied_recommendation_leaves_pending(self):
        rid = self.store.store_recommendation(_make_recommendation())
        self.store.mark_recommendation_applied(rid)
        pending_ids = [r["id"] for r in self.store.get_pending_recommendations()]
        self.assertNotIn(rid, pending_ids)

    def test_simulation_store_retrieve_cycle(self):
        params = {
            "base_value": 100.0,
            "parameters": {"x": {"distribution": "normal", "mean": 2.0, "std": 1.0, "weight": 1.0}},
        }
        sim_result = self.simulator.run_monte_carlo("integration_test", params, iterations=100)
        self.store.store_simulation(sim_result)
        retrieved = self.store.get_recent_simulations(limit=1)
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0]["scenario_name"], "integration_test")

    def test_full_pipeline_forecast_anomaly_recommendation(self):
        data = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11, 13, 10]
        forecast = self.forecaster.forecast("cpu_usage", data, periods=5)
        anomalies = self.predictor.detect("cpu_usage", data)
        recs = self.recommender.evaluate(forecast=forecast, anomalies=anomalies)
        self.store.store_forecast(forecast)
        for a in anomalies:
            self.store.store_anomaly(a)
        for r in recs:
            self.store.store_recommendation(r)
        self.assertEqual(len(self.store.get_recent_forecasts(limit=5)), 1)
        self.assertEqual(len(self.store.get_recent_anomalies(limit=20)), len(anomalies))
        self.assertGreater(len(self.store.get_pending_recommendations()), 0)

    def test_generate_all_recs_storeable(self):
        predictions = self.forecaster.forecast_all()
        anomalies = self.predictor.detect("cpu_usage", [10, 12, 11, 13, 10, 12, 11, 50, 12, 11])
        recs = self.recommender.generate_all(predictions, anomalies, [])
        for r in recs:
            self.store.store_recommendation(r)
        self.assertGreaterEqual(len(self.store.get_pending_recommendations()), len(recs))

    def test_prune_removes_stored_forecast(self):
        forecast = self.forecaster.forecast("cpu_usage", [50, 55, 60, 65, 70], periods=3)
        self.store.store_forecast(forecast)
        pruned = self.store.prune_old_records(days=0)
        self.assertGreater(pruned, 0)
        self.assertEqual(len(self.store.get_recent_forecasts(limit=100)), 0)

    def test_leaderboard_populated_after_check(self):
        data = [60 + i for i in range(10)]
        forecast = self.forecaster.forecast("memory_usage", data, periods=5)
        fid = self.store.store_forecast(forecast)
        self.store.check_accuracy(fid, 65.0)
        leaderboard = self.store.get_model_leaderboard("memory_usage")
        self.assertGreater(len(leaderboard), 0)

    def test_monte_carlo_risk_end_to_end(self):
        params = {
            "base_value": 100.0,
            "parameters": {
                "volatility": {"distribution": "normal", "mean": 5.0, "std": 10.0, "weight": 1.0},
            },
        }
        sim_result = self.simulator.run_monte_carlo("risk_test", params, iterations=500)
        self.store.store_simulation(sim_result)
        risk = self.simulator.evaluate_risk(sim_result, threshold=120.0)
        self.assertGreaterEqual(risk, 0.0)
        self.assertLessEqual(risk, 1.0)


if __name__ == "__main__":
    unittest.main()
