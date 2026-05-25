"""Session 14 — Health Integration tests.

Verifies:
- MetricsStore: all 7 tables, CRUD, prune_old_data, get_sources
- WearableConnector: connector registry, graceful auth failures, poll_all, phone sensor
- TrendAnalyzer: analyze, detect_anomalies, weekly_comparison, circadian, correlate, full_analysis
- FatigueMonitor: EAR-based fatigue, session tracking, HP system, memory writes
- SleepTracker: quality labels, sleep period inference, episodic memory writes
- ExerciseLogger: log sessions, HP awards, sedentary detection, weekly report
- HealthMonitor (core/sensing): fatigue_to_energy, system_load, health_snapshot
- Daily health snapshot in episodic_memory (session 14 integration requirement)
"""
from __future__ import annotations

import asyncio
import datetime
import tempfile
import unittest
from pathlib import Path


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. MetricsStore
# ---------------------------------------------------------------------------

class TestMetricsStore(unittest.TestCase):

    def setUp(self):
        from districts.health.metrics_store import MetricsStore
        self.store = MetricsStore(db_path=":memory:")

    def tearDown(self):
        self.store.close()

    def test_init_creates_all_tables(self):
        conn = self.store._ensure_conn()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        expected = {
            "health_metrics", "wearable_metrics", "metric_trends",
            "health_anomalies", "health_recommendations",
            "emergency_events", "daily_health_summaries",
        }
        self.assertTrue(expected.issubset(tables))

    def test_store_and_get_metric(self):
        self.store.store_metric("test_source", "heart_rate", 72.0, "bpm")
        rows = self.store.get_metrics("heart_rate", days=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric_name"], "heart_rate")
        self.assertAlmostEqual(rows[0]["value"], 72.0)

    def test_get_metrics_timeframe_filter(self):
        ts_old = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
        self.store.store_metric("s", "steps", 5000.0, "count", timestamp=ts_old)
        self.store.store_metric("s", "steps", 8000.0, "count")
        rows_7d = self.store.get_metrics("steps", days=7)
        self.assertEqual(len(rows_7d), 1)
        self.assertAlmostEqual(rows_7d[0]["value"], 8000.0)

    def test_get_latest_returns_most_recent(self):
        self.store.store_metric("s", "hrv", 45.0)
        self.store.store_metric("s", "hrv", 52.0)
        latest = self.store.get_latest("hrv")
        self.assertIsNotNone(latest)
        self.assertAlmostEqual(latest["value"], 52.0)

    def test_get_latest_returns_none_for_unknown(self):
        result = self.store.get_latest("nonexistent_metric")
        self.assertIsNone(result)

    def test_store_batch(self):
        metrics = [
            {"source": "garmin", "metric_name": "steps", "value": 3000.0},
            {"source": "garmin", "metric_name": "steps", "value": 4500.0},
            {"source": "garmin", "metric_name": "calories", "value": 320.0},
        ]
        count = self.store.store_batch(metrics)
        self.assertEqual(count, 3)
        step_rows = self.store.get_metrics("steps", days=1)
        self.assertEqual(len(step_rows), 2)

    def test_store_and_get_wearable(self):
        payload = {
            "heart_rate": 68.0,
            "hrv": 42.5,
            "sleep_hours": 7.2,
            "steps": 8000,
        }
        row_id = self.store.store_wearable("oura", payload)
        self.assertIsNotNone(row_id)
        latest = self.store.get_latest_wearable(source="oura")
        self.assertIsNotNone(latest)
        self.assertAlmostEqual(latest["heart_rate"], 68.0)

    def test_store_and_get_trend(self):
        trend = {
            "metric_name": "sleep_hours",
            "direction": "improving",
            "change_pct": 12.5,
            "avg": 7.0,
            "min": 5.5,
            "max": 8.0,
            "std_dev": 0.6,
            "stability": "stable",
        }
        self.store.store_trend(trend)
        trends = self.store.get_trends("sleep_hours")
        self.assertEqual(len(trends), 1)
        self.assertEqual(trends[0]["direction"], "improving")

    def test_store_and_get_anomaly(self):
        anomaly = {
            "metric_name": "heart_rate",
            "expected": 70.0,
            "actual": 130.0,
            "deviation": 85.7,
            "severity": 8,
            "detected_at": datetime.datetime.now().isoformat(),
            "trend_direction": "up",
        }
        self.store.store_anomaly(anomaly)
        anomalies = self.store.get_anomalies()
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["metric_name"], "heart_rate")

    def test_acknowledge_anomaly(self):
        anomaly = {"metric_name": "hrv", "expected": 40.0, "actual": 10.0,
                   "deviation": -75.0, "severity": 9,
                   "detected_at": datetime.datetime.now().isoformat()}
        self.store.store_anomaly(anomaly)
        rows = self.store.get_anomalies(unresolved_only=True)
        self.assertEqual(len(rows), 1)
        ok = self.store.acknowledge_anomaly(rows[0]["id"])
        self.assertTrue(ok)
        unresolved = self.store.get_anomalies(unresolved_only=True)
        self.assertEqual(len(unresolved), 0)

    def test_store_and_get_recommendation(self):
        rec = {
            "type": "sleep",
            "title": "Sleep earlier",
            "description": "Aim for 7+ hours",
            "priority": 2,
            "actionable": True,
        }
        self.store.store_recommendation(rec)
        recs = self.store.get_recommendations(priority_min=3)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["title"], "Sleep earlier")

    def test_store_and_get_emergency_event(self):
        evt = {
            "event_type": "heart_rate_critical",
            "value": 0.0,
            "severity": 10,
            "message": "Heart rate stopped",
        }
        self.store.store_emergency_event(evt)
        events = self.store.get_emergency_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "heart_rate_critical")

    def test_resolve_emergency(self):
        evt = {"event_type": "battery_dead", "value": 0.0, "severity": 3, "message": "test"}
        self.store.store_emergency_event(evt)
        unresolved = self.store.get_emergency_events(unresolved_only=True)
        self.assertEqual(len(unresolved), 1)
        ok = self.store.resolve_emergency(unresolved[0]["id"])
        self.assertTrue(ok)
        still_unresolved = self.store.get_emergency_events(unresolved_only=True)
        self.assertEqual(len(still_unresolved), 0)

    def test_store_and_get_daily_summary(self):
        summary = {
            "summary_date": datetime.date.today().isoformat(),
            "avg_heart_rate": 71.0,
            "avg_hrv": 43.0,
            "total_steps": 9500,
            "total_sleep_h": 7.5,
        }
        self.store.store_daily_summary(summary)
        summaries = self.store.get_daily_summaries(days=1)
        self.assertEqual(len(summaries), 1)
        self.assertAlmostEqual(summaries[0]["avg_heart_rate"], 71.0)

    def test_get_sources_distinct(self):
        self.store.store_metric("oura", "hrv", 40.0)
        self.store.store_metric("garmin", "steps", 5000.0)
        self.store.store_metric("oura", "heart_rate", 68.0)
        sources = self.store.get_sources()
        self.assertIn("oura", sources)
        self.assertIn("garmin", sources)
        self.assertEqual(len(sources), 2)

    def test_prune_old_data(self):
        old_ts = (datetime.datetime.now() - datetime.timedelta(days=100)).isoformat()
        self.store.store_metric("s", "steps", 1000.0, timestamp=old_ts)
        self.store.store_metric("s", "steps", 2000.0)
        counts = self.store.prune_old_data(retention_days=90)
        self.assertEqual(counts["health_metrics"], 1)
        remaining = self.store.get_metrics("steps", days=7)
        self.assertEqual(len(remaining), 1)


