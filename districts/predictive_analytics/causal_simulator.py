from pathlib import Path
import re

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from datetime import datetime, timezone

from loguru import logger


@dataclass
class SimulationResult:
    scenario_name: str
    iterations: int
    outcomes: list[dict] = field(default_factory=list)
    mean_outcome: float = 0.0
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    risk_factors: list[dict] = field(default_factory=list)
    converged: bool = False


class CausalSimulator:
    def __init__(self):
        self._rng = np.random.default_rng()
        self._causal_graph = None
        try:
            from core.memory.causal_graph import CausalGraph
            self._causal_graph = CausalGraph()
            logger.info("[VECTOR][predictive_analytics] CausalGraph loaded")
        except Exception as e:
            logger.debug(f"[VECTOR][predictive_analytics] CausalGraph unavailable: {e}")

    def run_monte_carlo(
        self,
        metric_name: str,
        scenario_params: dict,
        iterations: int = 1000,
    ) -> SimulationResult:
        try:
            outcomes = []
            base = scenario_params.get("base_value", 50.0)
            param_names = list(scenario_params.get("parameters", {}).keys())
            trailing_var = []
            converged = False

            for iteration in range(iterations):
                outcome = base
                factors = {}
                for param_name, param_config in scenario_params.get("parameters", {}).items():
                    dist_type = param_config.get("distribution", "normal")
                    if dist_type == "normal":
                        value = self._normal_outcome(
                            param_config.get("mean", 0.0),
                            param_config.get("std", 1.0),
                        )
                    elif dist_type == "uniform":
                        value = self._uniform_outcome(
                            param_config.get("low", -1.0),
                            param_config.get("high", 1.0),
                        )
                    elif dist_type == "triangular":
                        value = self._triangular_outcome(
                            param_config.get("mode", 0.0),
                            param_config.get("low", -1.0),
                            param_config.get("high", 1.0),
                        )
                    else:
                        # A typo'd distribution used to contribute 0.0 and report a confident result.
                        raise ValueError(f"unknown distribution '{dist_type}' for parameter '{param_name}'")
                    weight = param_config.get("weight", 1.0)
                    outcome += value * weight
                    factors[param_name] = value
                factors["_outcome"] = outcome
                outcomes.append(factors)

                if iteration >= 100 and iteration % 50 == 0:
                    recent = [o["_outcome"] for o in outcomes[-50:]]
                    trailing_var.append(float(np.var(recent)))
                    if len(trailing_var) >= 5:
                        recent_vars = trailing_var[-5:]
                        if max(recent_vars) - min(recent_vars) < 0.01 * abs(np.mean(recent_vars) + 1e-10):
                            converged = True
                            break

            raw_outcomes = [o["_outcome"] for o in outcomes]
            mean_outcome = float(np.mean(raw_outcomes))
            ci_lower = float(np.percentile(raw_outcomes, 2.5))
            ci_upper = float(np.percentile(raw_outcomes, 97.5))

            logger.info(
                f"[VECTOR][predictive_analytics] MC simulation '{metric_name}' "
                f"over {len(outcomes)} iterations: mean={mean_outcome:.2f}, "
                f"CI=[{ci_lower:.2f}, {ci_upper:.2f}] converged={converged}"
            )

            if self._causal_graph is not None:
                try:
                    self._causal_graph.add_node(
                        f"sim_{metric_name}_{datetime.now(timezone.utc).isoformat()}",
                        "simulation",
                        f"MC simulation of {metric_name}",
                        {"mean": mean_outcome, "ci_lower": ci_lower, "ci_upper": ci_upper},
                    )
                except Exception:
                    logger.debug("[VECTOR] suppressed exception", exc_info=True)

            return SimulationResult(
                scenario_name=metric_name,
                iterations=len(outcomes),
                outcomes=outcomes,
                mean_outcome=mean_outcome,
                confidence_interval=(ci_lower, ci_upper),
                risk_factors=self._compute_risk_factors(outcomes, scenario_params),
                converged=converged,
            )
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Monte Carlo simulation failed: {e}")
            return SimulationResult(
                scenario_name=metric_name,
                iterations=0,
                outcomes=[],
                mean_outcome=0.0,
                confidence_interval=(0.0, 0.0),
                risk_factors=[],
            )

    def _normal_outcome(self, mean: float, std: float) -> float:
        return float(self._rng.normal(mean, std))

    def _uniform_outcome(self, low: float, high: float) -> float:
        return float(self._rng.uniform(low, high))

    def _triangular_outcome(self, mode: float, low: float, high: float) -> float:
        c = (mode - low) / (high - low) if (high - low) > 0 else 0.5
        return float(self._rng.triangular(low, mode, high))

    def evaluate_risk(self, results: SimulationResult, threshold: float) -> float:
        try:
            if not results.outcomes:
                return 0.0
            raw = [o["_outcome"] for o in results.outcomes]
            exceed = sum(1 for v in raw if v >= threshold)
            probability = exceed / len(raw)
            return probability
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Risk evaluation failed: {e}")
            return 0.0

    def _compute_risk_factors(
        self,
        outcomes: list[dict],
        scenario_params: dict,
    ) -> list[dict]:
        risk_factors: list[dict] = []
        try:
            param_names = [k for k in scenario_params.get("parameters", {}).keys()]
            if not param_names or len(outcomes) < 2:
                return risk_factors
            outcome_arr = np.array([o["_outcome"] for o in outcomes])
            for param_name in param_names:
                param_vals = np.array([o.get(param_name, 0.0) for o in outcomes])
                if np.std(param_vals) > 0:
                    corr_matrix = np.corrcoef(param_vals, outcome_arr)
                    correlation = float(corr_matrix[0, 1])
                    risk_factors.append({
                        "parameter": param_name,
                        "correlation": round(correlation, 4),
                        "impact": "high" if abs(correlation) > 0.5 else "medium" if abs(correlation) > 0.3 else "low",
                        "direction": "positive" if correlation > 0 else "negative",
                    })
                    risk_factors.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Risk factor computation failed: {e}")
        return risk_factors

    def suggest_scenarios(self) -> list[dict]:
        default_scenarios = [
            {
                "name": "high_load",
                "description": "System under high load — CPU/memory stress test",
                "base_value": 50.0,
                "parameters": {
                    "cpu_load": {"distribution": "normal", "mean": 15.0, "std": 5.0, "weight": 1.0},
                    "memory_pressure": {"distribution": "normal", "mean": 10.0, "std": 3.0, "weight": 0.8},
                    "concurrent_tasks": {"distribution": "uniform", "low": 1.0, "high": 10.0, "weight": 0.5},
                },
            },
            {
                "name": "budget_scenario",
                "description": "Monthly budget projection with expense variability",
                "base_value": 500.0,
                "parameters": {
                    "fixed_costs": {"distribution": "normal", "mean": -200.0, "std": 10.0, "weight": 1.0},
                    "variable_costs": {"distribution": "triangular", "mode": -100.0, "low": -200.0, "high": -50.0, "weight": 0.8},
                    "income": {"distribution": "normal", "mean": 1000.0, "std": 100.0, "weight": 1.0},
                },
            },
            {
                "name": "productivity_forecast",
                "description": "Task completion rate projection",
                "base_value": 75.0,
                "parameters": {
                    "task_volume": {"distribution": "normal", "mean": 5.0, "std": 2.0, "weight": 1.0},
                    "interruptions": {"distribution": "uniform", "low": -10.0, "high": 0.0, "weight": 0.6},
                    "focus_time": {"distribution": "normal", "mean": 3.0, "std": 1.0, "weight": 0.8},
                },
            },
        ]

        if self._causal_graph is not None:
            try:
                if hasattr(self._causal_graph, "_nodes") and self._causal_graph._nodes:
                    outcomes = list(self._causal_graph._nodes.values())
                    recent = [n for n in outcomes if n.get("type") in ("outcome", "simulation")]
                    if recent:
                        default_scenarios.append({
                            "name": "causal_inference",
                            "description": f"Based on {len(recent)} recent causal outcomes",
                            "base_value": 50.0,
                            "parameters": {
                                "causal_strength": {"distribution": "normal", "mean": 0.5, "std": 0.2, "weight": 1.0},
                                "outcome_impact": {"distribution": "normal", "mean": 5.0, "std": 2.0, "weight": 0.8},
                            },
                        })
            except Exception:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)

        return default_scenarios

    def run_custom_scenario(self, name: str, interventions: dict) -> SimulationResult:
        base = interventions.get("base_value", 50.0)
        raw_params = interventions.get("parameters", {})
        params = {
            "base_value": base,
            "parameters": raw_params,
        }
        iterations = interventions.get("iterations", 1000)
        result = self.run_monte_carlo(name, params, iterations=iterations)
        return result

    def load_scenario(self, name: str) -> Optional[dict]:
        # name becomes a filename: reject separators/traversal (CWE-22) for both the read and the template write.
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", name):
            logger.warning("[VECTOR][predictive_analytics] Rejected unsafe scenario name: {!r}", name)
            return None
        scenario_paths = [
            Path(__file__).parent.parent.parent / "data" / "predictive" / "scenarios" / f"{name}.yaml",
            Path(__file__).parent.parent.parent / "data" / "predictive" / "scenarios" / f"{name}.yml",
        ]
        for sp in scenario_paths:
            if sp.exists():
                try:
                    import yaml
                    with open(sp, "r", encoding="utf-8") as f:
                        params = yaml.safe_load(f)
                    logger.info(f"[VECTOR][predictive_analytics] Loaded scenario '{name}' from {sp}")
                    return params
                except ImportError:
                    logger.warning("[VECTOR][predictive_analytics] PyYAML not installed")
                    return None
                except Exception as e:
                    logger.warning(f"[VECTOR][predictive_analytics] Failed to load '{name}': {e}")
                    return None
        scenario_dir = Path(__file__).parent.parent.parent / "data" / "predictive" / "scenarios"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        template = {
            "name": name,
            "description": f"Auto-created scenario: {name}",
            "base_value": 50.0,
            "parameters": {
                "param1": {"distribution": "normal", "mean": 0.0, "std": 1.0, "weight": 1.0},
            },
        }
        try:
            import yaml
            yaml_path = scenario_dir / f"{name}.yaml"
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(template, f, default_flow_style=False)
            logger.info(f"[VECTOR][predictive_analytics] Created scenario template at {yaml_path}")
        except ImportError:
            logger.warning("[VECTOR][predictive_analytics] PyYAML not installed, cannot write template")
        except Exception as e:
            logger.warning(f"[VECTOR][predictive_analytics] Failed to write template: {e}")
        return template


