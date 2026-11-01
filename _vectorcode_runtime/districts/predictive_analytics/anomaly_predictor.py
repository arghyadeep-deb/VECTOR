
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta
from numbers import Real
import numpy as np

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

class AnomalyType(Enum):
    VALUE_OUT_OF_RANGE = "value_out_of_range"
    TREND_DIVERGENCE = "trend_divergence"
    RATE_ACCELERATION = "rate_acceleration"
    COMPOUND_ANOMALY = "compound_anomaly"
    MISSING_EXPECTED = "missing_expected"

@dataclass
class MetricAnomaly:
    metric_name: str
    anomaly_type: AnomalyType
    severity: int
    detected_at: str
    expected_value: float
    actual_value: float
    confidence: float
    cause: str = ""
    resolved: bool = False

ANOMALY_CONFIG = {
    "confidence_ci_threshold": 95,
    "trend_points": 5,
    "rate_acceleration_factor": 2.0,
}

class AnomalyPredictor:
    def __init__(self, zscore_threshold: float = 2.5, ma_window: int = 7):
        self.zscore_threshold = zscore_threshold
        self.ma_window = ma_window
        self._reported_keys: set = set()
        self._config = dict(ANOMALY_CONFIG)

    def detect(
        self,
        metric_name: str,
        values: list[float],
        timestamps: Optional[list[str]] = None,
    ) -> list[MetricAnomaly]:
        if not values or len(values) < 3:
            logger.warning(f"[VECTOR][predictive_analytics] Insufficient data for anomaly detection on {metric_name}")
            return []

        if timestamps is None:
            now = datetime.now(timezone.utc)
            timestamps = [(now - timedelta(hours=len(values) - i)).isoformat() for i in range(len(values))]

        anomalies: list[MetricAnomaly] = []
        # NaN/inf readings poison mean/std (every z-score becomes NaN -> "clean"); report them, analyse the rest.
        bad = [i for i, v in enumerate(values) if not isinstance(v, Real) or not np.isfinite(v)]
        if bad:
            anomalies.append(MetricAnomaly(
                metric_name=metric_name,
                anomaly_type=AnomalyType.MISSING_EXPECTED,
                severity=7,
                detected_at=timestamps[bad[-1]],
                expected_value=0.0,
                actual_value=0.0,
                confidence=0.9,
                cause=f"{len(bad)} non-finite or non-numeric readings for {metric_name}",
            ))
            bad_set = set(bad)
            keep = [i for i in range(len(values)) if i not in bad_set]
            values = [values[i] for i in keep]
            timestamps = [timestamps[i] for i in keep]
            if len(values) < 3:
                logger.info("[VECTOR][predictive_analytics] {}: too few finite readings after filtering", metric_name)
                return anomalies
        try:
            anomalies.extend(self._detect_value_out_of_range(metric_name, values, timestamps))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] value_out_of_range failed: {e}")

        try:
            anomalies.extend(self._detect_trend_divergence(metric_name, values, timestamps))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] trend_divergence failed: {e}")

        try:
            anomalies.extend(self._detect_rate_acceleration(metric_name, values, timestamps))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] rate_acceleration failed: {e}")

        try:
            anomalies.extend(self._detect_missing_expected(metric_name, values, timestamps))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] missing_expected failed: {e}")

        if len([a for a in anomalies if a.severity >= 5]) >= 3:
            compound_severity = sum(a.severity for a in anomalies) // len(anomalies)
            anomalies.append(MetricAnomaly(
                metric_name=metric_name,
                anomaly_type=AnomalyType.COMPOUND_ANOMALY,
                severity=min(10, compound_severity + 2),
                detected_at=timestamps[-1],
                expected_value=0.0,
                actual_value=float(len([a for a in anomalies if a.severity >= 5])),
                confidence=0.85,
                cause=f"Multiple simultaneous anomalies ({len(anomalies)} active)",
            ))

        deduped = self._deduplicate(anomalies)
        deduped.sort(key=lambda a: a.severity, reverse=True)

        for a in deduped:
            if a.severity >= 7:
                self._pushover_alert(a)

        logger.info(f"[VECTOR][predictive_analytics] Detected {len(deduped)} anomalies for {metric_name}")
        return deduped

    def analyze(self, forecast, actual) -> list[MetricAnomaly]:
        if not actual:
            return []
        anomalies = []
        metric_name = getattr(forecast, "metric_name", "unknown")
        predicted = getattr(forecast, "values", [])
        timestamps = getattr(forecast, "timestamps", [])
        if not predicted or not actual:
            return anomalies
        min_len = min(len(predicted), len(actual))
        if min_len < 1:
            return anomalies
        ts = timestamps[:min_len] if len(timestamps) >= min_len else [
            datetime.now(timezone.utc).isoformat() for _ in range(min_len)
        ]
        for i in range(min_len):
            expected = predicted[i]
            actual_v = actual[i]
            if expected == 0:
                pct_dev = abs(actual_v) / 0.01
            else:
                pct_dev = abs(actual_v - expected) / abs(expected)
            if pct_dev > 0.3:
                severity = min(10, int(pct_dev * 10))
                anomalies.append(MetricAnomaly(
                    metric_name=metric_name,
                    anomaly_type=AnomalyType.VALUE_OUT_OF_RANGE,
                    severity=severity,
                    detected_at=ts[i],
                    expected_value=float(expected),
                    actual_value=float(actual_v),
                    confidence=min(1.0, pct_dev),
                    cause=self._estimate_cause(
                        metric_name, float(expected), float(actual_v), {}
                    ),
                ))
        return anomalies

    def _detect_value_out_of_range(
        self,
        metric_name: str,
        values: list[float],
        timestamps: list[str],
    ) -> list[MetricAnomaly]:
        anomalies = []
        arr = np.array(values, dtype=float)
        mean = float(np.mean(arr))
        std = float(np.std(arr)) if len(arr) > 1 else 1.0
        if std == 0:
            return anomalies
        z_scores = np.abs((arr - mean) / std)
        for i, z in enumerate(z_scores):
            if z > self.zscore_threshold:
                severity = min(10, int((z - self.zscore_threshold) / self.zscore_threshold * 5) + 3)
                anomalies.append(MetricAnomaly(
                    metric_name=metric_name,
                    anomaly_type=AnomalyType.VALUE_OUT_OF_RANGE,
                    severity=severity,
                    detected_at=timestamps[i],
                    expected_value=round(float(mean), 4),
                    actual_value=round(float(values[i]), 4),
                    confidence=round(float(min(1.0, z / 6.0)), 4),
                    cause=self._estimate_cause(metric_name, float(mean), float(values[i]), {}),
                ))
        return anomalies

    def _detect_trend_divergence(
        self,
        metric_name: str,
        values: list[float],
        timestamps: list[str],
    ) -> list[MetricAnomaly]:
        anomalies = []
        if len(values) < 6:
            return anomalies
        arr = np.array(values, dtype=float)
        n = len(arr)
        half = n // 2
        first_half = arr[:half]
        second_half = arr[half:]
        x1 = np.arange(len(first_half), dtype=float)
        x2 = np.arange(len(second_half), dtype=float)
        if len(first_half) > 1 and len(second_half) > 1:
            slope1 = float(np.polyfit(x1, first_half, 1)[0])
            slope2 = float(np.polyfit(x2, second_half, 1)[0])
            slope_change = slope2 - slope1
            if abs(slope_change) > abs(slope1) * 0.5 + 0.01:
                severity = min(10, int(abs(slope_change) / (abs(slope1) + 0.001) * 4) + 4)
                anomalies.append(MetricAnomaly(
                    metric_name=metric_name,
                    anomaly_type=AnomalyType.TREND_DIVERGENCE,
                    severity=severity,
                    detected_at=timestamps[-1],
                    expected_value=round(float(slope1), 4),
                    actual_value=round(float(slope2), 4),
                    confidence=round(min(1.0, abs(slope_change) / (abs(slope1) + 0.001)), 4),
                    cause=f"Trend changed from {slope1:.2f} to {slope2:.2f} per step",
                ))
        return anomalies

    def _detect_rate_acceleration(
        self,
        metric_name: str,
        values: list[float],
        timestamps: list[str],
    ) -> list[MetricAnomaly]:
        anomalies = []
        n = len(values)
        if n < 8:
            return anomalies
        third = n // 3
        chunk1 = values[:third]
        chunk2 = values[third:2*third]
        chunk3 = values[2*third:]
        if len(chunk1) < 2 or len(chunk2) < 2 or len(chunk3) < 2:
            return anomalies
        rate1 = abs(chunk2[-1] - chunk2[0]) / max(len(chunk2), 1)
        rate2 = abs(chunk3[-1] - chunk3[0]) / max(len(chunk3), 1)
        if rate1 > 0 and rate2 / rate1 > self._config.get("rate_acceleration_factor", 2.0):
            severity = min(10, int(rate2 / rate1 * 3))
            anomalies.append(MetricAnomaly(
                metric_name=metric_name,
                anomaly_type=AnomalyType.RATE_ACCELERATION,
                severity=severity,
                detected_at=timestamps[-1],
                expected_value=round(float(rate1), 4),
                actual_value=round(float(rate2), 4),
                confidence=round(min(1.0, rate2 / (rate2 + rate1)), 4),
                cause=f"Rate accelerated from {rate1:.4f} to {rate2:.4f}",
            ))
        return anomalies

    def _detect_missing_expected(
        self,
        metric_name: str,
        values: list[float],
        timestamps: list[str],
    ) -> list[MetricAnomaly]:
        anomalies = []
        if len(values) < 4:
            return anomalies
        arr = np.array(values[-4:], dtype=float)
        if np.all(arr == 0) or np.all(np.abs(arr - arr[0]) < 0.001):
            anomalies.append(MetricAnomaly(
                metric_name=metric_name,
                anomaly_type=AnomalyType.MISSING_EXPECTED,
                severity=7,
                detected_at=timestamps[-1],
                expected_value=0.0,
                actual_value=float(arr[-1]),
                confidence=0.9,
                cause=f"Metric {metric_name} appears frozen or missing at {timestamps[-1]}",
            ))
        return anomalies

    def _deduplicate(self, anomalies: list[MetricAnomaly]) -> list[MetricAnomaly]:
        seen = {}
        deduped = []
        for a in anomalies:
            key = (a.metric_name, a.anomaly_type.value, a.detected_at[:13])
            existing = seen.get(key)
            if existing is None or a.severity > existing.severity:
                seen[key] = a
        return list(seen.values())

    def _estimate_cause(self, metric: str, expected: float, actual: float, context: dict) -> str:
        diff = actual - expected
        pct = diff / abs(expected) if expected != 0 else float("inf")
        if abs(pct) > 2.0:
            return "Extreme deviation — possible sensor fault or configuration change"
        if pct > 0.5:
            return f"Unexpected rise of {pct*100:.0f}% — check for load spike or resource contention"
        if pct < -0.5:
            return f"Unexpected drop of {abs(pct)*100:.0f}% — check for service degradation or capacity loss"
        if expected == 0 and actual != 0:
            return "Unexpected non-zero reading when zero expected"
        if actual == 0 and expected != 0:
            return "Expected non-zero value but got zero — possible data pipeline failure"
        return f"Deviation of {abs(diff):.2f} from expected {expected:.2f}"

    def _pushover_alert(self, anomaly: MetricAnomaly) -> None:
        # Sends via Telegram now (2026-10-30, owner decision — Pushover is a
        # paid service). Still synchronous (httpx.Client, not AsyncClient) —
        # this method is called from sync code with no event loop available.
        try:
            from core.config import CONFIG
            import httpx
            token = CONFIG.get("api_keys", {}).get("telegram_bot_token", "")
            chat_id = CONFIG.get("api_keys", {}).get("telegram_chat_id", "")
            if not token or not chat_id:
                return
            msg = (
                f"[VECTOR ALERT] Anomaly: {anomaly.metric_name} "
                f"({anomaly.anomaly_type.value}) severity={anomaly.severity}/10 "
                f"expected={anomaly.expected_value:.2f} actual={anomaly.actual_value:.2f}"
            )
            with httpx.Client(timeout=5.0) as c:
                c.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    data={"chat_id": chat_id, "text": "\U0001F7E1 " + msg},
                )
            logger.info(f"[VECTOR][predictive_analytics] Telegram alert sent for {anomaly.metric_name}")
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Telegram alert failed: {e}")

if __name__ == "__main__":
    ap = AnomalyPredictor()
    values = [10, 12, 11, 13, 10, 12, 11, 50, 12, 11, 13, 10]
    anomalies = ap.detect("cpu_usage", values)
    assert isinstance(anomalies, list)
    assert len(anomalies) > 0
    assert all(isinstance(a, MetricAnomaly) for a in anomalies)
    assert all(isinstance(a.anomaly_type, AnomalyType) for a in anomalies)
    assert all(1 <= a.severity <= 10 for a in anomalies)

    empty = ap.detect("no_data", [1, 2])
    assert len(empty) == 0

    drift_vals = [1, 1.1, 1.2, 1.3, 1.4, 10, 11, 12, 13, 14]
    drift_anomalies = ap.detect("drift_test", drift_vals)
    assert len(drift_anomalies) > 0

    frozen_vals = [50, 50, 50, 50, 50]
    frozen = ap.detect("frozen_metric", frozen_vals)
    assert any(a.anomaly_type == AnomalyType.MISSING_EXPECTED for a in frozen)

    cause = ap._estimate_cause("cpu", 50.0, 95.0, {})
    assert isinstance(cause, str) and len(cause) > 0

    print("[OK] anomaly_predictor.py")