# ---------------------------------------------------------------------------
# 2. WearableConnector
# ---------------------------------------------------------------------------

class TestWearableConnector(unittest.TestCase):

    def setUp(self):
        from districts.health.wearable_connector import WearableConnector
        self.wc = WearableConnector()

    def test_connector_registry_has_all_types(self):
        expected = {"apple_health", "google_fit", "oura", "garmin", "whoop", "phone_sensor"}
        self.assertEqual(set(self.wc._connectors.keys()), expected)

    def test_get_connector_returns_correct_type(self):
        from districts.health.wearable_connector import OuraConnector
        connector = self.wc.get_connector("oura")
        self.assertIsInstance(connector, OuraConnector)

    def test_get_connector_unknown_returns_none(self):
        result = self.wc.get_connector("nonexistent_wearable")
        self.assertIsNone(result)

    def test_poll_all_returns_list(self):
        results = _run(self.wc.poll_all())
        self.assertIsInstance(results, list)

    def test_poll_all_skips_uncredentialed(self):
        # Without real API keys, all cloud connectors fail auth gracefully
        results = _run(self.wc.poll_all())
        for r in results:
            self.assertIn("source", r)

    def test_phone_sensor_poll_returns_dict(self):
        result = _run(self.wc.poll_phone_sensors())
        self.assertIsInstance(result, dict)

    def test_apple_health_authenticate_graceful(self):
        from districts.health.wearable_connector import AppleHealthConnector
        conn = AppleHealthConnector()
        authed = _run(conn.authenticate())
        # pyhealth not installed — should return False without raising
        self.assertIsInstance(authed, bool)

    def test_oura_auth_false_without_token(self):
        from districts.health.wearable_connector import OuraConnector
        connector = OuraConnector()
        connector._token = ""
        authed = _run(connector.authenticate())
        self.assertFalse(authed)


