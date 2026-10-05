"""Regression for vectorcode/src/learning/optimize/optimizer.py's
OptimizationEngine._write_toml_fallback() (used by export_best_recipe()
when tomli_w is not installed):

the fallback manually interpolated string values into TOML basic
strings (f'{key} = "{val}"') with zero escaping. Params like
agent.system_prompt / intelligence.system_prompt can be DSPy/GEPA-
generated optimizer output containing a double-quote, backslash, or
control character -- any of which previously produced a syntactically
invalid TOML recipe file. Same bug class already fixed in
skills/overlay.py's write_overlay() this audit cycle.
"""
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from learning.optimize.optimizer import OptimizationEngine
from learning.optimize.types import OptimizationRun, SearchSpace, TrialConfig, TrialResult


def _run_with_system_prompt(value: str) -> OptimizationRun:
    config = TrialConfig(
        trial_id="t1",
        params={"agent.system_prompt": value},
    )
    trial = TrialResult(trial_id="t1", config=config, accuracy=0.9)
    return OptimizationRun(
        run_id="r1",
        search_space=SearchSpace(),
        trials=[trial],
        best_trial=trial,
    )


def test_fallback_escapes_quotes_and_control_chars(tmp_path):
    engine = OptimizationEngine.__new__(OptimizationEngine)
    dangerous = 'He said "hi"\nthen a vtab:\x0b and a backslash: \\'
    run = _run_with_system_prompt(dangerous)
    recipe_data = engine._trial_to_recipe_dict(run.best_trial)

    out_path = tmp_path / "recipe.toml"
    engine._write_toml_fallback(recipe_data, out_path)

    # Must round-trip through a real TOML parser without raising.
    parsed = tomllib.loads(out_path.read_text(encoding="utf-8"))
    assert parsed["agent"]["system_prompt"] == dangerous


def test_fallback_handles_plain_string_normally(tmp_path):
    engine = OptimizationEngine.__new__(OptimizationEngine)
    run = _run_with_system_prompt("You are a helpful agent.")
    recipe_data = engine._trial_to_recipe_dict(run.best_trial)

    out_path = tmp_path / "recipe.toml"
    engine._write_toml_fallback(recipe_data, out_path)

    parsed = tomllib.loads(out_path.read_text(encoding="utf-8"))
    assert parsed["agent"]["system_prompt"] == "You are a helpful agent."


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
