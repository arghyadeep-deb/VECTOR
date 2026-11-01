from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import datetime
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from loguru import logger


_DEFAULT_DB = str(__import__("core.runtime_paths", fromlist=["data_path"]).data_path("health", "health_metrics.db"))


class MetricsStore:
    def __init__(self, db_path: str | Path | None = None, retention_days: int = 90) -> None:
        self._db_path = str(db_path or _DEFAULT_DB)
        self._retention_days = retention_days
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._init_db()
        logger.info(f"[VECTOR][metrics_store] db={self._db_path} retention={retention_days}d")

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            apply_pragmas(self._conn)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._ensure_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_metrics (
                id          TEXT PRIMARY KEY,
                source      TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value       REAL NOT NULL,
                unit        TEXT NOT NULL DEFAULT '',
                timestamp   TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hm_name_ts ON health_metrics(metric_name, timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hm_source ON health_metrics(source)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS wearable_metrics (
                id                  TEXT PRIMARY KEY,
                source              TEXT NOT NULL,
                heart_rate          REAL,
                hrv                 REAL,
                resting_heart_rate  REAL,
                sleep_hours         REAL,
                sleep_quality       TEXT,
                sleep_stages        TEXT,
                steps               INTEGER,
                active_calories     REAL,
                exercise_minutes    REAL,
                spo2                REAL,
                stress_level        REAL,
                skin_temperature    REAL,
                respiratory_rate    REAL,
                raw_json            TEXT,
                timestamp           TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wm_source_ts ON wearable_metrics(source, timestamp)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS metric_trends (
                id              TEXT PRIMARY KEY,
                metric_name     TEXT NOT NULL,
                direction       TEXT NOT NULL,
                change_pct      REAL,
                avg             REAL,
                min_val         REAL,
                max_val         REAL,
                std_dev         REAL,
                baseline_7d_mean    REAL,
                baseline_7d_std     REAL,
                baseline_30d_mean   REAL,
                baseline_30d_std    REAL,
                delta_7d_pct    REAL,
                delta_30d_pct   REAL,
                stability       TEXT,
                computed_at     TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mt_name ON metric_trends(metric_name)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_anomalies (
                id              TEXT PRIMARY KEY,
                metric_name     TEXT NOT NULL,
                expected        REAL,
                actual          REAL,
                deviation       REAL,
                severity        INTEGER,
                detected_at     TEXT NOT NULL,
                trend_direction TEXT,
                probable_causes TEXT,
                acknowledged    INTEGER DEFAULT 0,
                resolved_at     TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ha_detected ON health_anomalies(detected_at)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_recommendations (
                id              TEXT PRIMARY KEY,
                rec_type        TEXT NOT NULL,
                title           TEXT NOT NULL,
                description     TEXT,
                priority        INTEGER,
                metric_source   TEXT,
                actionable      INTEGER DEFAULT 1,
                created_at      TEXT NOT NULL,
                applied         INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hr_priority ON health_recommendations(priority)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS emergency_events (
                id              TEXT PRIMARY KEY,
                event_type      TEXT NOT NULL,
                value           REAL,
                threshold       TEXT,
                severity        INTEGER,
                message         TEXT,
                detected_at     TEXT NOT NULL,
                acknowledged    INTEGER DEFAULT 0,
                escalated       INTEGER DEFAULT 0,
                resolved_at     TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ee_detected ON emergency_events(detected_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ee_resolved ON emergency_events(resolved_at)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_health_summaries (
                id              TEXT PRIMARY KEY,
                summary_date    TEXT NOT NULL,
                avg_heart_rate  REAL,
                avg_hrv         REAL,
                total_steps     INTEGER,
                total_sleep_h   REAL,
                avg_spo2        REAL,
                avg_stress      REAL,
                anomaly_count   INTEGER DEFAULT 0,
                rec_count       INTEGER DEFAULT 0,
                summary_json    TEXT,
                created_at      TEXT NOT NULL
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dhs_date ON daily_health_summaries(summary_date)")
        conn.commit()

    def store_metric(self, source: str, metric_name: str, value: float, unit: str = "", timestamp: str | None = None) -> str:
        row_id = uuid.uuid4().hex[:12]
        ts = timestamp or datetime.datetime.now().isoformat(timespec="seconds")
        conn = self._ensure_conn()
        conn.execute("INSERT INTO health_metrics (id, source, metric_name, value, unit, timestamp) VALUES (?, ?, ?, ?, ?, ?)", (row_id, source, metric_name, value, unit, ts))
        conn.commit()
        return row_id

    def store_batch(self, metrics: list[dict[str, Any]]) -> int:
        conn = self._ensure_conn()
        now = datetime.datetime.now().isoformat(timespec="seconds")
        rows = [(m.get("id", uuid.uuid4().hex[:12]), m["source"], m["metric_name"], m["value"], m.get("unit", ""), m.get("timestamp", now)) for m in metrics]
        conn.executemany("INSERT INTO health_metrics (id, source, metric_name, value, unit, timestamp) VALUES (?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        return len(rows)

    def store_wearable(self, source: str, metrics: dict[str, Any]) -> str:
        row_id = uuid.uuid4().hex[:12]
        ts = metrics.get("timestamp") or datetime.datetime.now().isoformat(timespec="seconds")
        conn = self._ensure_conn()
        sleep_stages = metrics.get("sleep_stages")
        raw_json = json.dumps(metrics, default=str)
        conn.execute(
            "INSERT INTO wearable_metrics (id, source, heart_rate, hrv, resting_heart_rate, sleep_hours, sleep_quality, sleep_stages, steps, active_calories, exercise_minutes, spo2, stress_level, skin_temperature, respiratory_rate, raw_json, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, source,
             metrics.get("heart_rate"), metrics.get("hrv"), metrics.get("resting_heart_rate"),
             metrics.get("sleep_hours"), metrics.get("sleep_quality"), json.dumps(sleep_stages) if sleep_stages else None,
             metrics.get("steps"), metrics.get("active_calories"), metrics.get("exercise_minutes"),
             metrics.get("spo2"), metrics.get("stress_level"), metrics.get("skin_temperature"),
             metrics.get("respiratory_rate"), raw_json, ts),
        )
        conn.commit()
        return row_id

    def store_trend(self, trend: dict[str, Any]) -> str:
        row_id = uuid.uuid4().hex[:12]
        conn = self._ensure_conn()
        conn.execute(
            "INSERT INTO metric_trends (id, metric_name, direction, change_pct, avg, min_val, max_val, std_dev, baseline_7d_mean, baseline_7d_std, baseline_30d_mean, baseline_30d_std, delta_7d_pct, delta_30d_pct, stability, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, trend["metric_name"], trend.get("direction", "stable"), trend.get("change_pct", 0.0),
             trend.get("avg", 0.0), trend.get("min", 0.0), trend.get("max", 0.0), trend.get("std_dev", 0.0),
             trend.get("baseline_7d_mean", 0.0), trend.get("baseline_7d_std", 0.0),
             trend.get("baseline_30d_mean", 0.0), trend.get("baseline_30d_std", 0.0),
             trend.get("delta_7d_pct", 0.0), trend.get("delta_30d_pct", 0.0),
             trend.get("stability", "stable"), datetime.datetime.now().isoformat()),
        )
        conn.commit()
        return row_id

    def store_anomaly(self, anomaly: dict[str, Any]) -> str:
        row_id = uuid.uuid4().hex[:12]
        conn = self._ensure_conn()
        causes = anomaly.get("probable_causes", [])
        conn.execute(
            "INSERT INTO health_anomalies (id, metric_name, expected, actual, deviation, severity, detected_at, trend_direction, probable_causes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, anomaly["metric_name"], anomaly.get("expected", 0.0), anomaly.get("actual", 0.0),
             anomaly.get("deviation", 0.0), anomaly.get("severity", 5),
             anomaly.get("detected_at", datetime.datetime.now().isoformat()),
             anomaly.get("trend_direction", "stable"),
             json.dumps(causes) if causes else None),
        )
        conn.commit()
        return row_id

    def store_recommendation(self, rec: dict[str, Any]) -> str:
        row_id = uuid.uuid4().hex[:12]
        conn = self._ensure_conn()
        conn.execute(
            "INSERT INTO health_recommendations (id, rec_type, title, description, priority, metric_source, actionable, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, rec.get("type", "general"), rec.get("title", ""), rec.get("description", ""),
             rec.get("priority", 3), rec.get("metric_source", ""),
             1 if rec.get("actionable", True) else 0,
             datetime.datetime.now().isoformat()),
        )
        conn.commit()
        return row_id

    def store_emergency_event(self, event: dict[str, Any]) -> str:
        row_id = uuid.uuid4().hex[:12]
        conn = self._ensure_conn()
        conn.execute(
            "INSERT INTO emergency_events (id, event_type, value, threshold, severity, message, detected_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row_id, event.get("event_type", "unknown"), event.get("value"), event.get("threshold"),
             event.get("severity", 5), event.get("message", ""),
             event.get("detected_at", datetime.datetime.now().isoformat())),
        )
        conn.commit()
        return row_id

    def store_daily_summary(self, summary: dict[str, Any]) -> str:
        row_id = uuid.uuid4().hex[:12]
        conn = self._ensure_conn()
        conn.execute(
            "INSERT INTO daily_health_summaries (id, summary_date, avg_heart_rate, avg_hrv, total_steps, total_sleep_h, avg_spo2, avg_stress, anomaly_count, rec_count, summary_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, summary.get("summary_date", datetime.date.today().isoformat()),
             summary.get("avg_heart_rate"), summary.get("avg_hrv"),
             summary.get("total_steps"), summary.get("total_sleep_h"),
             summary.get("avg_spo2"), summary.get("avg_stress"),
             summary.get("anomaly_count", 0), summary.get("rec_count", 0),
             json.dumps(summary.get("summary_json", {})) if summary.get("summary_json") else None,
             datetime.datetime.now().isoformat()),
        )
        conn.commit()
        return row_id

    def get_metrics(self, metric_name: str, days: int = 7) -> list[dict[str, Any]]:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        conn = self._ensure_conn()
        cursor = conn.execute(
            "SELECT id, source, metric_name, value, unit, timestamp FROM health_metrics WHERE metric_name = ? AND timestamp >= ? ORDER BY timestamp ASC",
            (metric_name, cutoff),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_latest(self, metric_name: str) -> dict[str, Any] | None:
        conn = self._ensure_conn()
        cursor = conn.execute(
            "SELECT id, source, metric_name, value, unit, timestamp FROM health_metrics WHERE metric_name = ? ORDER BY timestamp DESC LIMIT 1",
            (metric_name,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_latest_wearable(self, source: str | None = None) -> dict[str, Any] | None:
        conn = self._ensure_conn()
        if source:
            cursor = conn.execute("SELECT * FROM wearable_metrics WHERE source = ? ORDER BY timestamp DESC LIMIT 1", (source,))
        else:
            cursor = conn.execute("SELECT * FROM wearable_metrics ORDER BY timestamp DESC LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_trends(self, metric_name: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        if metric_name:
            cursor = conn.execute("SELECT * FROM metric_trends WHERE metric_name = ? ORDER BY computed_at DESC LIMIT ?", (metric_name, limit))
        else:
            cursor = conn.execute("SELECT * FROM metric_trends ORDER BY computed_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_anomalies(self, unresolved_only: bool = False, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        if unresolved_only:
            cursor = conn.execute("SELECT * FROM health_anomalies WHERE acknowledged = 0 ORDER BY detected_at DESC LIMIT ?", (limit,))
        else:
            cursor = conn.execute("SELECT * FROM health_anomalies ORDER BY detected_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_recommendations(self, priority_min: int = 1, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        cursor = conn.execute("SELECT * FROM health_recommendations WHERE priority <= ? ORDER BY priority ASC, created_at DESC LIMIT ?", (priority_min, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_emergency_events(self, unresolved_only: bool = False, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._ensure_conn()
        if unresolved_only:
            cursor = conn.execute("SELECT * FROM emergency_events WHERE resolved_at IS NULL ORDER BY detected_at DESC LIMIT ?", (limit,))
        else:
            cursor = conn.execute("SELECT * FROM emergency_events ORDER BY detected_at DESC LIMIT ?", (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def get_daily_summaries(self, days: int = 30) -> list[dict[str, Any]]:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        conn = self._ensure_conn()
        cursor = conn.execute("SELECT * FROM daily_health_summaries WHERE summary_date >= ? ORDER BY summary_date DESC", (cutoff,))
        return [dict(row) for row in cursor.fetchall()]

    def acknowledge_anomaly(self, anomaly_id: str) -> bool:
        conn = self._ensure_conn()
        cursor = conn.execute("UPDATE health_anomalies SET acknowledged = 1 WHERE id = ?", (anomaly_id,))
        conn.commit()
        return cursor.rowcount > 0

    def resolve_emergency(self, event_id: str) -> bool:
        conn = self._ensure_conn()
        cursor = conn.execute("UPDATE emergency_events SET resolved_at = ? WHERE id = ?", (datetime.datetime.now().isoformat(), event_id))
        conn.commit()
        return cursor.rowcount > 0

    def prune_old_data(self, retention_days: int | None = None) -> dict[str, int]:
        days = self._retention_days if retention_days is None else retention_days
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        conn = self._ensure_conn()
        counts: dict[str, int] = {}
        tables = ["health_metrics", "wearable_metrics", "metric_trends", "health_anomalies", "health_recommendations", "emergency_events", "daily_health_summaries"]
        for table in tables:
            ts_col = "timestamp" if table in ("health_metrics", "wearable_metrics") else "detected_at" if table in ("health_anomalies", "emergency_events") else "created_at" if table in ("health_recommendations",) else "computed_at" if table == "metric_trends" else "created_at"
            cursor = conn.execute(f"DELETE FROM {table} WHERE {ts_col} < ?", (cutoff,))
            counts[table] = cursor.rowcount
        conn.commit()
        logger.info(f"[VECTOR][metrics_store] pruned {sum(counts.values())} rows older than {days}d: {counts}")
        return counts

    def get_sources(self) -> list[str]:
        conn = self._ensure_conn()
        cursor = conn.execute("SELECT DISTINCT source FROM health_metrics ORDER BY source")
        return [row["source"] for row in cursor.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
        self._conn = None
