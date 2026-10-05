"""Regression tests for TerminalBench container isolation and cleanup safety."""

import sys
from types import ModuleType, SimpleNamespace

from vectorcode.src.evals.execution.terminalbench_env import TerminalBenchTaskEnv
from vectorcode.src.evals.scorers import terminalbench_v2_1


class _TerminalContext:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def __enter__(self):
        return SimpleNamespace(
            create_session=lambda *args, **kwargs: SimpleNamespace()
        )

    def __exit__(self, *args) -> None:
        return None


def test_terminalbench_container_names_are_unique(monkeypatch) -> None:
    names: list[str] = []

    def spin_up_terminal(**kwargs):
        names.append(kwargs["client_container_name"])
        return _TerminalContext(names)

    package = ModuleType("terminal_bench")
    terminal_package = ModuleType("terminal_bench.terminal")
    terminal_module = ModuleType("terminal_bench.terminal.terminal")
    terminal_module.spin_up_terminal = spin_up_terminal
    monkeypatch.setitem(sys.modules, "terminal_bench", package)
    monkeypatch.setitem(sys.modules, "terminal_bench.terminal", terminal_package)
    monkeypatch.setitem(sys.modules, "terminal_bench.terminal.terminal", terminal_module)
    metadata = {
        "task": SimpleNamespace(disable_asciinema=True),
        "task_paths": SimpleNamespace(docker_compose_path="compose.yaml"),
        "task_id": "same-task",
    }
    with TerminalBenchTaskEnv(metadata):
        pass
    with TerminalBenchTaskEnv(metadata):
        pass

    assert names[0] != names[1]


def test_scorer_cleanup_failure_does_not_replace_score(monkeypatch, tmp_path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 6:
            raise OSError("docker cleanup failed")
        stdout = "1" if calls == 5 else ""
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(terminalbench_v2_1.subprocess, "run", fake_run)
    scorer = terminalbench_v2_1.TerminalBenchV21Scorer()
    record = SimpleNamespace(
        metadata={"docker_image": "image", "task_dir": str(tmp_path), "task_id": "x"}
    )

    passed, metadata = scorer.score(record, "echo solved")

    assert passed is True
    assert metadata["score"] == 1.0


if __name__ == "__main__":
    raise SystemExit("Run with pytest")