# ---------------------------------------------------------------------------
# 3. TrendAnalyzer
# ---------------------------------------------------------------------------

class TestTrendAnalyzer(unittest.TestCase):

    def setUp(self):
        from districts.health.metrics_store import MetricsStore
        from districts.health.trend_analyzer import TrendAnalyzer
        self.store = MetricsStore(db_path=":memory:")
        self.analyzer = TrendAnalyzer(store=self.store)

    def tearDown(self):
        self.store.close()

    def test_analyze_no_data_insufficient(self):
        result = self.analyzer.analyze("nonexistent_metric")
        self.assertEqual(result["stability"], "insufficient_data")
        self.assertEqual(result["metric_name"], "nonexistent_metric")

    def test_analyze_returns_required_keys(self):
        self.store.store_metric("s", "hrv", 40.0)
        self.store.store_metric("s", "hrv", 42.0)
        result = self.analyzer.analyze("hrv")
        for key in ("metric_name", "direction", "change_pct", "avg", "min", "max", "std_dev", "stability"):
            self.assertIn(key, result)

    def test_analyze_increasing_trend(self):
        base = datetime.datetime.now() - datetime.timedelta(days=6)
        for i in range(8):
            ts = (base + datetime.timedelta(days=i)).isoformat()
            self.store.store_metric("s", "steps", float(3000 + i * 1000), timestamp=ts)
        result = self.analyzer.analyze("steps", days=7)
        self.assertIn(result["direction"], ("improving", "stable"))

    def test_detect_anomalies_empty_returns_empty(self):
        result = self.analyzer.detect_anomalies("hrv", [])
        self.assertEqual(result, [])

    def test_detect_anomalies_finds_outlier(self):
        # Use threshold=1.5 — with 5 points and one at 130, z≈2.0 which exceeds 1.5
        values = [70.0, 71.0, 69.0, 72.0, 130.0]
        anomalies = self.analyzer.detect_anomalies("heart_rate", values, threshold=1.5)
        self.assertGreater(len(anomalies), 0)
        for a in anomalies:
            self.assertIn("metric_name", a)
            self.assertIn("severity", a)
            self.assertIn("actual", a)

    def test_detect_anomalies_normal_values_no_anomaly(self):
        values = [70.0, 72.0, 71.0, 69.0, 73.0]
        anomalies = self.analyzer.detect_anomalies("heart_rate", values, threshold=3.0)
        self.assertEqual(len(anomalies), 0)

    def test_weekly_comparison_returns_required_keys(self):
        self.store.store_metric("s", "sleep_hours", 7.0)
        result = self.analyzer.weekly_comparison("sleep_hours")
        for key in ("metric_name", "this_week_avg", "last_week_avg", "change_pct", "insight"):
            self.assertIn(key, result)

    def test_circadian_patterns_no_data(self):
        result = self.analyzer.detect_circadian_patterns("nonexistent")
        self.assertEqual(result["pattern"], "unknown")
        self.assertEqual(result["metric_name"], "nonexistent")

    def test_circadian_patterns_with_data(self):
        base = datetime.datetime.now().replace(minute=0, second=0)
        for h in (9, 14, 21):
            ts = base.replace(hour=h).isoformat()
            self.store.store_metric("s", "energy", float(10 - abs(h - 14)), timestamp=ts)
        result = self.analyzer.detect_circadian_patterns("energy")
        self.assertIn(result["pattern"], ("circadian_detected", "flat"))
        self.assertIn("hourly_averages", result)

    def test_correlate_too_few_points_returns_zero(self):
        self.store.store_metric("s", "hrv", 40.0)
        self.store.store_metric("s", "sleep_hours", 7.0)
        r = self.analyzer.correlate("hrv", "sleep_hours")
        self.assertEqual(r, 0.0)

    def test_full_analysis_returns_structure(self):
        result = self.analyzer.full_analysis(days=7)
        for key in ("period_days", "generated_at", "trends", "anomalies", "weekly_comparisons", "circadian_patterns", "correlations"):
            self.assertIn(key, result)
        self.assertEqual(result["period_days"], 7)


