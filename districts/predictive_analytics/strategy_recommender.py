from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.city.agent_base import AgentBase
from districts.predictive_analytics.time_series_forecaster import ForecastResult
from districts.predictive_analytics.anomaly_predictor import MetricAnomaly, AnomalyType

class RecommendationType(Enum):
    TIME_MANAGEMENT = "time_management"
    HEALTH_ACTION = "health_action"
    PRODUCTIVITY_OPT = "productivity_opt"
    RISK_MITIGATION = "risk_mitigation"
    SECURITY_WARNING = "security_warning"
    SYSTEM_MAINTENANCE = "system_maintenance"
    LIFESTYLE_SUGGESTION = "lifestyle_suggestion"

@dataclass
class Recommendation:
    recommendation_type: RecommendationType
    title: str
    description: str
    priority: int
    metric: str
    confidence: float
    actions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    actionable: bool = True
    expires_at: Optional[str] = None
    source: str = "predictive_analytics"

class StrategyRecommender(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id=f"strategy_recommender_{int(datetime.now(timezone.utc).timestamp())}",
            name="strategy_recommender",
            district="predictive_analytics",
        )
        self.capabilities = ["detect_anomalies", "energy_level", "forecast", "health", "predict", "predictive_analytics", "recommend", "simulate", "strategy"]
        # Task A.4 (governor-wiring-and-ambient-perception.md): the district's
        # only AgentBase had no run() of its own, so governor.dispatch() hit
        # AgentBase's generic fake-success stub regardless of task type. This
        # composes the district's 3 other plain (non-AgentBase) helper
        # classes — all real, zero-arg-constructible — behind a real run().
        self._forecaster = None
        self._anomaly_predictor = None
        self._simulator = None
        self._store = None

    def _get_forecaster(self):
        if self._forecaster is None:
            from districts.predictive_analytics.time_series_forecaster import TimeSeriesForecaster
            self._forecaster = TimeSeriesForecaster()
        return self._forecaster

    def _get_anomaly_predictor(self):
        if self._anomaly_predictor is None:
            from districts.predictive_analytics.anomaly_predictor import AnomalyPredictor
            self._anomaly_predictor = AnomalyPredictor()
        return self._anomaly_predictor

    def _get_simulator(self):
        if self._simulator is None:
            from districts.predictive_analytics.causal_simulator import CausalSimulator
            self._simulator = CausalSimulator()
        return self._simulator

    def _get_store(self):
        if self._store is None:
            from districts.predictive_analytics.prediction_store import PredictionStore
            self._store = PredictionStore()
        return self._store

    async def run(self, task: dict) -> dict:
        """Governor-dispatchable entrypoint — branches on task["type"].

        Supported types: forecast, detect_anomalies, simulate (alias:
        what_if), recommend (alias: causal_query, experiment). Unknown
        types fall back to the store's pending recommendations rather than
        AgentBase's fake-success stub, so a dispatch always reflects real
        district state instead of a hardcoded shape.
        """
        task_type = task.get("type", "recommend")
        params = task.get("params", {}) or {}

        try:
            if task_type == "forecast":
                forecaster = self._get_forecaster()
                result = forecaster.forecast(
                    metric_name=params.get("metric_name", "unknown"),
                    historical_data=params.get("historical_data", []),
                    periods=params.get("periods", 7),
                )
                if not result.values:
                    return {
                        "status": "insufficient_data",
                        "error": "need at least 3 finite historical_data points to forecast",
                        "metric_name": result.metric_name,
                        "type": task_type,
                    }
                try:
                    self._get_store().store_forecast(result)
                except Exception as e:
                    logger.warning(f"[VECTOR][predictive_analytics] store_forecast failed: {e}")
                return {
                    "status": "ok",
                    "forecast": {
                        "metric_name": result.metric_name,
                        "timestamps": result.timestamps,
                        "values": result.values,
                        "confidence_lower": result.confidence_lower,
                        "confidence_upper": result.confidence_upper,
                        "model_used": result.model_used,
                    },
                }

            if task_type in ("detect_anomalies", "anomaly_prediction"):
                predictor = self._get_anomaly_predictor()
                if len(params.get("values", []) or []) < 3:
                    return {
                        "status": "insufficient_data",
                        "error": "need at least 3 values for anomaly detection; no anomalies is NOT a clean bill",
                        "type": task_type,
                    }
                anomalies = predictor.detect(
                    metric_name=params.get("metric_name", "unknown"),
                    values=params.get("values", []),
                    timestamps=params.get("timestamps"),
                )
                for a in anomalies:
                    try:
                        self._get_store().store_anomaly(a)
                    except Exception as e:
                        logger.warning(f"[VECTOR][predictive_analytics] store_anomaly failed: {e}")
                return {
                    "status": "ok",
                    "anomalies": [
                        {
                            "metric_name": a.metric_name,
                            "anomaly_type": a.anomaly_type.value,
                            "severity": a.severity,
                            "confidence": a.confidence,
                            "cause": a.cause,
                        }
                        for a in anomalies
                    ],
                }

            if task_type in ("simulate", "what_if", "causal_simulate"):
                simulator = self._get_simulator()
                result = simulator.run_monte_carlo(
                    metric_name=params.get("metric_name", "unknown"),
                    scenario_params=params.get("scenario_params", {}),
                    iterations=params.get("iterations", 1000),
                )
                if result.iterations == 0:
                    return {
                        "status": "error",
                        "error": "simulation failed (invalid scenario_params or iterations)",
                        "type": task_type,
                    }
                try:
                    self._get_store().store_simulation(result)
                except Exception as e:
                    logger.warning(f"[VECTOR][predictive_analytics] store_simulation failed: {e}")
                return {
                    "status": "ok",
                    "simulation": {
                        "scenario_name": result.scenario_name,
                        "iterations": result.iterations,
                        "mean_outcome": result.mean_outcome,
                        "confidence_interval": result.confidence_interval,
                        "converged": result.converged,
                    },
                }

            if task_type in ("recommend", "causal_query", "experiment", "strategy_recommend"):
                forecast = None
                if params.get("metric_name") and params.get("historical_data"):
                    forecast = self._get_forecaster().forecast(
                        metric_name=params["metric_name"],
                        historical_data=params["historical_data"],
                        periods=params.get("periods", 7),
                    )
                anomalies = []
                if params.get("metric_name") and params.get("values"):
                    anomalies = self._get_anomaly_predictor().detect(
                        metric_name=params["metric_name"],
                        values=params["values"],
                    )
                recs = self.evaluate(forecast=forecast, anomalies=anomalies, context=params.get("context", {}))
                for r in recs:
                    try:
                        self._get_store().store_recommendation(r)
                    except Exception as e:
                        logger.warning(f"[VECTOR][predictive_analytics] store_recommendation failed: {e}")
                return {
                    "status": "ok",
                    "recommendations": [
                        {
                            "type": r.recommendation_type.value,
                            "title": r.title,
                            "description": r.description,
                            "priority": r.priority,
                            "confidence": r.confidence,
                            "actions": r.actions,
                        }
                        for r in recs
                    ],
                }

            # Unknown type: reflect real pending state, not a fake-success stub.
            pending = self._get_store().get_pending_recommendations()
            return {"status": "ok", "recommendations": pending, "note": f"unhandled type '{task_type}', returning pending recommendations"}
        except Exception as e:
            logger.error(f"[VECTOR][predictive_analytics] run({task_type}) failed: {e}")
            return {"status": "error", "error": str(e), "type": task_type}

    def evaluate(
        self,
        forecast: Optional[ForecastResult] = None,
        anomalies: Optional[list[MetricAnomaly]] = None,
        context: Optional[dict] = None,
    ) -> list[Recommendation]:
        recommendations: list[Recommendation] = []
        if context is None:
            context = {}
        try:
            recommendations.extend(self._check_anomaly_impact(anomalies or [], context))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Anomaly impact check failed: {e}")
        try:
            recommendations.extend(self._check_thresholds(forecast, context))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Threshold check failed: {e}")
        try:
            recommendations.extend(self._check_trend_reversals(forecast, anomalies or [], context))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Trend reversal check failed: {e}")
        recommendations.sort(key=lambda r: r.priority)
        return recommendations

    def generate_all(
        self,
        predictions: dict[str, ForecastResult],
        anomalies: list[MetricAnomaly],
        simulations: list,
    ) -> list[Recommendation]:
        recs = []
        # Forecasts built on fabricated placeholder history must not drive alerts/recommendations.
        predictions = {k: v for k, v in predictions.items() if "synthetic_history" not in (v.model_used or "")}
        try:
            recs.extend(self._time_management_recs(predictions, anomalies))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] _time_management_recs failed: {e}")
        try:
            recs.extend(self._health_recs(predictions, anomalies))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] _health_recs failed: {e}")
        try:
            recs.extend(self._productivity_recs(predictions, anomalies))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] _productivity_recs failed: {e}")
        try:
            recs.extend(self._risk_recs(predictions, anomalies, simulations))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] _risk_recs failed: {e}")
        try:
            recs.extend(self._composite_recs(predictions, anomalies))
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] _composite_recs failed: {e}")
        recs.sort(key=lambda r: r.priority)
        logger.info(f"[VECTOR][predictive_analytics] generate_all: {len(recs)} recommendations")

        for r in recs:
            if r.priority <= 2:
                self._pushover_notify(r)

        return recs

    def _time_management_recs(
        self,
        predictions: dict[str, ForecastResult],
        anomalies: list[MetricAnomaly],
    ) -> list[Recommendation]:
        recs = []
        deadline_pred = predictions.get("deadline_proximity")
        if deadline_pred and deadline_pred.values:
            peak = max(deadline_pred.values)
            if peak > 10:
                recs.append(Recommendation(
                    recommendation_type=RecommendationType.TIME_MANAGEMENT,
                    title="Deadline pressure expected to increase",
                    description=f"Deadline proximity forecast peaks at {peak:.1f} days — plan workload accordingly",
                    priority=2,
                    metric="deadline_proximity",
                    confidence=0.75,
                    actions=["Review upcoming deadlines", "Allocate time blocks for critical tasks"],
                    evidence=[f"Forecast shows increasing deadline proximity trend"],
                    expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                ))

        task_anomalies = [a for a in anomalies if a.metric_name == "task_completion_rate"]
        if task_anomalies:
            worst = max(task_anomalies, key=lambda a: a.severity)
            if worst.severity >= 5:
                recs.append(Recommendation(
                    recommendation_type=RecommendationType.TIME_MANAGEMENT,
                    title="Task completion rate anomaly detected",
                    description=f"Task completion rate anomaly (severity={worst.severity}) — may need schedule adjustment",
                    priority=3,
                    metric="task_completion_rate",
                    confidence=worst.confidence,
                    actions=["Review current workload", "Consider deferring non-critical tasks"],
                    evidence=[f"Anomaly: expected={worst.expected_value:.1f} actual={worst.actual_value:.1f}"],
                ))

        return recs

    def _health_recs(
        self,
        predictions: dict[str, ForecastResult],
        anomalies: list[MetricAnomaly],
    ) -> list[Recommendation]:
        recs = []
        energy_pred = predictions.get("energy_level")
        if energy_pred and energy_pred.values:
            min_val = min(energy_pred.values)
            if min_val < 40:
                recs.append(Recommendation(
                    recommendation_type=RecommendationType.HEALTH_ACTION,
                    title="Energy level forecast below threshold",
                    description=f"Energy predicted to drop to {min_val:.0f}% — consider rest or health intervention",
                    priority=1,
                    metric="energy_level",
                    confidence=0.80,
                    actions=["Take a break and rest", "Check fatigue score", "Consider reducing workload"],
                    evidence=[f"Energy forecast minimum: {min_val:.1f}%"],
                ))

        health_anomalies = [a for a in anomalies if a.metric_name in ("energy_level", "cpu_usage", "memory_usage")]
        if len(health_anomalies) >= 2:
            recs.append(Recommendation(
                recommendation_type=RecommendationType.HEALTH_ACTION,
                title="Multiple health metrics show anomalies",
                description=f"{len(health_anomalies)} health-related anomalies detected",
                priority=1,
                metric=health_anomalies[0].metric_name,
                confidence=0.85,
                actions=["Check overall health status", "Review recent activity patterns"],
                evidence=[f"{a.metric_name}: severity={a.severity}" for a in health_anomalies],
            ))

        return recs

    def _productivity_recs(
        self,
        predictions: dict[str, ForecastResult],
        anomalies: list[MetricAnomaly],
    ) -> list[Recommendation]:
        recs = []
        comp_pred = predictions.get("task_completion_rate")
        if comp_pred and comp_pred.values:
            avg = sum(comp_pred.values) / len(comp_pred.values)
            if avg < 70:
                recs.append(Recommendation(
                    recommendation_type=RecommendationType.PRODUCTIVITY_OPT,
                    title="Task completion rate forecast below target",
                    description=f"Average predicted completion rate: {avg:.1f}% (target: >70%)",
                    priority=2,
                    metric="task_completion_rate",
                    confidence=0.78,
                    actions=["Review task priority ordering", "Break large tasks into smaller chunks"],
                    evidence=[f"Predicted average: {avg:.1f}% over {len(comp_pred.values)} periods"],
                ))

        user_pred = predictions.get("active_users")
        if user_pred and user_pred.values:
            min_users = min(user_pred.values)
            if min_users < 2:
                recs.append(Recommendation(
                    recommendation_type=RecommendationType.PRODUCTIVITY_OPT,
                    title="Low user activity forecast",
                    description=f"Active users forecast as low as {min_users:.0f}",
                    priority=4,
                    metric="active_users",
                    confidence=0.60,
                    actions=["Consider engagement strategies", "Review if system is accessible"],
                    evidence=[f"Minimum forecast: {min_users:.0f}"],
                ))

        return recs

    def _risk_recs(
        self,
        predictions: dict[str, ForecastResult],
        anomalies: list[MetricAnomaly],
        simulations: list,
    ) -> list[Recommendation]:
        recs = []
        security_anomalies = [a for a in anomalies if a.metric_name == "security_incident_rate"]
        if security_anomalies:
            s = max(security_anomalies, key=lambda a: a.severity)
            recs.append(Recommendation(
                recommendation_type=RecommendationType.SECURITY_WARNING,
                title=f"Security incident rate anomaly (severity={s.severity})",
                description=f"Unexpected security metric deviation: expected={s.expected_value:.2f} actual={s.actual_value:.2f}",
                priority=1,
                metric="security_incident_rate",
                confidence=s.confidence,
                actions=["Review security logs", "Check for unauthorized access", "Audit recent changes"],
                evidence=[f"Anomaly type: {s.anomaly_type.value}"],
                source="predictive_analytics:risk",
            ))

        budget_pred = predictions.get("daily_budget_remaining")
        if budget_pred and budget_pred.values:
            min_budget = min(budget_pred.values)
            if min_budget < 50:
                recs.append(Recommendation(
                    recommendation_type=RecommendationType.RISK_MITIGATION,
                    title="Budget may run low",
                    description=f"Daily budget forecast drops to {min_budget:.0f} INR — review spending",
                    priority=2,
                    metric="daily_budget_remaining",
                    confidence=0.75,
                    actions=["Review recent expenses", "Identify non-essential spending", "Adjust budget allocations"],
                    evidence=[f"Minimum forecast: {min_budget:.1f}"],
                ))

        if simulations:
            for sim in simulations:
                if isinstance(sim, dict) and sim.get("unusual", False):
                    recs.append(Recommendation(
                        recommendation_type=RecommendationType.RISK_MITIGATION,
                        title="Simulation detected unusual scenario",
                        description=f"Scenario '{sim.get('scenario_name', 'unknown')}' shows elevated risk",
                        priority=2,
                        metric=sim.get("scenario_name", "unknown"),
                        confidence=0.70,
                        actions=["Review simulation details", "Prepare contingency plan"],
                        evidence=[f"Simulation mean: {sim.get('mean_outcome', 0):.2f}"],
                    ))

        return recs

    def _composite_recs(
        self,
        predictions: dict[str, ForecastResult],
        anomalies: list[MetricAnomaly],
    ) -> list[Recommendation]:
        recs = []
        system_metrics = ["cpu_usage", "memory_usage", "response_time", "error_rate", "throughput"]
        system_forecasts = {k: v for k, v in predictions.items() if k in system_metrics and v.values}
        system_anomalies = [a for a in anomalies if a.metric_name in system_metrics]
        if len(system_anomalies) >= 2 or (system_forecasts and len(system_forecasts) >= 3):
            recs.append(Recommendation(
                recommendation_type=RecommendationType.SYSTEM_MAINTENANCE,
                title="System health assessment recommended",
                description=f"{len(system_forecasts)} system metrics tracked, {len(system_anomalies)} anomalies",
                priority=3,
                metric="system",
                confidence=0.70,
                actions=["Run system diagnostics", "Check resource usage trends", "Review system logs"],
                evidence=[
                    f"Metrics tracked: {', '.join(system_forecasts.keys())}",
                    f"Anomalies: {len(system_anomalies)}",
                ],
            ))

        high_severity = [a for a in anomalies if a.severity >= 7]
        if high_severity:
            recs.append(Recommendation(
                recommendation_type=RecommendationType.RISK_MITIGATION,
                title=f"High-severity anomalies require attention ({len(high_severity)})",
                description=f"Found {len(high_severity)} anomalies with severity >= 7",
                priority=1,
                metric=high_severity[0].metric_name,
                confidence=0.90,
                actions=["Investigate all high-severity anomalies immediately", "Consider system rollback if recent changes"],
                evidence=[f"{a.metric_name}: severity={a.severity}" for a in high_severity],
            ))

        return recs

    def _check_anomaly_impact(
        self,
        anomalies: list[MetricAnomaly],
        context: dict,
    ) -> list[Recommendation]:
        recs = []
        severe = [a for a in anomalies if a.severity >= 7]
        for a in severe:
            rtype = RecommendationType.SECURITY_WARNING if "security" in a.metric_name else RecommendationType.RISK_MITIGATION
            recs.append(Recommendation(
                recommendation_type=rtype,
                title=f"Severe {a.anomaly_type.value} in {a.metric_name}",
                description=f"{a.metric_name}: expected={a.expected_value:.2f} actual={a.actual_value:.2f} severity={a.severity}/10",
                priority=1 if a.severity >= 9 else 2,
                metric=a.metric_name,
                confidence=float(a.confidence),
                actions=[
                    f"Review {a.metric_name} at {a.detected_at}",
                    "Check correlated events in system logs",
                ],
                evidence=[a.cause] if a.cause else [f"Raw deviation: {a.actual_value - a.expected_value:.2f}"],
            ))

        moderate = [a for a in anomalies if 3 <= a.severity < 7]
        if len(moderate) >= 3:
            recs.append(Recommendation(
                recommendation_type=RecommendationType.SYSTEM_MAINTENANCE,
                title=f"Multiple moderate anomalies ({len(moderate)})",
                description=f"Detected {len(moderate)} anomalies with moderate severity",
                priority=3,
                metric=moderate[0].metric_name,
                confidence=0.5,
                actions=["Batch review all moderate anomalies", "Check for common root cause"],
                evidence=[f"{a.metric_name}: sev={a.severity}" for a in moderate[:5]],
            ))

        return recs

    def _check_thresholds(
        self,
        forecast: Optional[ForecastResult],
        context: dict,
    ) -> list[Recommendation]:
        recs = []
        if forecast is None or not forecast.values or "synthetic_history" in (forecast.model_used or ""):
            return recs

        from districts.predictive_analytics.time_series_forecaster import FORECAST_METRICS
        config = FORECAST_METRICS.get(forecast.metric_name, {})

        critical_high = config.get("critical_high")
        critical_low = config.get("critical_low")
        upper_bound = config.get("upper_bound")
        lower_bound = config.get("lower_bound")

        approaching_critical = False
        for val in forecast.values:
            if critical_high is not None and val >= critical_high * 0.9:
                approaching_critical = True
            if critical_low is not None and val <= critical_low * 1.1:
                approaching_critical = True
            if upper_bound is not None and val > upper_bound:
                approaching_critical = True
            if lower_bound is not None and val < lower_bound:
                approaching_critical = True

        if approaching_critical:
            peak = max(forecast.values) if forecast.values else 0
            domain = config.get("domain", "system")
            rtype_map = {
                "health": RecommendationType.HEALTH_ACTION,
                "security": RecommendationType.SECURITY_WARNING,
                "finance": RecommendationType.RISK_MITIGATION,
                "deadline": RecommendationType.TIME_MANAGEMENT,
            }
            rtype = rtype_map.get(domain, RecommendationType.SYSTEM_MAINTENANCE)
            recs.append(Recommendation(
                recommendation_type=rtype,
                title=f"{forecast.metric_name} approaching critical threshold",
                description=f"Forecast shows {forecast.metric_name} nearing critical bounds: peak {peak:.2f}",
                priority=2 if domain in ("health", "security") else 3,
                metric=forecast.metric_name,
                confidence=0.85,
                actions=[f"Investigate {forecast.metric_name} trend", "Prepare mitigation plan"],
                evidence=[f"Peak forecast value: {peak:.2f}", f"Domain: {domain}"],
            ))

        return recs

    def _check_trend_reversals(
        self,
        forecast: Optional[ForecastResult],
        anomalies: list[MetricAnomaly],
        context: dict,
    ) -> list[Recommendation]:
        recs = []
        if forecast is None or not forecast.values:
            return recs

        has_drift = any(a.anomaly_type == AnomalyType.TREND_DIVERGENCE for a in anomalies)
        has_spike = any(a.anomaly_type == AnomalyType.VALUE_OUT_OF_RANGE for a in anomalies)
        has_downward_trend = False
        has_upward_trend = False

        if len(forecast.values) >= 2:
            first_half = forecast.values[:len(forecast.values) // 2]
            second_half = forecast.values[len(forecast.values) // 2:]
            avg_first = sum(first_half) / len(first_half) if first_half else 0
            avg_second = sum(second_half) / len(second_half) if second_half else 0
            has_downward_trend = avg_second < avg_first * 0.95
            has_upward_trend = avg_second > avg_first * 1.05

        if has_drift and has_downward_trend:
            recs.append(Recommendation(
                recommendation_type=RecommendationType.RISK_MITIGATION,
                title=f"Sustained downward trend in {forecast.metric_name}",
                description="Drift detection combined with downward forecast trend indicates structural issue",
                priority=2,
                metric=forecast.metric_name,
                confidence=0.8,
                actions=["Root cause analysis for structural degradation", "Check for resource leaks"],
                evidence=["Drift confirmed by anomaly predictor", "Forecast trend shows continued decline"],
            ))

        if has_upward_trend and not has_drift and not has_spike:
            recs.append(Recommendation(
                recommendation_type=RecommendationType.PRODUCTIVITY_OPT,
                title=f"{forecast.metric_name} showing healthy improvement",
                description=f"Consistent improvement in {forecast.metric_name} without anomalies",
                priority=5,
                metric=forecast.metric_name,
                confidence=0.7,
                actions=["Document what changed", "Consider applying similar patterns elsewhere"],
                evidence=[f"Upward trend of {avg_second - avg_first:.2f} across forecast horizon"],
                source="predictive_analytics:trend",
            ))

        return recs

    def _pushover_notify(self, rec: Recommendation) -> None:
        try:
            from core.config import CONFIG
            import httpx
            token = CONFIG.get("api_keys", {}).get("pushover_token", "")
            user = CONFIG.get("api_keys", {}).get("pushover_user", "")
            if not token or not user:
                return
            msg = f"[VECTOR REC] {rec.title} | {rec.description[:100]} | priority={rec.priority}"
            with httpx.Client(timeout=5.0) as c:
                c.post(
                    "https://api.pushover.net/1/messages.json",
                    json={"token": token, "user": user, "message": msg, "priority": 1},
                )
            logger.debug(f"[VECTOR][predictive_analytics] Pushover sent for rec: {rec.title[:40]}")
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Pushover notify failed: {e}")

    def health_check(self) -> dict:
        return {
            "agent": self.name,
            "district": self.district,
            "hp": self.health_points,
            "status": self.get_status(),
            "recommendation_types": [rt.value for rt in RecommendationType],
        }

    def fallback_chain(self) -> list[str]:
        return ["heuristic_rules", "llm_strategy"]

if __name__ == "__main__":
    sr = StrategyRecommender()
    from districts.predictive_analytics.time_series_forecaster import ForecastResult
    from districts.predictive_analytics.anomaly_predictor import MetricAnomaly, AnomalyType

    forecast = ForecastResult(
        metric_name="cpu_usage",
        timestamps=["2026-01-01T00:00:00"] * 5,
        values=[85, 87, 90, 92, 95],
        confidence_lower=[80] * 5,
        confidence_upper=[98] * 5,
        model_used="moving_average",
        accuracy_score=0.85,
    )
    anomalies = [
        MetricAnomaly(
            metric_name="cpu_usage",
            anomaly_type=AnomalyType.VALUE_OUT_OF_RANGE,
            severity=8,
            detected_at="2026-01-01T00:00:00",
            expected_value=75.0,
            actual_value=95.0,
            confidence=0.9,
            cause="CPU spike detected",
        ),
    ]
    recs = sr.evaluate(forecast=forecast, anomalies=anomalies)
    assert isinstance(recs, list)
    assert len(recs) > 0
    assert all(isinstance(r, Recommendation) for r in recs)
    assert all(isinstance(r.recommendation_type, RecommendationType) for r in recs)
    assert all(1 <= r.priority <= 5 for r in recs)

    all_recs = sr.generate_all(
        predictions={"cpu_usage": forecast, "energy_level": forecast, "deadline_proximity": forecast, "task_completion_rate": forecast, "daily_budget_remaining": forecast, "active_users": forecast, "security_incident_rate": forecast},
        anomalies=anomalies,
        simulations=[],
    )
    assert len(all_recs) > 0

    recs2 = sr.evaluate()
    assert isinstance(recs2, list)
    print("[OK] strategy_recommender.py")
