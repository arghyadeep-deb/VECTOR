"""
core/experiments/ab_testing.py — A/B testing framework for VECTOR (Gap 18).

Allows comparing two decision strategies, two models, or two routing algorithms.
Uses SQLite for durable experiment state and result tracking.

Usage:
    from core.experiments.ab_testing import Experiment, ExperimentRegistry

    # Register an experiment
    reg = ExperimentRegistry()
    exp = reg.create("ollama_model_comparison",
                     variants=["vector-focus", "vector-deep"],
                     description="Compare response quality between two models")

    # Assign a variant for a given subject (deterministic, hash-based)
    variant = exp.assign("user_session_abc123")  # → "vector-focus" or "vector-deep"

    # Record a result
    exp.record(subject_id="user_session_abc123", variant=variant,
               metric="reward", value=0.87)

    # Get stats
    stats = exp.stats()  # → {variant: {mean, n, p_value}}
"""
from core.memory.db_utils import apply_pragmas
import hashlib

__all__ = [
    "Experiment",
    "ExperimentRegistry",
]

import json
import math
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from core.memory.db_utils import configured_db_path

_DB_PATH = configured_db_path()


def _get_conn(db_path: str) -> tuple[sqlite3.Connection, bool]:
    """Returns (conn, private). The main DB may be SQLCipher-encrypted, so a
    plain sqlite3.connect() against it fails with "file is not a database" --
    must go through episodic's singleton instead (never closed here). A
    redirected db_path (tests / a custom Experiment/ExperimentRegistry path)
    gets a private plain connection the caller closes. Mirrors
    core/queue/retry_queue.py::RetryQueue._conn()."""
    main_db = str(configured_db_path())
    if db_path != main_db:
        conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        apply_pragmas(conn)
        conn.row_factory = sqlite3.Row
        return conn, True
    from core.memory.episodic import get_db_connection
    import importlib
    conn = get_db_connection()
    conn.row_factory = importlib.import_module(type(conn).__module__).Row
    return conn, False


