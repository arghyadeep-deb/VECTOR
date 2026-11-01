
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone, timedelta
import os
from numbers import Real
import numpy as np

from loguru import logger


FORECAST_METRICS = {
    "cpu_usage": {"unit": "%", "lower_bound": 0, "upper_bound": 100, "critical_high": 90, "domain": "health"},
    "memory_usage": {"unit": "%", "lower_bound": 0, "upper_bound": 100, "critical_high": 85, "domain": "health"},
    "response_time": {"unit": "ms", "lower_bound": 0, "upper_bound": None, "critical_high": 2000, "domain": "system"},
    "error_rate": {"unit": "%", "lower_bound": 0, "upper_bound": 100, "critical_high": 5, "domain": "system"},
    "throughput": {"unit": "req/s", "lower_bound": 0, "upper_bound": None, "critical_low": 10, "domain": "system"},
    "memory_curator_hit_rate": {"unit": "%", "lower_bound": 0, "upper_bound": 100, "critical_low": 60, "domain": "system"},
    "token_usage": {"unit": "tokens", "lower_bound": 0, "upper_bound": None, "critical_high": 8000, "domain": "system"},
    "active_users": {"unit": "count", "lower_bound": 0, "upper_bound": None, "critical_low": 1, "domain": "productivity"},
    "task_completion_rate": {"unit": "%", "lower_bound": 0, "upper_bound": 100, "critical_low": 70, "domain": "productivity"},
    "inference_latency": {"unit": "ms", "lower_bound": 0, "upper_bound": None, "critical_high": 5000, "domain": "system"},
    "energy_level": {"unit": "%", "lower_bound": 0, "upper_bound": 100, "critical_low": 30, "domain": "health"},
    "daily_budget_remaining": {"unit": "inr", "lower_bound": 0, "upper_bound": None, "critical_low": 50, "domain": "finance"},
    "deadline_proximity": {"unit": "days", "lower_bound": 0, "upper_bound": None, "critical_high": 14, "domain": "deadline"},
    "security_incident_rate": {"unit": "count/day", "lower_bound": 0, "upper_bound": None, "critical_high": 3, "domain": "security"},
}


@dataclass
class ForecastResult:
    metric_name: str
    timestamps: list
    values: list
    confidence_lower: list
    confidence_upper: list
    model_used: str = "unknown"
    accuracy_score: Optional[float] = None


