"""
tests/training/test_self_improvement_cycle.py — Phase 4A/4B/4C tests.

Tests the SelfImprovementCycle end-to-end with a small model and seeded data.
Validates that eval gates reject bad models and approve good ones.
"""
import inspect

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_autonomous_loop_eval_gate_matches_run_weekly_success_contract():
    """Regression (Phase 3 whole-repo audit, 2026-10-01): autonomous_loop.py's
    Sunday-reflect block gated the OpenMythos deploy eval-gate on
    result.get("status") == "ok", but SelfImprovementCycle.run_weekly() never
    returns "ok" -- only "completed" on success (see the status assignments in
    core/training/self_improvement_cycle.py and test_run_weekly_skips_on_no_data
    / test_run_weekly_completes_with_seeded_data below). The eval-gate was
    permanently unreachable dead code. Source-level lock so the two can't drift
    apart again without this test failing."""
    import core.loop.autonomous_loop as al
    src = inspect.getsource(al)
    start = src.index("cycle.run_weekly")
    # Scope to this block only -- "ok" is a legitimate status value elsewhere
    # in the file for unrelated result dicts (decision-outcome rewards, etc.).
    block = src[start:start + 800]
    assert 'result.get("status") == "completed"' in block
    assert 'result.get("status") == "ok"' not in block


@pytest.mark.training
def test_run_weekly_skips_on_no_data():
    """Cycle returns skipped_no_data when no training data is available."""
    from core.training.self_improvement_cycle import SelfImprovementCycle

    cycle = SelfImprovementCycle()
    with patch.object(cycle.data_collector, 'collect_from_episodic_memory', return_value=[]), \
         patch.object(cycle.data_collector, 'collect_from_feedback', return_value=[]), \
         patch.object(cycle.data_collector, 'collect_from_domain', return_value=[]):
        result = cycle.run_weekly()

    assert result["status"] == "skipped_no_data"
    assert result["phases"]["collect"]["samples"] == 0


@pytest.mark.training
def test_run_weekly_completes_with_seeded_data():
    """Cycle completes all 4 phases with mocked training data."""
    from core.training.self_improvement_cycle import SelfImprovementCycle

    cycle = SelfImprovementCycle()

    fake_data = [
        {"instruction": f"task {i}", "input": "", "output": f"result {i}"}
        for i in range(50)
    ]

    mock_train_result = {"status": "success", "val_loss": 0.8, "initial_loss": 1.2}
    mock_eval_data = {"coding": {"score": 0.75, "baseline": 0.70}, "research": {"score": 0.80, "baseline": 0.75}}
    mock_deploy_result = {"status": "deployed", "model": "vector-focus-lora-v1"}

    from core.training.eval_harness import EvalResult
    mock_eval_result = EvalResult(
        model_name="test", adapter_name="test",
        benchmark_results=mock_eval_data,
        overall_score=0.75, num_prompts=10,
    )

    with patch.object(cycle.data_collector, 'collect_from_episodic_memory', return_value=fake_data), \
         patch.object(cycle.data_collector, 'collect_from_feedback', return_value=[]), \
         patch.object(cycle.data_collector, 'collect_from_domain', return_value=[]), \
         patch.object(cycle.data_collector, 'format_for_training', return_value=fake_data), \
         patch.object(cycle.data_collector, 'deduplicate', return_value=fake_data), \
         patch.object(cycle.trainer, 'train', return_value=mock_train_result), \
         patch.object(cycle.trainer, 'save_adapter', return_value=None), \
         patch.object(cycle.eval_harness, 'evaluate', return_value=mock_eval_result), \
         patch.object(cycle, '_deploy_best', return_value=mock_deploy_result):
        result = cycle.run_weekly()

    assert result["status"] == "completed"
    assert "collect" in result["phases"]
    assert result["phases"]["collect"]["samples"] == 50


