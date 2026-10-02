"""Regression: core/experiments/ab_testing.py's Experiment.winner() compared
candidates' p_value fields from stats() -- but stats() only ever computes
p_value relative to self.variants[0] (the base variant), and never sets a
p_value for self.variants[0] itself. Whenever variants[0] also qualified as
a candidate (n >= min_n) -- the normal case for a control group with plenty
of samples -- winner() read d.get("p_value") for it as None and returned
None immediately, regardless of real significance. Fixed by computing the
best-vs-other p-value directly instead of reusing stats()'s baseline-fixed
field.

Dormant today (zero real callers anywhere, confirmed via repo-wide grep --
Gap 18 / A/B testing is unwired from any production caller, a separate
pre-existing finding), fixed anyway per this cycle's "fix narrow bugs even
in dormant code" bar.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.experiments.ab_testing import ExperimentRegistry


def _seeded_registry(tmp_path):
    reg = ExperimentRegistry(db_path=tmp_path / "exp.db")
    exp = reg.create("test_exp", variants=["control", "treatment"])
    # control (variants[0]) is clearly worse and has plenty of samples --
    # the exact shape that made the old code always return None. Slightly
    # varied values (not an identical constant) so std != 0 -- real
    # experiment data is never exactly constant, and std==0 on both sides
    # is its own legitimate "can't tell" edge case unrelated to this bug.
    for i in range(40):
        exp.record("s", "control", "reward", 0.08 + (i % 5) * 0.005)
    for i in range(40):
        exp.record("s", "treatment", "reward", 0.88 + (i % 5) * 0.005)
    return exp


def test_winner_detects_clear_significant_winner_when_base_variant_qualifies(tmp_path):
    exp = _seeded_registry(tmp_path)
    assert exp.winner(min_n=30) == "treatment"


def test_stats_still_reports_pvalue_relative_to_base_for_display():
    from core.experiments.ab_testing import ExperimentRegistry
    import tempfile as _tf
    with _tf.TemporaryDirectory() as d:
        reg = ExperimentRegistry(db_path=Path(d) / "exp2.db")
        exp = reg.create("display_exp", variants=["control", "treatment"])
        for i in range(40):
            exp.record("s", "control", "reward", 0.08 + (i % 5) * 0.005)
        for i in range(40):
            exp.record("s", "treatment", "reward", 0.88 + (i % 5) * 0.005)
        s = exp.stats()
        assert "p_value" not in s["control"] or s["control"].get("p_value") is None
        assert s["treatment"]["p_value"] < 0.05


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