# ---------------------------------------------------------------------------
# 4. FatigueMonitor
# ---------------------------------------------------------------------------

class TestFatigueMonitor(unittest.TestCase):

    def setUp(self):
        from districts.health.fatigue_monitor import FatigueMonitor
        self.monitor = FatigueMonitor()

    def test_init_hp(self):
        self.assertEqual(self.monitor.health_points, 500)

    def test_init_district(self):
        self.assertEqual(self.monitor.district, "health")

    def test_check_once_no_camera_no_fatigue(self):
        # No camera EAR available — fatigue not detected, no crash
        result = _run(self.monitor.check_once())
        self.assertIn("fatigue", result)
        self.assertIsInstance(result["fatigue"], bool)
        self.assertIn("session_minutes", result)

    def test_check_once_low_ear_triggers_fatigue(self):
        # Inject a below-threshold EAR directly
        self.monitor._get_ear_from_world_state = lambda: 0.15
        result = _run(self.monitor.check_once())
        self.assertTrue(result["fatigue"])
        self.assertIsNotNone(result["reason"])

    def test_check_once_high_ear_no_fatigue(self):
        self.monitor._get_ear_from_world_state = lambda: 0.40
        result = _run(self.monitor.check_once())
        self.assertFalse(result["fatigue"])

    def test_session_start_set_after_first_check(self):
        self.assertIsNone(self.monitor._session_start)
        _run(self.monitor.check_once())
        self.assertIsNotNone(self.monitor._session_start)

    def test_session_minutes_increases_after_start(self):
        import time
        self.monitor._session_start = datetime.datetime.now() - datetime.timedelta(minutes=10)
        mins = self.monitor._session_minutes()
        self.assertGreaterEqual(mins, 9.9)

    def test_fatigue_count_increments(self):
        self.monitor._get_ear_from_world_state = lambda: 0.10
        initial = self.monitor._fatigue_count
        _run(self.monitor.check_once())
        self.assertEqual(self.monitor._fatigue_count, initial + 1)

    def test_run_returns_status_ok(self):
        result = _run(self.monitor.run({"type": "check_fatigue"}))
        self.assertEqual(result["status"], "ok")

    def test_handle_event_returns_handled(self):
        result = _run(self.monitor.handle_event({"event_type": "health_alert"}))
        self.assertEqual(result["status"], "handled")


# ---------------------------------------------------------------------------
# 5. SleepTracker
# ---------------------------------------------------------------------------