if __name__ == "__main__":
    cs = CausalSimulator()
    params = {
        "base_value": 100.0,
        "parameters": {
            "demand": {"distribution": "normal", "mean": 5.0, "std": 2.0, "weight": 1.0},
            "cost": {"distribution": "uniform", "low": -3.0, "high": 1.0, "weight": 0.5},
            "efficiency": {"distribution": "triangular", "mode": 2.0, "low": -1.0, "high": 5.0, "weight": 0.8},
        },
    }

    result = cs.run_monte_carlo("system_load_test", params, iterations=500)
    assert result.iterations <= 500
    assert len(result.outcomes) > 0
    assert isinstance(result.mean_outcome, float)
    assert len(result.confidence_interval) == 2

    risk = cs.evaluate_risk(result, threshold=120.0)
    assert 0.0 <= risk <= 1.0

    suggestions = cs.suggest_scenarios()
    assert len(suggestions) >= 3

    custom = cs.run_custom_scenario("custom_test", {
        "base_value": 100.0,
        "parameters": {"x": {"distribution": "normal", "mean": 0.0, "std": 1.0, "weight": 1.0}},
        "iterations": 50,
    })
    assert custom.iterations > 0

    loaded = cs.load_scenario("nonexistent_test_scenario")
    assert loaded is not None

    n = cs._normal_outcome(10.0, 2.0)
    assert isinstance(n, float)

    print("[OK] causal_simulator.py")