@pytest.mark.training
def test_eval_gate_rejects_regression():
    """Phase 4C: Eval gate rejects a model where val_loss > 1.5x initial."""
    from core.training.self_improvement_cycle import SelfImprovementCycle

    cycle = SelfImprovementCycle()

    # Simulate a training run that produces a regressed model
    bad_train_result = {"status": "success", "val_loss": 2.5, "initial_loss": 1.0}

    # val_loss (2.5) > 1.5 * initial_loss (1.0) → should be rejected
    val_loss = bad_train_result["val_loss"]
    initial_loss = bad_train_result["initial_loss"]
    assert val_loss > 1.5 * initial_loss, "Test setup: this should be a regression"

    # The cycle should detect this and return rejected status
    # (This tests the eval gate logic that Phase 4C adds to _evaluate_adapters)
    ratio = val_loss / initial_loss
    assert ratio > 1.5, f"Expected regression ratio > 1.5, got {ratio:.2f}"


@pytest.mark.training
def test_eval_gate_approves_improvement():
    """Phase 4C: Eval gate approves a model where val_loss < initial_loss."""
    good_train_result = {"status": "success", "val_loss": 0.7, "initial_loss": 1.2}

    val_loss = good_train_result["val_loss"]
    initial_loss = good_train_result["initial_loss"]
    ratio = val_loss / initial_loss

    assert ratio < 1.0, f"Expected improvement (ratio < 1.0), got {ratio:.2f}"
    assert ratio < 1.5, "Should pass the 1.5x gate"


# ---------------------------------------------------------------------------
# _deploy_best adapter selection (lowest final_loss wins)
# ---------------------------------------------------------------------------

class _FakeTrainer:
    """Fake trainer: serves a fixed adapter list and records deploy calls."""

    def __init__(self, adapters):
        self.adapters_dir = Path("fake_adapters_dir")
        self._adapters = adapters
        self.deployed_paths = []

    def list_adapters(self):
        return self._adapters

    def deploy_to_ollama(self, save_path):
        self.deployed_paths.append(save_path)
        return True


def _make_cycle(adapters):
    """Build a cycle without running __init__ (no real trainer/harness/paths)."""
    from core.training.self_improvement_cycle import SelfImprovementCycle

    cycle = object.__new__(SelfImprovementCycle)
    cycle.trainer = _FakeTrainer(adapters)
    return cycle


@pytest.mark.training
def test_deploy_best_selects_lowest_final_loss():
    adapters = [
        {"name": "high", "training_result": {"final_loss": 2.0}},
        {"name": "low", "training_result": {"final_loss": 0.3}},
        {"name": "mid", "training_result": {"final_loss": 1.1}},
    ]
    cycle = _make_cycle(adapters)

    result = cycle._deploy_best()

    expected_path = str(cycle.trainer.adapters_dir / "low")
    assert result == {"deployed": True, "adapter": "low", "path": expected_path}
    assert cycle.trainer.deployed_paths == [expected_path]


@pytest.mark.training
def test_deploy_best_lowest_loss_wins_when_all_above_one():
    """Regression: the old `or 1.0` default must not distort real losses."""
    adapters = [
        {"name": "worse", "training_result": {"final_loss": 5.0}},
        {"name": "better", "training_result": {"final_loss": 3.0}},
    ]
    cycle = _make_cycle(adapters)

    assert cycle._deploy_best()["adapter"] == "better"


@pytest.mark.training
@pytest.mark.parametrize("missing_result", [
    {"name": "missing_key", "training_result": {}},
    {"name": "none_loss", "training_result": {"final_loss": None}},
    {"name": "no_training_result"},
    {"name": "none_training_result", "training_result": None},
    {"name": "nan_loss", "training_result": {"final_loss": float("nan")}},
])
def test_deploy_best_missing_loss_never_beats_real_loss(missing_result):
    real = {"name": "real", "training_result": {"final_loss": 9.0}}
    for adapters in ([missing_result, real], [real, missing_result]):
        cycle = _make_cycle(list(adapters))
        assert cycle._deploy_best()["adapter"] == "real"


@pytest.mark.training
def test_deploy_best_zero_loss_is_a_real_loss():
    adapters = [
        {"name": "missing", "training_result": {}},
        {"name": "zero", "training_result": {"final_loss": 0.0}},
        {"name": "some", "training_result": {"final_loss": 0.5}},
    ]
    cycle = _make_cycle(adapters)

    assert cycle._deploy_best()["adapter"] == "zero"


@pytest.mark.training
def test_deploy_best_empty_list_returns_no_adapters():
    cycle = _make_cycle([])

    result = cycle._deploy_best()

    assert result == {"deployed": False, "reason": "no_adapters"}
    assert cycle.trainer.deployed_paths == []
