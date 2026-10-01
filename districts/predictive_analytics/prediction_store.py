from core.memory.db_utils import apply_pragmas
from pathlib import Path

import sqlite3
import json
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import uuid4
import numpy as np

from loguru import logger

from districts.predictive_analytics.time_series_forecaster import ForecastResult
from districts.predictive_analytics.anomaly_predictor import MetricAnomaly, AnomalyType
from districts.predictive_analytics.strategy_recommender import Recommendation, RecommendationType

PREDICTION_RETENTION_DAYS = 90


class PredictionStore:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base = Path(__file__).parent.parent.parent / "data" / "predictive"
            base.mkdir(parents=True, exist_ok=True)
            db_path = str(base / "prediction_store.db")
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.info(f"[VECTOR][predictive_analytics] PredictionStore ready at {db_path}")

    def _create_tables(self):
        with self._lock:
            apply_pragmas(self._conn)
            cur = self._conn.cursor()
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS forecasts (
                id TEXT PRIMARY KEY,
                metric_name TEXT NOT NULL,
                model_used TEXT NOT NULL,
                accuracy_score REAL,
                timestamps TEXT NOT NULL,
                forecast_values TEXT NOT NULL,
                confidence_lower TEXT NOT NULL,
                confidence_upper TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS anomalies (
                id TEXT PRIMARY KEY,
                metric_name TEXT NOT NULL,
                anomaly_type TEXT NOT NULL,
                severity INTEGER NOT NULL,
                detected_at TEXT NOT NULL,
                expected_value REAL NOT NULL,
                actual_value REAL NOT NULL,
                confidence REAL NOT NULL,
                cause TEXT DEFAULT '',
                resolved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id TEXT PRIMARY KEY,
                metric TEXT NOT NULL,
                rec_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                priority INTEGER NOT NULL,
                confidence REAL NOT NULL,
                actions TEXT NOT NULL,
                evidence TEXT DEFAULT '[]',
                actionable INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT,
                source TEXT DEFAULT 'predictive_analytics',
                is_applied INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS simulations (
                id TEXT PRIMARY KEY,
                scenario_name TEXT NOT NULL,
                iterations INTEGER NOT NULL,
                mean_outcome REAL NOT NULL,
                ci_lower REAL NOT NULL,
                ci_upper REAL NOT NULL,
                converged INTEGER NOT NULL DEFAULT 0,
                outcomes TEXT NOT NULL DEFAULT '[]',
                risk_factors TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS prediction_accuracy (
                id TEXT PRIMARY KEY,
                forecast_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                model_used TEXT NOT NULL,
                rmse REAL,
                mae REAL,
                mape REAL,
                actual_value REAL NOT NULL,
                predicted_value REAL NOT NULL,
                computed_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_forecasts_metric ON forecasts(metric_name);
            CREATE INDEX IF NOT EXISTS idx_forecasts_created ON forecasts(created_at);
            CREATE INDEX IF NOT EXISTS idx_anomalies_metric ON anomalies(metric_name);
            CREATE INDEX IF NOT EXISTS idx_anomalies_detected ON anomalies(detected_at);
            CREATE INDEX IF NOT EXISTS idx_recommendations_applied ON recommendations(is_applied);
            CREATE INDEX IF NOT EXISTS idx_simulations_name ON simulations(scenario_name);
            CREATE INDEX IF NOT EXISTS idx_accuracy_metric ON prediction_accuracy(metric_name);
            CREATE INDEX IF NOT EXISTS idx_accuracy_forecast ON prediction_accuracy(forecast_id);
        """)
            self._conn.commit()

    def store_forecast(self, forecast: ForecastResult) -> str:
        rec_id = str(uuid4())
        try:
            with self._lock:
                self._conn.execute(
                """INSERT INTO forecasts (id, metric_name, model_used, accuracy_score, timestamps, forecast_values, confidence_lower, confidence_upper)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec_id,
                    forecast.metric_name,
                    forecast.model_used,
                    forecast.accuracy_score,
                    json.dumps(forecast.timestamps),
                    json.dumps(forecast.values),
                    json.dumps(forecast.confidence_lower),
                    json.dumps(forecast.confidence_upper),
                ),
            )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to store forecast: {e}")
            return ""
        return rec_id

    def store_anomaly(self, anomaly: MetricAnomaly) -> str:
        rec_id = str(uuid4())
        try:
            with self._lock:
                self._conn.execute(
                """INSERT INTO anomalies (id, metric_name, anomaly_type, severity, detected_at, expected_value, actual_value, confidence, cause, resolved)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec_id,
                    anomaly.metric_name,
                    anomaly.anomaly_type.value,
                    anomaly.severity,
                    anomaly.detected_at,
                    anomaly.expected_value,
                    anomaly.actual_value,
                    anomaly.confidence,
                    anomaly.cause,
                    1 if anomaly.resolved else 0,
                ),
            )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to store anomaly: {e}")
            return ""
        return rec_id

    def store_recommendation(self, rec: Recommendation) -> str:
        rec_id = str(uuid4())
        try:
            with self._lock:
                self._conn.execute(
                """INSERT INTO recommendations (id, metric, rec_type, title, description, priority, confidence, actions, evidence, actionable, expires_at, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec_id,
                    rec.metric,
                    rec.recommendation_type.value,
                    rec.title,
                    rec.description,
                    rec.priority,
                    rec.confidence,
                    json.dumps(rec.actions),
                    json.dumps(rec.evidence),
                    1 if rec.actionable else 0,
                    rec.expires_at,
                    rec.source,
                ),
            )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to store recommendation: {e}")
            return ""
        return rec_id

    def store_simulation(self, simulation) -> str:
        rec_id = str(uuid4())
        try:
            outcomes_str = "[]"
            risk_factors_str = "[]"
            if hasattr(simulation, "outcomes"):
                outcomes_str = json.dumps(simulation.outcomes[:100])
            if hasattr(simulation, "risk_factors"):
                risk_factors_str = json.dumps(simulation.risk_factors)
            ci_lower, ci_upper = getattr(simulation, "confidence_interval", (0.0, 0.0))
            with self._lock:
                self._conn.execute(
                """INSERT INTO simulations (id, scenario_name, iterations, mean_outcome, ci_lower, ci_upper, converged, outcomes, risk_factors)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec_id,
                    simulation.scenario_name,
                    simulation.iterations,
                    simulation.mean_outcome,
                    ci_lower,
                    ci_upper,
                    1 if getattr(simulation, "converged", False) else 0,
                    outcomes_str,
                    risk_factors_str,
                ),
            )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to store simulation: {e}")
            return ""
        return rec_id

    def store_accuracy(self, accuracy: dict) -> str:
        rec_id = str(uuid4())
        try:
            with self._lock:
                self._conn.execute(
                """INSERT INTO prediction_accuracy (id, forecast_id, metric_name, model_used, rmse, mae, mape, actual_value, predicted_value)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec_id,
                    accuracy.get("forecast_id", ""),
                    accuracy.get("metric_name", ""),
                    accuracy.get("model_used", ""),
                    accuracy.get("rmse"),
                    accuracy.get("mae"),
                    accuracy.get("mape"),
                    accuracy.get("actual_value", 0),
                    accuracy.get("predicted_value", 0),
                ),
            )
                self._conn.commit()
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to store accuracy: {e}")
            return ""
        return rec_id

    def check_accuracy(self, forecast_id: str, actual_value: float) -> dict:
        try:
            with self._lock:
                row = self._conn.execute(
                    """SELECT * FROM forecasts WHERE id = ?""", (forecast_id,)
                ).fetchone()
            if not row:
                logger.warning(f"[VECTOR][predictive_analytics] Forecast {forecast_id} not found")
                return {}
            metric_name = row["metric_name"]
            model_used = row["model_used"]
            forecast_values = json.loads(row["forecast_values"])
            if not forecast_values:
                return {}
            predicted_value = float(forecast_values[0])
            if not np.isfinite(actual_value) or not np.isfinite(predicted_value):
                logger.warning("[VECTOR][predictive_analytics] check_accuracy: non-finite value for {}", forecast_id)
                return {}
            actual_arr = np.array([actual_value], dtype=float)
            predicted_arr = np.array([predicted_value], dtype=float)
            diff = actual_arr - predicted_arr
            rmse = float(np.sqrt(np.mean(diff ** 2))) if len(diff) > 0 else 0.0
            mae = float(np.mean(np.abs(diff))) if len(diff) > 0 else 0.0
            # actual≈0 makes percentage error undefined; the 1e-10 guard produced ~1e12 "MAPE" poisoning the leaderboard.
            mape = None if abs(float(actual_value)) < 1e-9 else round(float(np.mean(np.abs(diff / actual_arr))) * 100, 4)

            accuracy_entry = {
                "forecast_id": forecast_id,
                "metric_name": metric_name,
                "model_used": model_used,
                "rmse": round(float(rmse), 4),
                "mae": round(float(mae), 4),
                "mape": mape,
                "actual_value": float(actual_value),
                "predicted_value": round(float(predicted_value), 4),
            }
            self.store_accuracy(accuracy_entry)
            logger.info("[VECTOR][predictive_analytics] Accuracy for {}: RMSE={:.4f} MAE={:.4f} MAPE={}", forecast_id, rmse, mae, "n/a" if mape is None else f"{mape:.2f}%")
            return accuracy_entry
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] check_accuracy failed: {e}")
            return {}

    def get_model_leaderboard(self, metric_name: str) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT model_used, AVG(rmse) as avg_rmse, AVG(mae) as avg_mae, AVG(mape) as avg_mape,
                              COUNT(*) as num_evals
                       FROM prediction_accuracy
                       WHERE metric_name = ? AND rmse IS NOT NULL
                       GROUP BY model_used
                       ORDER BY avg_rmse ASC""",
                    (metric_name,),
                ).fetchall()
            result = [dict(r) for r in rows]
            for entry in result:
                for k in ("avg_rmse", "avg_mae", "avg_mape"):
                    if entry.get(k) is not None:
                        entry[k] = round(float(entry[k]), 4)
            return result
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] get_model_leaderboard failed: {e}")
            return []

    def get_accuracy_trend(self, metric_name: str, days: int = 30) -> list[dict]:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            with self._lock:
                rows = self._conn.execute(
                    """SELECT id, metric_name, model_used, accuracy_score, created_at
                       FROM forecasts
                       WHERE metric_name = ? AND created_at >= ?
                       ORDER BY created_at ASC""",
                    (metric_name, cutoff),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to get accuracy trend: {e}")
            return []

    def get_recent_anomalies(self, limit: int = 20) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM anomalies ORDER BY detected_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to get recent anomalies: {e}")
            return []

    def get_pending_recommendations(self) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM recommendations WHERE is_applied = 0 ORDER BY
                       priority ASC, created_at DESC""",
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to get pending recommendations: {e}")
            return []

    def get_recent_forecasts(self, limit: int = 10) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT * FROM forecasts ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to get recent forecasts: {e}")
            return []

    def get_recent_simulations(self, limit: int = 10) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    """SELECT id, scenario_name, iterations, mean_outcome, ci_lower, ci_upper, converged, created_at
                       FROM simulations ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to get recent simulations: {e}")
            return []

    def mark_recommendation_applied(self, rec_id: str) -> bool:
        try:
            with self._lock:
                cur = self._conn.execute(
                    """UPDATE recommendations SET is_applied = 1 WHERE id = ?""",
                    (rec_id,),
                )
                self._conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to mark recommendation: {e}")
            return False

    def prune_old_records(self, days: int = PREDICTION_RETENTION_DAYS) -> int:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            total = 0
            with self._lock:
                for table in ("forecasts", "anomalies", "recommendations", "simulations"):
                    cur = self._conn.execute(
                        f"""DELETE FROM {table} WHERE created_at < ?""", (cutoff,)
                    )
                    total += cur.rowcount
                cur = self._conn.execute(
                    """DELETE FROM prediction_accuracy WHERE computed_at < ?""", (cutoff,)
                )
                total += cur.rowcount
                self._conn.commit()
            if total > 0:
                logger.info(f"[VECTOR][predictive_analytics] Pruned {total} records older than {days} days")
            return total
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Prune failed: {e}")
            return 0

    def close(self):
        try:
            with self._lock:
                self._conn.close()
            logger.info("[VECTOR][predictive_analytics] PredictionStore closed")
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Error closing store: {e}")


if __name__ == "__main__":
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    ps = PredictionStore(db_path)
    from districts.predictive_analytics.time_series_forecaster import ForecastResult
    from districts.predictive_analytics.anomaly_predictor import MetricAnomaly, AnomalyType
    from districts.predictive_analytics.strategy_recommender import Recommendation, RecommendationType

    fcast = ForecastResult(
        metric_name="cpu_usage",
        timestamps=["2026-01-01T00:00:00"],
        values=[85.0],
        confidence_lower=[80.0],
        confidence_upper=[90.0],
        model_used="moving_average",
        accuracy_score=0.9,
    )
    fid = ps.store_forecast(fcast)
    assert isinstance(fid, str)

    anom = MetricAnomaly(
        metric_name="cpu_usage",
        anomaly_type=AnomalyType.VALUE_OUT_OF_RANGE,
        severity=8,
        detected_at="2026-01-01T00:00:00",
        expected_value=75.0,
        actual_value=95.0,
        confidence=0.9,
        cause="CPU spike",
    )
    aid = ps.store_anomaly(anom)
    assert isinstance(aid, str)

    rec = Recommendation(
        recommendation_type=RecommendationType.RISK_MITIGATION,
        title="Test rec",
        description="Test description",
        priority=1,
        metric="cpu_usage",
        confidence=0.8,
        actions=["Do something"],
    )
    rid = ps.store_recommendation(rec)
    assert isinstance(rid, str)

    from districts.predictive_analytics.causal_simulator import SimulationResult
    sim = SimulationResult(
        scenario_name="test_sim",
        iterations=100,
        outcomes=[{"_outcome": 50.0}],
        mean_outcome=50.0,
        confidence_interval=(45.0, 55.0),
        converged=True,
    )
    sid = ps.store_simulation(sim)
    assert isinstance(sid, str)

    acc = ps.check_accuracy(fid, 83.0)
    assert isinstance(acc, dict)
    assert "rmse" in acc

    leaderboard = ps.get_model_leaderboard("cpu_usage")
    assert isinstance(leaderboard, list)

    trend = ps.get_accuracy_trend("cpu_usage", days=30)
    assert isinstance(trend, list)

    recent = ps.get_recent_anomalies(limit=10)
    assert isinstance(recent, list)

    pending = ps.get_pending_recommendations()
    assert isinstance(pending, list)

    forecasts = ps.get_recent_forecasts()
    assert isinstance(forecasts, list)

    sims = ps.get_recent_simulations()
    assert isinstance(sims, list)

    assert ps.mark_recommendation_applied(rid) is True
    assert ps.mark_recommendation_applied("nonexistent") is False

    pruned = ps.prune_old_records(days=0)
    assert isinstance(pruned, int)

    ps.close()
    Path(db_path).unlink(missing_ok=True)
    print("[OK] prediction_store.py")
