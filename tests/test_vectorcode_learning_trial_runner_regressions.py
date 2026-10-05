"""Regressions for vectorcode/src/learning/optimize/trial_runner.py:

1. _run_terminalbench_native() passed agent_import_path=
   "vector.evals.backends.tb_agent:VectorCodeTerminalBenchAgent" to
   terminal-bench's Harness -- there is no top-level "vector" package
   anywhere in this repo (confirmed: `import vector` raises
   ModuleNotFoundError). The real module lives at
   vectorcode/src/evals/backends/tb_agent.py. Every call to this method
   would fail to dynamically import the agent class and silently report
   a 0.0-accuracy, 1-error BenchmarkScore instead of a real result.

2. TrialRunner.run_trial()'s cleanup `finally` block called
   backend.close() then judge_backend.close() unguarded -- if
   backend.close() raised (its real implementation just forwards to
   self._system.close(), which can fail), judge_backend.close() would
   never run, leaking its resources. Each close() is now wrapped so one
   failing does not skip the other.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import learning.optimize.trial_runner as trial_runner_module
from learning.optimize.trial_runner import TrialRunner


def test_terminalbench_agent_import_path_has_no_bare_vector_package():
    src = inspect.getsource(trial_runner_module)
    assert '"vector.evals.backends.tb_agent' not in src
    assert '"vectorcode.src.evals.backends.tb_agent:VectorCodeTerminalBenchAgent"' in src


def test_terminalbench_agent_import_path_resolves_to_a_real_module():
    # terminal_bench itself is an optional heavy dependency not installed
    # in this environment; confirm the *file* the corrected dotted path
    # resolves to actually exists and defines the class, via AST rather
    # than a real import (which would need the optional package).
    import ast

    module_path = Path(__file__).parent.parent / "vectorcode" / "src" / "evals" / "backends" / "tb_agent.py"
    assert module_path.is_file()
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    class_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert "VectorCodeTerminalBenchAgent" in class_names


def test_run_trial_closes_judge_backend_even_if_backend_close_raises():
    trial = MagicMock()
    trial.trial_id = "t1"
    trial.to_recipe.return_value = MagicMock(
        model="m", agent_type=None, max_tokens=None, temperature=None,
        engine_key="cloud", tools=[], system_prompt="",
    )

    backend = MagicMock()
    backend.close.side_effect = RuntimeError("boom")
    judge_backend = MagicMock()

    runner = TrialRunner(benchmark="fake-bench")

    with patch("vectorcode.src.evals.cli._build_backend", return_value=backend), \
         patch("vectorcode.src.evals.cli._build_judge_backend", return_value=judge_backend), \
         patch("vectorcode.src.evals.cli._build_dataset", return_value=MagicMock()), \
         patch("vectorcode.src.evals.cli._build_scorer", return_value=MagicMock()), \
         patch("vectorcode.src.evals.core.runner.EvalRunner") as mock_runner_cls:
        mock_runner = MagicMock()
        mock_runner.run.return_value = MagicMock(
            accuracy=1.0, mean_latency_seconds=0.0, total_cost_usd=0.0,
            total_energy_joules=0.0, total_input_tokens=0, total_output_tokens=0,
            errors=0, total_samples=0,
        )
        mock_runner.results = []
        mock_runner_cls.return_value = mock_runner

        runner.run_trial(trial)

    judge_backend.close.assert_called_once()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
