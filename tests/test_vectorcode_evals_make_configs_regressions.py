"""Regression tests for framework-comparison config generation."""

from vectorcode.src.evals.comparison.make_configs import FRAMEWORKS


def test_native_and_external_vector_frameworks_are_both_reachable():
    assert len(FRAMEWORKS) == 4
    assert FRAMEWORKS["vector-agent"]["backend_id"] == "vector-agent"
    assert FRAMEWORKS["vector"]["backend_id"] == "vector"


if __name__ == "__main__":
    raise SystemExit("Run with pytest")