class TimeSeriesForecaster:
    def __init__(self):
        self._prophet_available = False
        self._Prophet = None
        try:
            from prophet import Prophet
            self._Prophet = Prophet
            self._prophet_available = True
            logger.info("[VECTOR][predictive_analytics] Prophet available")
        except ImportError:
            logger.warning("[VECTOR][predictive_analytics] Prophet not installed")

        self._arima_available = False
        self._ARIMA = None
        try:
            from statsmodels.tsa.arima.model import ARIMA
            self._ARIMA = ARIMA
            self._arima_available = True
            logger.info("[VECTOR][predictive_analytics] ARIMA available")
        except ImportError:
            logger.warning("[VECTOR][predictive_analytics] statsmodels not installed")

    def forecast(
        self,
        metric_name: str,
        historical_data: list[float],
        periods: int = 7,
    ) -> ForecastResult:
        if historical_data:
            finite = [v for v in historical_data if isinstance(v, Real) and np.isfinite(v)]
            if len(finite) != len(historical_data):
                logger.warning(
                    "[VECTOR][predictive_analytics] {}: dropped {} non-finite/non-numeric points",
                    metric_name, len(historical_data) - len(finite),
                )
                historical_data = finite
        if not historical_data or len(historical_data) < 3:
            logger.warning(f"[VECTOR][predictive_analytics] Insufficient data for {metric_name}")
            return ForecastResult(
                metric_name=metric_name,
                timestamps=[],
                values=[],
                confidence_lower=[],
                confidence_upper=[],
                model_used="none",
            )

        try:
            if len(historical_data) >= 10 and self._prophet_available and self._arima_available:
                return self._ensemble_forecast(metric_name, historical_data, periods)
            if self._prophet_available and len(historical_data) >= 10:
                return self._prophet_forecast(metric_name, historical_data, periods)
            if self._arima_available and len(historical_data) >= 6:
                return self._arima_forecast(metric_name, historical_data, periods)
            return self._moving_average_forecast(metric_name, historical_data, periods)
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Forecast failed for {metric_name}: {e}")
            try:
                return self._moving_average_forecast(metric_name, historical_data, periods)
            except Exception:
                return self._naive_forecast(metric_name, historical_data, periods)

    def forecast_all(self, metrics_config: dict = FORECAST_METRICS) -> dict[str, ForecastResult]:
        results = {}
        for metric_name in metrics_config:
            try:
                history = self._collect_history(metric_name, days=30)
                synthetic = not history
                if synthetic:
                    history = self._synthetic_history(metric_name)
                result = self.forecast(metric_name, history, periods=7)
                if synthetic:
                    # Fabricated placeholder history: never present it as a real model forecast.
                    result.model_used = f"{result.model_used}+synthetic_history"
                    logger.warning(
                        "[VECTOR][predictive_analytics] {}: no real history, forecast is synthetic", metric_name
                    )
                results[metric_name] = result
            except Exception as e:
                logger.warning(f"[VECTOR][predictive_analytics] forecast_all failed for {metric_name}: {e}")
        logger.info(f"[VECTOR][predictive_analytics] forecast_all: {len(results)} metrics")
        return results

    def _collect_history(self, metric: str, days: int = 30) -> list[float]:
        try:
            from districts.predictive_analytics.prediction_store import PredictionStore
            store = PredictionStore()
            rows = store._conn.execute(
                """SELECT actual_value FROM prediction_accuracy
                   WHERE metric_name = ? ORDER BY computed_at DESC LIMIT ?""",
                (metric, days),
            ).fetchall()
            store._conn.close()
            if rows:
                return [r[0] for r in reversed(rows)]
        except Exception as e:
            logger.warning("[VECTOR][predictive_analytics] history read failed for {}: {}", metric, e)
        if os.environ.get("VECTOR_PREDICTIVE_USE_MEMORY") != "1":
            return []

        try:
            from core.config import CONFIG
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            episodes = mem.recall(f"metric:{metric}", limit=min(days, 50))
            if episodes:
                vals = []
                for ep in episodes:
                    ctx = ep.get("context") or {}
                    if isinstance(ctx, str):
                        import json
                        try:
                            ctx = json.loads(ctx)
                        except Exception:
                            ctx = {}
                    v = ctx.get(metric)
                    if v is not None:
                        try:
                            vals.append(float(v))
                        except (ValueError, TypeError):
                            logger.warning("[VECTOR][predictive_analytics] non-numeric {} in episode skipped", metric)
                if len(vals) >= 3:
                    return vals[-days:]
        except Exception as e:
            logger.warning("[VECTOR][predictive_analytics] episodic history read failed for {}: {}", metric, e)
        return []

    def _synthetic_history(self, metric_name: str) -> list[float]:
        cfg = FORECAST_METRICS.get(metric_name, {})
        mid = (cfg.get("upper_bound", 100) or 100) / 2
        if cfg.get("critical_high"):
            mid = cfg["critical_high"] * 0.7
        if cfg.get("critical_low"):
            mid = cfg["critical_low"] * 1.5
        rng = np.random.default_rng(hash(metric_name) % 2**32)
        trend = rng.normal(0, 1.0, 14).tolist()
        base = mid if isinstance(mid, (int, float)) else 50.0
        return [max(0, base + t + rng.uniform(-2, 2)) for t in trend]

    def _ensemble_forecast(
        self,
        metric_name: str,
        historical_data: list[float],
        periods: int = 7,
    ) -> ForecastResult:
        prophet_result = self._prophet_forecast(metric_name, historical_data, periods)
        arima_result = self._arima_forecast(metric_name, historical_data, periods)
        # A sub-model that failed falls back internally to moving_average; don't blend that in as "prophet"/"arima".
        weight_p = 0.6 if prophet_result.model_used == "prophet" else 0.0
        weight_a = 0.4 if arima_result.model_used == "arima" else 0.0
        if weight_p + weight_a == 0:
            return self._moving_average_forecast(metric_name, historical_data, periods)
        if weight_p == 0.0:
            return arima_result
        if weight_a == 0.0:
            return prophet_result
        weight_p = weight_p / (weight_p + weight_a)
        weight_a = weight_a / (weight_p + weight_a)

        values = []
        lower = []
        upper = []
        timestamps = prophet_result.timestamps if prophet_result.timestamps else arima_result.timestamps
        for i in range(periods):
            v_p = prophet_result.values[i] if i < len(prophet_result.values) else 0
            v_a = arima_result.values[i] if i < len(arima_result.values) else 0
            l_p = prophet_result.confidence_lower[i] if i < len(prophet_result.confidence_lower) else v_p * 0.8
            l_a = arima_result.confidence_lower[i] if i < len(arima_result.confidence_lower) else v_a * 0.8
            u_p = prophet_result.confidence_upper[i] if i < len(prophet_result.confidence_upper) else v_p * 1.2
            u_a = arima_result.confidence_upper[i] if i < len(arima_result.confidence_upper) else v_a * 1.2
            values.append(v_p * weight_p + v_a * weight_a)
            lower.append(l_p * weight_p + l_a * weight_a)
            upper.append(u_p * weight_p + u_a * weight_a)

        return ForecastResult(
            metric_name=metric_name,
            timestamps=timestamps,
            values=values,
            confidence_lower=lower,
            confidence_upper=upper,
            model_used="ensemble",
        )

    def _prophet_forecast(
        self,
        metric_name: str,
        historical_data: list[float],
        periods: int = 7,
    ) -> ForecastResult:
        try:
            import pandas as pd
            df = pd.DataFrame({
                "ds": pd.date_range(end=pd.Timestamp.now(), periods=len(historical_data), freq="D"),
                "y": historical_data,
            })
            model = self._Prophet(
                yearly_seasonality=False,
                weekly_seasonality=True,
                daily_seasonality=False,
                interval_width=0.80,
            )
            model.fit(df)
            future = model.make_future_dataframe(periods=periods, freq="D")
            forecast = model.predict(future)
            forecast_values = forecast["yhat"].tail(periods).tolist()
            lower = forecast["yhat_lower"].tail(periods).tolist()
            upper = forecast["yhat_upper"].tail(periods).tolist()
            timestamps = [t.isoformat() for t in forecast["ds"].tail(periods)]

            return ForecastResult(
                metric_name=metric_name,
                timestamps=timestamps,
                values=[float(v) for v in forecast_values],
                confidence_lower=[float(v) for v in lower],
                confidence_upper=[float(v) for v in upper],
                model_used="prophet",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Prophet failed: {e}")
            return self._moving_average_forecast(metric_name, historical_data, periods)

    def _arima_forecast(
        self,
        metric_name: str,
        historical_data: list[float],
        periods: int = 7,
    ) -> ForecastResult:
        try:
            import pandas as pd
            series = pd.Series(historical_data, dtype=float)
            model = self._ARIMA(series, order=(2, 1, 2))
            fitted = model.fit()
            forecast_result = fitted.forecast(steps=periods)
            forecast_values = forecast_result.tolist()
            resid = fitted.resid
            std_resid = float(np.std(resid)) if len(resid) > 1 else float(np.std(historical_data)) * 0.1
            timestamps = [
                (datetime.now(timezone.utc) + timedelta(days=i + 1)).isoformat()
                for i in range(periods)
            ]
            lower = [v - 1.96 * std_resid for v in forecast_values]
            upper = [v + 1.96 * std_resid for v in forecast_values]

            return ForecastResult(
                metric_name=metric_name,
                timestamps=timestamps,
                values=forecast_values,
                confidence_lower=lower,
                confidence_upper=upper,
                model_used="arima",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] ARIMA failed: {e}")
            return self._moving_average_forecast(metric_name, historical_data, periods)

    def _moving_average_forecast(
        self,
        metric_name: str,
        historical_data: list[float],
        periods: int = 7,
    ) -> ForecastResult:
        try:
            arr = np.array(historical_data, dtype=float)
            window = min(7, len(arr))
            if window <= 0:
                window = 3
            weights = np.ones(window) / window
            smoothed = np.convolve(arr, weights, mode="valid")
            if len(smoothed) == 0:
                smoothed = arr
            last_value = float(smoothed[-1]) if len(smoothed) > 0 else float(arr[-1])
            recent_trend = 0.0
            if len(smoothed) >= 2:
                recent_trend = float(smoothed[-1] - smoothed[0]) / max(len(smoothed), 1)
            std = float(np.std(arr)) if len(arr) > 1 else last_value * 0.1
            forecast_values = []
            lower_bound = []
            upper_bound = []
            timestamps = []
            for i in range(periods):
                v = last_value + recent_trend * (i + 1)
                forecast_values.append(v)
                lower_bound.append(v - 1.96 * std)
                upper_bound.append(v + 1.96 * std)
                ts = (datetime.now(timezone.utc) + timedelta(days=i + 1)).isoformat()
                timestamps.append(ts)

            return ForecastResult(
                metric_name=metric_name,
                timestamps=timestamps,
                values=forecast_values,
                confidence_lower=lower_bound,
                confidence_upper=upper_bound,
                model_used="moving_average",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] MA forecast failed: {e}")
            return self._naive_forecast(metric_name, historical_data, periods)

    def _naive_forecast(
        self,
        metric_name: str,
        historical_data: list[float],
        periods: int = 7,
    ) -> ForecastResult:
        last = historical_data[-1] if historical_data else 50.0
        values = [float(last)] * periods
        lower = [float(last) * 0.9] * periods
        upper = [float(last) * 1.1] * periods
        timestamps = [
            (datetime.now(timezone.utc) + timedelta(days=i + 1)).isoformat()
            for i in range(periods)
        ]
        return ForecastResult(
            metric_name=metric_name,
            timestamps=timestamps,
            values=values,
            confidence_lower=lower,
            confidence_upper=upper,
            model_used="naive",
        )

    def compute_confidence_intervals(
        self, values: list[float], ci_80: bool = True, ci_95: bool = True
    ) -> dict:
        if not values:
            return {"ci_80_lower": [], "ci_80_upper": [], "ci_95_lower": [], "ci_95_upper": []}
        arr = np.array(values, dtype=float)
        std = float(np.std(arr)) if len(arr) > 1 else 1.0
        result = {}
        if ci_80:
            result["ci_80_lower"] = [v - 1.28 * std for v in values]
            result["ci_80_upper"] = [v + 1.28 * std for v in values]
        if ci_95:
            result["ci_95_lower"] = [v - 1.96 * std for v in values]
            result["ci_95_upper"] = [v + 1.96 * std for v in values]
        return result

    def calculate_accuracy(self, actual: list[float], predicted: list[float]) -> float:
        try:
            if not actual or not predicted:
                return 0.0
            actual_arr = np.array(actual, dtype=float)
            predicted_arr = np.array(predicted[:len(actual)], dtype=float)
            if len(actual_arr) != len(predicted_arr) or len(actual_arr) < 2:
                ss_res = np.sum((actual_arr - predicted_arr) ** 2)
                ss_tot = np.sum((actual_arr - np.mean(actual_arr)) ** 2)
                if ss_tot == 0:
                    mape = np.mean(np.abs((actual_arr - predicted_arr) / (actual_arr + 1e-10))) * 100
                    return max(0.0, 100.0 - mape)
                r2 = 1 - (ss_res / ss_tot)
                return max(0.0, float(r2))
            else:
                mape = np.mean(np.abs((actual_arr - predicted_arr) / (actual_arr + 1e-10))) * 100
                return max(0.0, 100.0 - mape)
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Accuracy calc failed: {e}")
            return 0.0


if __name__ == "__main__":
    tf = TimeSeriesForecaster()
    data = [10 + i + (i % 3) * 2 for i in range(30)]
    result = tf.forecast("cpu_usage", data, periods=5)
    assert result.metric_name == "cpu_usage"
    assert len(result.values) == 5
    assert result.model_used in ("prophet", "moving_average", "none", "ensemble", "arima", "naive")

    all_results = tf.forecast_all()
    assert len(all_results) >= 14

    ci = tf.compute_confidence_intervals([10, 20, 30])
    assert "ci_80_lower" in ci
    assert "ci_95_lower" in ci

    acc = tf.calculate_accuracy(data[:5], data[5:10])
    assert isinstance(acc, float)

    empty = tf.forecast("memory_usage", [])
    assert len(empty.values) == 0
    print("[OK] time_series_forecaster.py")
