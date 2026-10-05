"""Regression coverage for TauBench environment-result scoring."""

from vectorcode.src.evals.core.types import EvalRecord
from vectorcode.src.evals.scorers.taubench import TauBenchScorer


def _record(metadata):
    return EvalRecord(
        record_id="tau-test",
        problem="test",
        reference="",
        category="agentic",
        metadata=metadata,
    )


def test_missing_tau_reward_is_indeterminate_not_failure():
    is_correct, metadata = TauBenchScorer().score(_record({}), "answer")

    assert is_correct is None
    assert metadata["reason"] == "no_environment_results"


def test_zero_tau_reward_remains_a_real_failure():
    is_correct, metadata = TauBenchScorer().score(
        _record({"tau_reward": 0.0}), "answer"
    )

    assert is_correct is False
    assert metadata["score"] == 0.0


if __name__ == "__main__":
    raise SystemExit("Run with pytest")
