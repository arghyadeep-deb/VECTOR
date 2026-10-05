"""Regressions for three real bugs found in vectorcode/src/learning/ (round 2):

1. distillation/gate/regression.py's regression_check() defaulted a
   cluster missing from the "after" snapshot to score 0.0 -- but a
   missing cluster means it wasn't sampled this run (subsample_size can
   skip clusters), not that it scored zero. This manufactured a false
   catastrophic "regression" and spuriously rejected genuinely improving
   edits whenever subsampling happened to skip a cluster.

2. distillation/plan/prompt_diff.py's maybe_downgrade_to_replace()
   fell back to using the raw unified-diff text itself as the new
   system prompt content when the diff couldn't be applied -- showing a
   human reviewer diff markup (@@ -1,5 +1,8 @@, -old, +new, ...) as if
   it were the actual proposed prompt, instead of an honest failure
   message.

3. Three LearningRegistry wrapper classes' __init__ (dspy_optimizer.py's
   _DSPyLearningPolicy, gepa_optimizer.py's _GEPALearningPolicy,
   intelligence/grpo_trainer.py's _GRPOLearningPolicy) unconditionally
   raised NotImplementedError -- a regression from an earlier blanket
   "pass-only stub -> raise NotImplementedError" commit that incorrectly
   touched these concrete, intentionally-stateless wrapper classes,
   making each registry entry permanently unconstructable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.learning.distillation.gate.regression import regression_check
from vectorcode.src.learning.distillation.models import BenchmarkSnapshot


def _snapshot(scores: dict) -> BenchmarkSnapshot:
    overall = sum(scores.values()) / len(scores) if scores else 0.0
    return BenchmarkSnapshot(
        benchmark_version="v1",
        overall_score=overall,
        cluster_scores=scores,
        task_count=len(scores),
        elapsed_seconds=0.0,
    )


def test_missing_cluster_in_after_is_not_treated_as_zero_score():
    before = _snapshot({"math": 0.9, "coding": 0.8})
    # "coding" wasn't sampled this run -- absent, not scored 0.0.
    after = _snapshot({"math": 0.95})

    result = regression_check(before, after, max_regression=0.05)

    assert result.has_regression is False
    assert result.regressed_clusters == {}


def test_real_regression_in_a_sampled_cluster_is_still_caught():
    before = _snapshot({"math": 0.9, "coding": 0.8})
    after = _snapshot({"math": 0.95, "coding": 0.5})

    result = regression_check(before, after, max_regression=0.05)

    assert result.has_regression is True
    assert "coding" in result.regressed_clusters
    assert "math" not in result.regressed_clusters


def test_diff_apply_failure_does_not_leak_raw_diff_as_prompt_content():
    from vectorcode.src.learning.distillation.plan.prompt_diff import (
        maybe_downgrade_to_replace,
    )
    from vectorcode.src.learning.distillation.models import Edit, EditOp, EditRiskTier

    bad_diff = "not a valid unified diff at all"
    edit = Edit(
        id="edit_001",
        pillar="agent",
        op=EditOp.PATCH_SYSTEM_PROMPT,
        target="agents.simple.system_prompt",
        payload={"diff": bad_diff},
        rationale="test",
        expected_improvement="cluster_1",
        risk_tier=EditRiskTier.REVIEW,
        references=[],
    )

    result = maybe_downgrade_to_replace(edit, prompt_reader=lambda _t: "original prompt")

    assert result.op == EditOp.REPLACE_SYSTEM_PROMPT
    new_content = result.payload["new_content"]
    assert bad_diff not in new_content
    assert "FAILED" in new_content.upper()


def test_dspy_learning_policy_is_constructable():
    from vectorcode.src.learning.agents.dspy_optimizer import _DSPyLearningPolicy

    policy = _DSPyLearningPolicy()
    assert policy is not None


def test_gepa_learning_policy_is_constructable():
    from vectorcode.src.learning.agents.gepa_optimizer import _GEPALearningPolicy

    policy = _GEPALearningPolicy()
    assert policy is not None


def test_grpo_learning_policy_is_constructable():
    from vectorcode.src.learning.intelligence.grpo_trainer import _GRPOLearningPolicy

    policy = _GRPOLearningPolicy()
    assert policy is not None


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
