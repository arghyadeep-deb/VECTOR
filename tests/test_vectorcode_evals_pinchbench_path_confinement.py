"""Path-confinement regressions for the PinchBench task environment."""

from pathlib import Path

import pytest

from vectorcode.src.evals.core.types import EvalRecord
from vectorcode.src.evals.execution.pinchbench_env import PinchBenchTaskEnv


def _record(tmp_path: Path, workspace_files: list[dict]) -> EvalRecord:
    return EvalRecord(
        record_id="pinch-path-test",
        problem="test",
        reference="",
        category="agentic",
        metadata={
            "workspace_files": workspace_files,
            "pinchbench_repo_dir": str(tmp_path / "repo"),
        },
    )


@pytest.mark.parametrize("unsafe_path", ["../escape.txt", "..\\escape.txt"])
def test_inline_fixture_cannot_escape_workspace(tmp_path, unsafe_path):
    record = _record(tmp_path, [{"path": unsafe_path, "content": "owned"}])

    with pytest.raises(ValueError, match="Unsafe PinchBench destination path"):
        PinchBenchTaskEnv(record).__enter__()

    assert not (tmp_path / "escape.txt").exists()


def test_absolute_fixture_path_cannot_override_workspace(tmp_path):
    target = tmp_path / "outside.txt"
    record = _record(tmp_path, [{"path": str(target), "content": "owned"}])

    with pytest.raises(ValueError, match="Unsafe PinchBench destination path"):
        PinchBenchTaskEnv(record).__enter__()

    assert not target.exists()


def test_asset_source_cannot_escape_assets_directory(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    record = _record(
        tmp_path,
        [{"source": "../../../secret.txt", "dest": "copied.txt"}],
    )

    with pytest.raises(ValueError, match="Unsafe PinchBench source path"):
        PinchBenchTaskEnv(record).__enter__()


if __name__ == "__main__":
    raise SystemExit("Run with pytest")