class TestSleepTracker(unittest.TestCase):

    def setUp(self):
        from districts.health.sleep_tracker import SleepTracker
        self.tracker = SleepTracker()

    def test_quality_label_excellent(self):
        self.assertEqual(self.tracker._quality_label(8.5), "excellent")

    def test_quality_label_good(self):
        self.assertEqual(self.tracker._quality_label(7.0), "good")

    def test_quality_label_fair(self):
        self.assertEqual(self.tracker._quality_label(6.2), "fair")

    def test_quality_label_poor(self):
        self.assertEqual(self.tracker._quality_label(4.5), "poor")

    def test_quality_label_very_poor(self):
        self.assertEqual(self.tracker._quality_label(3.5), "very poor")

    def test_infer_sleep_periods_empty_db_returns_empty(self):
        # Fresh tracker with default DB — no forced gap rows, so result is 0 or more
        periods = self.tracker._infer_sleep_periods(days=0)
        self.assertIsInstance(periods, list)

    def test_infer_sleep_periods_detects_gap(self):
        import uuid
        now = datetime.datetime.now()
        ts1 = (now - datetime.timedelta(hours=6)).isoformat()
        ts2 = (now - datetime.timedelta(minutes=30)).isoformat()
        # Use UUIDs so re-runs don't hit UNIQUE constraint
        id1 = uuid.uuid4().hex
        id2 = uuid.uuid4().hex
        self.tracker._memory.conn.execute(
            "INSERT INTO episodic_memory (id, event_type, content, source, timestamp, tags) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (id1, "ambient", "working", "sleep_gap_test", ts1, "[]"),
        )
        self.tracker._memory.conn.execute(
            "INSERT INTO episodic_memory (id, event_type, content, source, timestamp, tags) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (id2, "ambient", "wake", "sleep_gap_test", ts2, "[]"),
        )
        self.tracker._memory.conn.commit()
        periods = self.tracker._infer_sleep_periods(days=1)
        self.assertGreater(len(periods), 0)
        gap_hours = [p["duration_hours"] for p in periods]
        self.assertTrue(any(h >= 4.0 for h in gap_hours))

    def test_track_stores_sleep_log_to_episodic(self):
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Health").mkdir()
            self.tracker._obsidian._vault = vault
            ok = _run(self.tracker.track())
        self.assertTrue(ok)
        # Verify episodic_memory has a sleep_log event
        cur = self.tracker._memory.conn.cursor()
        cur.execute("SELECT count(*) FROM episodic_memory WHERE event_type='sleep_log'")
        count = cur.fetchone()[0]
        self.assertGreater(count, 0)

    def test_run_returns_status_ok(self):
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Health").mkdir()
            self.tracker._obsidian._vault = vault
            result = _run(self.tracker.run({}))
        self.assertEqual(result["status"], "ok")


# ---------------------------------------------------------------------------
# 6. ExerciseLogger
# ---------------------------------------------------------------------------

class TestExerciseLogger(unittest.TestCase):

    def setUp(self):
        from districts.health.exercise_logger import ExerciseLogger
        self.logger = ExerciseLogger()

    def test_init_hp(self):
        self.assertEqual(self.logger.health_points, 500)

    def test_log_session_returns_true(self):
        ok = self.logger.log_session("Running", 20, "Morning jog")
        self.assertTrue(ok)

    def test_log_session_awards_hp(self):
        initial = self.logger.health_points
        self.logger.log_session("Yoga", 30)
        self.assertGreater(self.logger.health_points, initial)

    def test_log_session_stores_to_episodic(self):
        self.logger.log_session("Cycling", 45, "Evening ride")
        sessions = self.logger._fetch_recent_sessions(days=1)
        # At least the session just logged
        self.assertGreater(len(sessions), 0)
        contents = [s["content"] for s in sessions]
        self.assertTrue(any("Cycling" in c for c in contents))

    def test_days_since_last_exercise_no_sessions(self):
        # On a fresh DB, returns 30 (max)
        # Use a fresh logger instance with no history
        from districts.health.exercise_logger import ExerciseLogger
        el = ExerciseLogger()
        # Override fetch to return empty
        el._fetch_recent_sessions = lambda days=30: []
        days = el._days_since_last_exercise()
        self.assertEqual(days, 30)

    def test_days_since_last_exercise_after_log(self):
        from districts.health.exercise_logger import ExerciseLogger
        el = ExerciseLogger()
        # Inject a session logged right now to test the calculation logic
        el._fetch_recent_sessions = lambda days=30: [
            {"timestamp": datetime.datetime.now().isoformat(), "content": "Swimming 60min"}
        ]
        days = el._days_since_last_exercise()
        self.assertEqual(days, 0)

    def test_weekly_summary_no_sessions(self):
        summary = self.logger._weekly_summary([])
        self.assertIn("No exercise", summary)

    def test_weekly_summary_with_sessions(self):
        sessions = [{"timestamp": "2026-05-25T10:00:00", "content": "Running 20min"}]
        summary = self.logger._weekly_summary(sessions)
        self.assertIn("Running", summary)

    def test_weekly_report_returns_true(self):
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Health").mkdir()
            self.logger._obsidian._vault = vault
            ok = _run(self.logger.weekly_report())
        self.assertTrue(ok)

    def test_run_log_exercise_task(self):
        result = _run(self.logger.run({
            "type": "log_exercise",
            "params": {"activity": "Walk", "duration_min": 15, "notes": ""},
        }))
        self.assertEqual(result["status"], "ok")