@dataclass
class Experiment:
    id: int
    name: str
    variants: list[str]
    description: str
    created_at: float
    active: bool
    _db: str = field(repr=False, default="")

    def assign(self, subject_id: str) -> str:
        """Deterministically assign a variant to a subject (hash-based, no randomness)."""
        h = int(hashlib.sha256(f"{self.name}:{subject_id}".encode()).hexdigest(), 16)
        return self.variants[h % len(self.variants)]

    def record(self, subject_id: str, variant: str, metric: str, value: float,
               metadata: dict | None = None) -> None:
        """Record a metric observation for a variant."""
        conn, private = _get_conn(self._db)
        try:
            conn.execute("""
                INSERT INTO experiment_results
                    (experiment_id, subject_id, variant, metric, value, metadata, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (self.id, subject_id, variant, metric, value,
                  json.dumps(metadata or {}), time.time()))
            conn.commit()
        finally:
            if private:
                conn.close()
        logger.debug(f"[VECTOR][exp] {self.name}/{variant} {metric}={value:.4f}")

    def stats(self, metric: str = "reward") -> dict[str, dict]:
        """Return per-variant stats: mean, n, std, and Welch's t-test p-value vs first variant."""
        conn, private = _get_conn(self._db)
        try:
            rows = conn.execute("""
                SELECT variant, value FROM experiment_results
                WHERE experiment_id = ? AND metric = ?
            """, (self.id, metric)).fetchall()
        finally:
            if private:
                conn.close()

        buckets: dict[str, list[float]] = {v: [] for v in self.variants}
        for variant, value in rows:
            if variant in buckets:
                buckets[variant].append(value)

        result: dict[str, dict] = {}
        for v, vals in buckets.items():
            n = len(vals)
            mean = sum(vals) / n if n else 0.0
            variance = sum((x - mean) ** 2 for x in vals) / max(n - 1, 1) if n > 1 else 0.0
            result[v] = {"mean": round(mean, 4), "n": n, "std": round(math.sqrt(variance), 4)}

        # Welch's t-test p-value between first and each other variant
        if len(self.variants) >= 2:
            base = self.variants[0]
            base_stats = result[base]
            for v in self.variants[1:]:
                s = result[v]
                n1, n2 = base_stats["n"], s["n"]
                if n1 < 2 or n2 < 2:
                    result[v]["p_value"] = None
                    continue
                se = math.sqrt(
                    (base_stats["std"] ** 2 / n1) + (s["std"] ** 2 / n2)
                )
                if se == 0:
                    result[v]["p_value"] = 1.0
                    continue
                t = abs(base_stats["mean"] - s["mean"]) / se
                # Approximate p-value using normal distribution (valid for n > 30)
                # For small n this is an approximation; use scipy.stats for exact.
                p = 2 * (1 - _normal_cdf(t))
                result[v]["p_value"] = round(p, 4)

        return result

    def winner(self, metric: str = "reward", min_n: int = 30) -> str | None:
        """Return the variant with the highest mean if statistically significant (p < 0.05)."""
        s = self.stats(metric)
        candidates = [(v, d) for v, d in s.items() if d["n"] >= min_n]
        if not candidates:
            return None
        best = max(candidates, key=lambda x: x[1]["mean"])
        # Check significance vs all others
        for v, d in candidates:
            if v == best[0]:
                continue
            p = d.get("p_value")
            if p is None or p >= 0.05:
                return None  # not significant yet
        return best[0]


def _normal_cdf(z: float) -> float:
    """Approximation of the standard normal CDF."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


class ExperimentRegistry:
    _instance: "ExperimentRegistry | None" = None

    def __init__(self, db_path: Path = _DB_PATH):
        self._db = str(db_path)
        self._lock = threading.RLock()
        self._init_db()

    @classmethod
    def get(cls) -> "ExperimentRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _conn(self) -> tuple[sqlite3.Connection, bool]:
        """Returns (conn, private). See _get_conn() above."""
        return _get_conn(self._db)

    def _init_db(self) -> None:
        conn, private = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiments (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT UNIQUE NOT NULL,
                    variants    TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    active      INTEGER NOT NULL DEFAULT 1,
                    created_at  REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiment_results (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id INTEGER NOT NULL,
                    subject_id    TEXT NOT NULL,
                    variant       TEXT NOT NULL,
                    metric        TEXT NOT NULL,
                    value         REAL NOT NULL,
                    metadata      TEXT NOT NULL DEFAULT '{}',
                    recorded_at   REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_exp_results
                ON experiment_results (experiment_id, metric, variant)
            """)
            conn.commit()
        finally:
            if private:
                conn.close()

    def create(self, name: str, variants: list[str], description: str = "") -> Experiment:
        """Create or retrieve an experiment by name."""
        conn, private = self._conn()
        try:
            existing = conn.execute(
                "SELECT * FROM experiments WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                return self._row_to_exp(existing)
            cur = conn.execute(
                "INSERT INTO experiments (name, variants, description, active, created_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (name, json.dumps(variants), description, time.time()),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM experiments WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        finally:
            if private:
                conn.close()
        logger.info(f"[VECTOR][exp] created experiment '{name}' variants={variants}")
        return self._row_to_exp(row)

    def get_experiment(self, name: str) -> Experiment | None:
        conn, private = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM experiments WHERE name = ?", (name,)
            ).fetchone()
        finally:
            if private:
                conn.close()
        return self._row_to_exp(row) if row else None

    def list_active(self) -> list[Experiment]:
        conn, private = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM experiments WHERE active = 1 ORDER BY created_at DESC"
            ).fetchall()
        finally:
            if private:
                conn.close()
        return [self._row_to_exp(r) for r in rows]

    def deactivate(self, name: str) -> None:
        conn, private = self._conn()
        try:
            conn.execute("UPDATE experiments SET active = 0 WHERE name = ?", (name,))
            conn.commit()
        finally:
            if private:
                conn.close()

    def _row_to_exp(self, row: Any) -> Experiment:
        return Experiment(
            id=row["id"],
            name=row["name"],
            variants=json.loads(row["variants"]),
            description=row["description"],
            created_at=row["created_at"],
            active=bool(row["active"]),
            _db=self._db,
        )
