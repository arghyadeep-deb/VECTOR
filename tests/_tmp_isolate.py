import asyncio
from core.city.governor import Governor
from core.city.agent_registry import get_registry
from districts.predictive_analytics.strategy_recommender import StrategyRecommender


async def test_minimal_repro():
    reg = get_registry()
    a = StrategyRecommender()
    a.capabilities = ["forecast"]
    reg.register(a)
    r = await Governor().dispatch({
        "type": "forecast",
        "district": "predictive_analytics",
        "params": {"metric_name": "cpu_usage", "historical_data": [1.0, 2.0, 3.0, 4.0]},
    })
    print("\nRESULT:", r.get("status"))
    assert r.get("status") == "ok"