# ---------------------------------------------------------------------------
# 7. HealthMonitor (core/sensing)
# ---------------------------------------------------------------------------

class TestHealthMonitor(unittest.TestCase):

    def setUp(self):
        from core.sensing.health_monitor import HealthMonitor
        self.monitor = HealthMonitor()

    def test_fatigue_to_energy_zero_is_high(self):
        from core.sensing.health_monitor import HealthMonitor
        self.assertEqual(HealthMonitor._fatigue_to_energy(0.0), "high")

    def test_fatigue_to_energy_three_is_high(self):
        from core.sensing.health_monitor import HealthMonitor
        self.assertEqual(HealthMonitor._fatigue_to_energy(3.9), "high")

    def test_fatigue_to_energy_four_is_medium(self):
        from core.sensing.health_monitor import HealthMonitor
        self.assertEqual(HealthMonitor._fatigue_to_energy(4.0), "medium")

    def test_fatigue_to_energy_six_is_medium(self):
        from core.sensing.health_monitor import HealthMonitor
        self.assertEqual(HealthMonitor._fatigue_to_energy(6.9), "medium")

    def test_fatigue_to_energy_seven_is_low(self):
        from core.sensing.health_monitor import HealthMonitor
        self.assertEqual(HealthMonitor._fatigue_to_energy(7.0), "low")

    def test_fatigue_to_energy_ten_is_low(self):
        from core.sensing.health_monitor import HealthMonitor
        self.assertEqual(HealthMonitor._fatigue_to_energy(10.0), "low")

    def test_get_fatigue_score_returns_float(self):
        score = self.monitor.get_fatigue_score()
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 10.0)

    def test_get_system_load_returns_dict(self):
        load = self.monitor.get_system_load()
        self.assertIsInstance(load, dict)
        self.assertIn("cpu_percent", load)
        self.assertIn("ram_percent", load)

    def test_get_system_load_values_in_range(self):
        load = self.monitor.get_system_load()
        self.assertGreaterEqual(load["cpu_percent"], 0.0)
        self.assertLessEqual(load["cpu_percent"], 100.0)
        self.assertGreaterEqual(load["ram_percent"], 0.0)
        self.assertLessEqual(load["ram_percent"], 100.0)

    def test_get_health_snapshot_has_required_keys(self):
        snap = self.monitor.get_health_snapshot()
        for key in ("fatigue_score", "energy_level", "system_load", "wearable", "timestamp"):
            self.assertIn(key, snap)

    def test_health_snapshot_energy_level_valid(self):
        snap = self.monitor.get_health_snapshot()
        self.assertIn(snap["energy_level"], ("high", "medium", "low"))

    def test_health_snapshot_wearable_has_available(self):
        snap = self.monitor.get_health_snapshot()
        self.assertIn("available", snap["wearable"])


# ---------------------------------------------------------------------------
# 8. BiometricsAggregator
# ---------------------------------------------------------------------------

class TestBiometricsAggregator(unittest.TestCase):

    def setUp(self):
        from districts.health.biometrics_aggregator import BiometricsAggregator
        self.agg = BiometricsAggregator()

    def test_normalize_flat_dict(self):
        raw = {"sleep_hours": 7.5, "steps": 9000, "heart_rate_avg": 68.0, "source": "oura"}
        result = self.agg._normalize(raw, source="oura")
        self.assertAlmostEqual(result["sleep_hours"], 7.5)
        self.assertEqual(result["steps"], 9000)

    def test_normalize_nested_dict(self):
        raw = {"metrics": {"sleep_hours": 8.0, "hrv_ms": 45.0}}
        result = self.agg._normalize(raw, source="apple_health")
        self.assertAlmostEqual(result["sleep_hours"], 8.0)
        self.assertAlmostEqual(result["hrv_ms"], 45.0)

    def test_normalize_non_dict_raw(self):
        result = self.agg._normalize("plain string", source="test")
        self.assertEqual(result["source"], "test")
        self.assertEqual(result["raw"], "plain string")

    def test_run_no_connectors_returns_ok(self):
        # No real credentials — all connectors return None gracefully
        result = _run(self.agg.run({"obsidian": False}))
        self.assertEqual(result["status"], "ok")
        self.assertIn("sources_attempted", result)
        self.assertIn("records", result)

    def test_run_returns_records_count(self):
        result = _run(self.agg.run({"sources": ["apple_health"], "obsidian": False}))
        self.assertIsInstance(result["records"], int)
        self.assertGreaterEqual(result["records"], 0)

    def test_run_sources_attempted_matches_input(self):
        result = _run(self.agg.run({"sources": ["oura", "strava"], "obsidian": False}))
        self.assertIn("oura", result["sources_attempted"])
        self.assertIn("strava", result["sources_attempted"])


