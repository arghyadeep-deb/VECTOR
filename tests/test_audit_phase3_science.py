"""Audit phase 3 regressions for districts/science (no network)."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.science.science_agent import ScienceAgent


def run(task):
    return asyncio.run(ScienceAgent().run(task))


def test_params_none_does_not_crash():
    r = run({"type": "science", "params": None})
    assert r["status"] == "ok"


@pytest.mark.parametrize("params", [
    {"simulation": "projectile", "velocity": float("nan")},
    {"simulation": "projectile", "velocity": -5},
    {"simulation": "projectile", "angle_deg": 120},
    {"simulation": "projectile", "mass_kg": 0},
    {"simulation": "pendulum", "length_m": 0},
    {"simulation": "pendulum", "length_m": -1},
    {"simulation": "pendulum", "length_m": float("inf")},
    {"simulation": "warp"},
])
def test_physics_bad_input_is_error(params):
    assert run({"type": "physics", "params": params})["status"] == "error"


@pytest.mark.parametrize("params", [
    {"shape": "box", "length": -2, "width": 3, "height": 4},
    {"shape": "cylinder", "radius": 0},
    {"shape": "sphere", "radius": float("nan")},
    {"shape": "torus"},
])
def test_cad_bad_input_is_error(params):
    assert run({"type": "cad", "params": params})["status"] == "error"


def test_cad_valid_still_ok():
    r = run({"type": "cad", "params": {"shape": "box", "length": 3, "width": 4, "height": 5}})
    assert r["status"] == "ok" and abs(r["result"]["volume"] - 60) < 1e-6


class _Chem:
    def analyze_molecule(self, s):
        return {"smiles": s, "valid": False, "error": "Invalid SMILES"}


def test_chemistry_invalid_smiles_is_error():
    a = ScienceAgent()
    a._chemistry = _Chem()
    r = asyncio.run(a.run({"type": "chemistry", "params": {"smiles": "not-a-molecule"}}))
    assert r["status"] == "error"


class _Causal:
    def explain(self, n):
        return {"node_id": n, "causes": [], "error": "causal_graph unavailable"}

    def what_if(self, a, h):
        return {"error": "counterfactual unavailable"}

    def estimate_effect(self, t, o):
        return {"ate": None, "method": "unavailable"}

    def _get_causal_graph(self):
        return None


def _agent_causal():
    a = ScienceAgent()
    a._causal = _Causal()
    return a


@pytest.mark.parametrize("params", [
    {"mode": "explain", "node": "x"},
    {"mode": "explain"},
    {"mode": "what_if", "action": "a", "hypothetical": "b"},
    {"mode": "estimate_effect", "treatment": "a", "outcome": "b"},
    {"mode": "estimate_effect"},
    {"mode": "bogus"},
])
def test_causal_failure_not_reported_ok(params):
    r = asyncio.run(_agent_causal().run({"type": "causal_query", "params": params}))
    assert r["status"] == "error"


def test_experiment_propagates_physics_failure():
    r = run({"type": "experiment", "params": {"name": "e", "simulation": "projectile", "velocity": -1}})
    assert r["status"] == "error"
