import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from unittest.mock import patch, MagicMock

import pytest

from districts.predictive_analytics.causal_simulator import CausalSimulator, SimulationResult


@pytest.fixture
def simulator():
    return CausalSimulator()


@pytest.fixture
def sample_params():
    return {
        "base_value": 100.0,
        "parameters": {
            "demand": {"distribution": "normal", "mean": 5.0, "std": 2.0, "weight": 1.0},
            "cost": {"distribution": "uniform", "low": -3.0, "high": 1.0, "weight": 0.5},
            "efficiency": {"distribution": "triangular", "mode": 2.0, "low": -1.0, "high": 5.0, "weight": 0.8},
        },
    }


def test_run_monte_carlo(simulator, sample_params):
    result = simulator.run_monte_carlo("system_load", sample_params, iterations=500)
    assert result.scenario_name == "system_load"
    assert result.iterations == 500
    assert len(result.outcomes) == 500
    assert isinstance(result.mean_outcome, float)
    assert len(result.confidence_interval) == 2
    assert len(result.risk_factors) > 0


def test_monte_carlo_small_iterations(simulator):
    params = {"base_value": 50.0, "parameters": {}}
    result = simulator.run_monte_carlo("minimal", params, iterations=10)
    assert result.iterations == 10
    assert result.mean_outcome == 50.0


def test_convergence_detection(simulator):
    params = {"base_value": 100.0, "parameters": {}}
    result = simulator.run_monte_carlo("convergent", params, iterations=1000)
    assert isinstance(result.converged, bool)


def test_evaluate_risk(simulator, sample_params):
    result = simulator.run_monte_carlo("risk_test", sample_params, iterations=200)
    risk = simulator.evaluate_risk(result, threshold=120.0)
    assert isinstance(risk, float)
    assert 0.0 <= risk <= 1.0


def test_evaluate_risk_empty(simulator):
    result = SimulationResult(
        scenario_name="empty", iterations=0, outcomes=[],
        mean_outcome=0.0, confidence_interval=(0.0, 0.0),
    )
    assert simulator.evaluate_risk(result, threshold=10.0) == 0.0


def test_suggest_scenarios(simulator):
    scenarios = simulator.suggest_scenarios()
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 3
    for sc in scenarios:
        assert "name" in sc
        assert "base_value" in sc
        assert "parameters" in sc


def test_run_custom_scenario(simulator):
    interventions = {
        "base_value": 200.0,
        "parameters": {
            "x": {"distribution": "normal", "mean": 10.0, "std": 1.0, "weight": 1.0},
        },
        "iterations": 100,
    }
    result = simulator.run_custom_scenario("custom_test", interventions)
    assert result.scenario_name == "custom_test"
    assert result.iterations == 100
    assert isinstance(result.mean_outcome, float)


def test_load_scenario_new(simulator):
    result = simulator.load_scenario("test_new_scenario")
    assert result is not None
    assert result["name"] == "test_new_scenario"
    scenario_dir = Path(__file__).parent.parent.parent.parent / "data" / "predictive" / "scenarios"
    path = scenario_dir / "test_new_scenario.yaml"
    if path.exists():
        path.unlink()


def test_normal_outcome(simulator):
    val = simulator._normal_outcome(10.0, 2.0)
    assert isinstance(val, float)


def test_uniform_outcome(simulator):
    val = simulator._uniform_outcome(0.0, 1.0)
    assert 0.0 <= val <= 1.0


def test_triangular_outcome(simulator):
    val = simulator._triangular_outcome(2.0, 0.0, 5.0)
    assert 0.0 <= val <= 5.0


def test_simulation_result_dataclass():
    sr = SimulationResult(
        scenario_name="test",
        iterations=100,
        outcomes=[{"_outcome": 50.0}],
        mean_outcome=50.0,
        confidence_interval=(45.0, 55.0),
        risk_factors=[{"parameter": "x", "correlation": 0.5}],
        converged=True,
    )
    assert sr.scenario_name == "test"
    assert sr.iterations == 100
    assert sr.converged is True


def test_causal_graph_integration(simulator):
    with patch("core.memory.causal_graph.CausalGraph") as mock_cg:
        mock_instance = MagicMock()
        mock_cg.return_value = mock_instance
        from districts.predictive_analytics.causal_simulator import CausalSimulator
        cs = CausalSimulator()
        assert cs._causal_graph is not None