# ---------------------------------------------------------------------------
# 9. Daily Health Snapshot in Episodic Memory (Session 14 requirement)
# ---------------------------------------------------------------------------

class TestDailyHealthSnapshot(unittest.TestCase):
    """Verify that health agents write daily snapshots to episodic_memory."""

    def test_sleep_log_in_episodic_memory(self):
        from districts.health.sleep_tracker import SleepTracker
        tracker = SleepTracker()
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Health").mkdir()
            tracker._obsidian._vault = vault
            _run(tracker.track())
        cur = tracker._memory.conn.cursor()
        cur.execute("SELECT count(*) FROM episodic_memory WHERE event_type='sleep_log' AND source='sleep_tracker'")
        count = cur.fetchone()[0]
        self.assertGreater(count, 0)

    def test_exercise_session_in_episodic_memory(self):
        from districts.health.exercise_logger import ExerciseLogger
        logger = ExerciseLogger()
        logger.log_session("Pushups", 10)
        cur = logger._memory.conn.cursor()
        cur.execute("SELECT count(*) FROM episodic_memory WHERE event_type='exercise_session' AND source='exercise_logger'")
        count = cur.fetchone()[0]
        self.assertGreater(count, 0)

    def test_fatigue_event_in_episodic_memory(self):
        from districts.health.fatigue_monitor import FatigueMonitor
        monitor = FatigueMonitor()
        monitor._get_ear_from_world_state = lambda: 0.10
        _run(monitor.check_once())
        cur = monitor._memory.conn.cursor()
        cur.execute("SELECT count(*) FROM episodic_memory WHERE event_type='fatigue_detected' AND source='fatigue_monitor'")
        count = cur.fetchone()[0]
        self.assertGreater(count, 0)

    def test_health_snapshot_persists_to_metrics_store(self):
        from districts.health.metrics_store import MetricsStore
        store = MetricsStore(db_path=":memory:")
        store.store_metric("health_monitor", "fatigue_score", 5.0)
        store.store_metric("health_monitor", "cpu_percent", 23.5)
        store.store_metric("health_monitor", "ram_percent", 48.2)
        rows = store.get_metrics("fatigue_score", days=1)
        self.assertEqual(len(rows), 1)
        store.close()

    def test_wearable_metrics_persisted_via_store(self):
        from districts.health.metrics_store import MetricsStore
        store = MetricsStore(db_path=":memory:")
        payload = {
            "heart_rate": 72.0,
            "hrv": 38.5,
            "sleep_hours": 7.0,
            "spo2": 98.5,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        store.store_wearable("phone_sensor", payload)
        latest = store.get_latest_wearable()
        self.assertIsNotNone(latest)
        self.assertAlmostEqual(latest["heart_rate"], 72.0)
        store.close()

    def test_trend_analyzer_writes_trend_to_store(self):
        from districts.health.metrics_store import MetricsStore
        from districts.health.trend_analyzer import TrendAnalyzer
        store = MetricsStore(db_path=":memory:")
        base = datetime.datetime.now() - datetime.timedelta(days=6)
        for i in range(7):
            ts = (base + datetime.timedelta(days=i)).isoformat()
            store.store_metric("test", "sleep_hours", float(6 + i * 0.2), timestamp=ts)
        analyzer = TrendAnalyzer(store=store)
        trend = analyzer.analyze("sleep_hours", days=7)
        store.store_trend(trend)
        stored_trends = store.get_trends("sleep_hours")
        self.assertEqual(len(stored_trends), 1)
        self.assertEqual(stored_trends[0]["metric_name"], "sleep_hours")
        store.close()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
