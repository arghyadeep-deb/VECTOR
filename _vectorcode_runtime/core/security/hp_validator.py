"""
VECTOR HP Validator — validates district HP changes for integrity.

Ensures HP deltas from district agents are honest by detecting outliers,
applying temporal smoothing, requiring cross-validation for large changes,
and detecting adversarial seesaw patterns.
"""
from __future__ import annotations

from core.memory.db_utils import apply_pragmas
__all__ = [
    "CROSS_VALIDATE_THRESHOLD",
    "EMA_ALPHA",
    "get_hp_validator",
    "HP_DB_PATH",
    "HPValidationResult",
    "HPValidator",
    "MAX_DELTA",
    "SEESAW_WINDOW",
]


import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger


HP_DB_PATH = Path(__file__).parent / "hp_validator.db"
MAX_DELTA = 200.0
EMA_ALPHA = 0.3
CROSS_VALIDATE_THRESHOLD = 50.0
SEESAW_WINDOW = 10


@dataclass
class HPValidationResult:
    validated_delta: float
    original_delta: float
    issues: list[str] = field(default_factory=list)
    smoothed_hp: float = 0.0
    cross_validated: bool = False


class HPValidator:
    """
    Validates HP changes from district agents.

    Usage:
        validator = HPValidator()
        result = validator.validate(25.0, "district_alpha", "mining", {})
        if result.issues:
            logger.warning("HP issues: {}", result.issues)
    """

    def __init__(self, db_path: str | Path = HP_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._ema_state: dict[str, float] = {}
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is not None:
                return self._conn
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            apply_pragmas(self._conn)
            return self._conn

    def _init_db(self) -> None:
        try:
            conn = self._get_conn()
            with self._lock:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS hp_delta_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_id TEXT NOT NULL,
                        delta REAL NOT NULL,
                        validated_delta REAL NOT NULL,
                        source_district TEXT NOT NULL,
                        context TEXT DEFAULT '',
                        timestamp REAL NOT NULL,
                        issues TEXT DEFAULT ''
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.warning("[VECTOR][hp] db init failed: {}", e)

    def validate(
        self,
        delta: float,
        agent_id: str,
        source_district: str,
        context: dict[str, Any] | None = None,
    ) -> HPValidationResult:
        issues: list[str] = []
        original_delta = delta
        smoothed = 0.0
        cross_validated = False

        is_outlier, clamped = self._check_outlier(delta)
        if is_outlier:
            issues.append(f"delta {delta} exceeds {MAX_DELTA}, clamped to {clamped}")
            delta = clamped

        try:
            smoothed = self._smooth(delta, agent_id)
        except Exception as e:
            logger.warning("[VECTOR][hp] smoothing failed for {}: {}", agent_id, e)

        if abs(delta) >= CROSS_VALIDATE_THRESHOLD:
            try:
                cross_validated = self._cross_validate(delta, source_district)
                if not cross_validated:
                    issues.append(
                        f"delta {delta} from {source_district} lacks cross-validation"
                    )
            except Exception as e:
                logger.warning("[VECTOR][hp] cross-validate failed: {}", e)
                issues.append("cross-validation error")

        try:
            if self._detect_adversarial_pattern(agent_id, delta):
                issues.append(f"adversarial seesaw pattern detected for {agent_id}")
        except Exception as e:
            logger.warning("[VECTOR][hp] adversarial check failed: {}", e)

        validated = smoothed if smoothed != 0.0 else delta

        self._store_delta(
            agent_id=agent_id,
            delta=original_delta,
            validated_delta=validated,
            source_district=source_district,
            context=str(context or {}),
            issues="; ".join(issues),
        )

        return HPValidationResult(
            validated_delta=validated,
            original_delta=original_delta,
            issues=issues,
            smoothed_hp=smoothed,
            cross_validated=cross_validated,
        )

    def _check_outlier(self, delta: float) -> tuple[bool, float]:
        if abs(delta) > MAX_DELTA:
            clamped = MAX_DELTA if delta > 0 else -MAX_DELTA
            return True, clamped
        return False, delta

    def _smooth(self, delta: float, agent_id: str) -> float:
        # The EMA used to be ONE state per agent shared by rewards and penalties, so a small penalty right after a large award was
        # blended with it (measured: a -5 after a -30 became -22.5; after a +50 it turned into +33.5, which deduct_points then took as
        # a 33.5 HP loss via abs()). With VECTOR_HP_FAIR penalties are not smoothed at all -- a -30 must cost 30 and a first-of-a-kind
        # -5 must cost 5, whatever came before (deduct_points is documented as deliberately unshaped) -- and awards keep an EMA of
        # their own, so smoothing only ever damps runs of rewards.
        key = agent_id
        try:
            from core.city.experience import hp_fair_enabled
            if hp_fair_enabled():
                if delta < 0:
                    return round(delta, 2)
                key = f"{agent_id}:+"
        except Exception:
            pass
        with self._lock:
            prev = self._ema_state.get(key, delta)
            smoothed = EMA_ALPHA * delta + (1 - EMA_ALPHA) * prev
            self._ema_state[key] = smoothed
        return round(smoothed, 2)

    def _cross_validate(self, delta: float, source_district: str) -> bool:
        try:
            conn = self._get_conn()
            cutoff = time.time() - 60
            with self._lock:
                rows = conn.execute(
                    "SELECT source_district, validated_delta FROM hp_delta_log "
                    "WHERE timestamp > ? AND source_district != ? "
                    "ORDER BY timestamp DESC LIMIT 20",
                    (cutoff, source_district),
                ).fetchall()

            if not rows:
                return False

            agreements = 0
            for row in rows:
                other_delta = row[1]
                if abs(other_delta - delta) < CROSS_VALIDATE_THRESHOLD / 2:
                    agreements += 1

            return agreements >= 2
        except Exception as e:
            logger.warning("[VECTOR][hp] cross-validate query failed: {}", e)
            return False

    def _detect_adversarial_pattern(self, agent_id: str, delta: float) -> bool:
        with self._lock:
            history = self._history[agent_id]
            history.append({"delta": delta, "ts": time.time()})

            while len(history) > SEESAW_WINDOW:
                history.pop(0)

            if len(history) < 4:
                return False

            sign_changes = 0
            for i in range(1, len(history)):
                if history[i]["delta"] * history[i - 1]["delta"] < 0:
                    sign_changes += 1

            return sign_changes >= 3

    def _store_delta(
        self,
        agent_id: str,
        delta: float,
        validated_delta: float,
        source_district: str,
        context: str,
        issues: str,
    ) -> None:
        try:
            conn = self._get_conn()
            with self._lock:
                conn.execute(
                    "INSERT INTO hp_delta_log "
                    "(agent_id, delta, validated_delta, source_district, context, timestamp, issues) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (agent_id, delta, validated_delta, source_district, context, time.time(), issues),
                )
                conn.commit()
        except Exception as e:
            logger.warning("[VECTOR][hp] store failed: {}", e)

    def get_agent_history(self, agent_id: str, days: int = 7) -> list[dict[str, Any]]:
        try:
            conn = self._get_conn()
            cutoff = time.time() - days * 86400
            with self._lock:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM hp_delta_log WHERE agent_id = ? AND timestamp > ? "
                    "ORDER BY timestamp DESC LIMIT 100",
                    (agent_id, cutoff),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("[VECTOR][hp] get_agent_history failed: {}", e)
            return []


_validator: HPValidator | None = None


def get_hp_validator() -> HPValidator:
    global _validator
    if _validator is None:
        _validator = HPValidator()
    return _validator


if __name__ == "__main__":
    validator = HPValidator(db_path=":memory:")

    result = validator.validate(30.0, "district_alpha", "mining", {})
    assert result.validated_delta == 30.0
    assert result.original_delta == 30.0
    assert not result.issues

    result2 = validator.validate(500.0, "district_alpha", "mining", {})
    assert result2.validated_delta < 500.0
    assert any("clamped" in i for i in result2.issues)

    result3 = validator.validate(-50.0, "district_beta", "combat", {})
    assert result3.validated_delta == -50.0
    assert result3.original_delta == -50.0

    for v in [10.0, -10.0, 10.0, -10.0]:
        validator.validate(v, "district_gamma", "testing", {})
    r4 = validator.validate(-10.0, "district_gamma", "testing", {})
    assert any("seesaw" in i for i in r4.issues)

    history = validator.get_agent_history("district_alpha", days=1)
    assert len(history) >= 2

    print("OK hp_validator.py — outlier, smoothing, cross-validate, seesaw, history verified")
