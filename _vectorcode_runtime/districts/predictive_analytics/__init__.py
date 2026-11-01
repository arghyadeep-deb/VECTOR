
from loguru import logger

from districts.predictive_analytics.time_series_forecaster import TimeSeriesForecaster, ForecastResult, FORECAST_METRICS
from districts.predictive_analytics.anomaly_predictor import AnomalyPredictor, MetricAnomaly, AnomalyType
from districts.predictive_analytics.strategy_recommender import StrategyRecommender, Recommendation, RecommendationType
from districts.predictive_analytics.prediction_store import PredictionStore
from districts.predictive_analytics.causal_simulator import CausalSimulator, SimulationResult

logger.info("[VECTOR][predictive_analytics] Predictive Analytics district loaded")

__all__ = [
    "TimeSeriesForecaster",
    "ForecastResult",
    "FORECAST_METRICS",
    "AnomalyPredictor",
    "MetricAnomaly",
    "AnomalyType",
    "StrategyRecommender",
    "Recommendation",
    "RecommendationType",
    "PredictionStore",
    "CausalSimulator",
    "SimulationResult",
]

if __name__ == "__main__":
    from districts.predictive_analytics.time_series_forecaster import TimeSeriesForecaster, ForecastResult
    from districts.predictive_analytics.anomaly_predictor import AnomalyPredictor, MetricAnomaly, AnomalyType
    from districts.predictive_analytics.strategy_recommender import StrategyRecommender, Recommendation, RecommendationType
    from districts.predictive_analytics.prediction_store import PredictionStore
    from districts.predictive_analytics.causal_simulator import CausalSimulator, SimulationResult

    tf = TimeSeriesForecaster()
    ap = AnomalyPredictor()
    sr = StrategyRecommender()
    ps = PredictionStore(":memory:")
    cs = CausalSimulator()

    assert TimeSeriesForecaster
    assert AnomalyPredictor
    assert StrategyRecommender
    assert PredictionStore
    assert CausalSimulator

    print("[OK] predictive_analytics/__init__.py")
