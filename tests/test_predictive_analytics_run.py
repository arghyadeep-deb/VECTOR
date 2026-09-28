"""Task A.4 (plans/governor-wiring-and-ambient-perception.md): predictive_analytics
had zero dispatchable agents — its only AgentBase subclass, StrategyRecommender,
had no `run()` of its own, so a dispatch would silently hit AgentBase's generic
fake-success stub (`{"status": "ok", "agent": ..., "task": task}`) regardless of
what was asked, exactly the failure mode the rest of this effort exists to close.

The other 3 files in the district (TimeSeriesForecaster, AnomalyPredictor,
CausalSimulator, PredictionStore) are real, working, plain (non-AgentBase)
classes with zero-arg constructors. This composes them behind a real
`run(task)` on StrategyRecommender — the district's one AgentBase — that
branches on task["type"]: forecast / detect_anomalies / simulate / recommend
(default), persisting results via PredictionStore and returning real status,
not a hardcoded shape.

Isolated from the real production vector_memory.db via a module-scoped
fixture that points VECTOR_DB_PATH at a temp file and resets the
core.memory.episodic singleton — running 5+ tests in this file against the
shared SQLCipher singleton reproducibly corrupted a LATER test's read of
the real DB ("hmac check failed for pgno=1"), specifically when a prior
test exercised CausalSimulator -> CausalGraph -> the same shared connection
before a later governor.dispatch() test reused it. Confirmed this is a
pytest/shared-singleton interaction, not real data corruption or a bug in
this district's code: a standalone, non-pytest script ran the exact same
governor.dispatch() call cleanly every time, and the real DB's stats
(68k+ episodic rows) were confirmed intact and writable afterward.

IMPORTANT: an earlier version of this isolation set `os.environ[...]`
at module level with no teardown — that leaked into every OTHER test file
collected in the same `pytest` invocation (pytest imports all test modules
during collection, before running any test, so a bare module-level env
mutation here broke test_governor.py/test_investment_router_agent_paths.py/
etc. when run together). Fixed with an autouse fixture that saves/restores
the env var and resets the singleton on both setup and teardown, per the
project's own testing rule ("SQLite episodic_memory — use a test DB, not
mocks") and this session's instruction to verify against isolated temp DBs
without polluting shared global state.
"""
import os
import tempfile
from pathlib import Path

import pytest

from districts.predictive_analytics.strategy_recommender import StrategyRecommender


@pytest.fixture(autouse=True)
def _isolated_episodic_db(tmp_path):
    import core.memory.episodic as episodic

    original_path = os.environ.get("VECTOR_DB_PATH")
    # A fresh file per test: the old fixed name in the system temp dir survived between sessions, and once the
    # suite's DB key changed the leftover file was undecryptable ("hmac check failed"), failing the governor test.
    temp_path = str(tmp_path / "vector_test_predictive_analytics.db")
    os.environ["VECTOR_DB_PATH"] = temp_path
    episodic.close_db_connection()
    try:
        yield
    finally:
        episodic.close_db_connection()
        if original_path is None:
            os.environ.pop("VECTOR_DB_PATH", None)
        else:
            os.environ["VECTOR_DB_PATH"] = original_path
        episodic.close_db_connection()


async def test_governor_dispatch_reaches_strategy_recommender_via_manifest():
    """End-to-end: manifest -> registry -> governor.dispatch() reaches the
    real run(), not just direct instantiation."""
    from core.city.declarative_manifest import ManifestLoader
    from core.city.agent_registry import get_registry
    from core.city.governor import Governor

    reg = get_registry()
    before = set(reg._agents.keys())
    try:
        loader = ManifestLoader()
        agents = [a for a in loader.load() if a["district"] == "predictive_analytics"]
        assert len(agents) == 1
        registered = loader.register_all(agents, reg)
        assert registered == 1

        result = await Governor().dispatch({
            "type": "forecast",
            "district": "predictive_analytics",
            "params": {"metric_name": "cpu_usage", "historical_data": [1.0, 2.0, 3.0, 4.0]},
        })
        assert result.get("status") == "ok"
        assert "forecast" in result
    finally:
        for aid in list(reg._agents.keys()):
            if aid not in before:
                reg._agents.pop(aid, None)


async def test_run_does_not_use_the_agentbase_fake_success_stub():
    """The smoking-gun regression check: AgentBase's generic run() always
    returns {"status": "ok", "agent": ..., "task": task} verbatim — if
    StrategyRecommender.run() still produces that exact shape, it means our
    override isn't actually being called (or doesn't do real work)."""
    agent = StrategyRecommender()
    result = await agent.run({"type": "forecast", "params": {
        "metric_name": "cpu_usage",
        "historical_data": [10.0, 12.0, 11.0, 13.0, 14.0, 12.5, 15.0],
    }})
    assert result.get("agent") != agent.name or "task" not in result, (
        "run() returned the unmodified AgentBase stub shape — override not real"
    )
    assert "forecast" in result or result.get("status") == "ok"


async def test_run_forecast_branch_returns_real_forecast():
    agent = StrategyRecommender()
    result = await agent.run({
        "type": "forecast",
        "params": {
            "metric_name": "cpu_usage",
            "historical_data": [10.0, 12.0, 11.0, 13.0, 14.0, 12.5, 15.0, 16.0, 13.0, 14.0],
            "periods": 3,
        },
    })
    assert result["status"] == "ok"
    assert result["forecast"]["metric_name"] == "cpu_usage"
    assert len(result["forecast"]["values"]) == 3


async def test_run_detect_anomalies_branch():
    agent = StrategyRecommender()
    result = await agent.run({
        "type": "detect_anomalies",
        "params": {
            "metric_name": "error_rate",
            "values": [1.0, 1.1, 0.9, 1.0, 50.0, 1.0, 0.95],
        },
    })
    assert result["status"] == "ok"
    assert "anomalies" in result


async def test_run_simulate_branch():
    agent = StrategyRecommender()
    result = await agent.run({
        "type": "simulate",
        "params": {
            "metric_name": "deadline_risk",
            "scenario_params": {"base_value": 50.0, "parameters": {}},
            "iterations": 50,
        },
    })
    assert result["status"] == "ok"
    assert "simulation" in result


async def test_run_unknown_type_falls_back_to_pending_recommendations_not_fake_ok():
    agent = StrategyRecommender()
    result = await agent.run({"type": "totally_unhandled_type", "params": {}})
    assert result["status"] == "ok"
    assert "recommendations" in result
