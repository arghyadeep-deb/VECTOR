"""Regression tests for LifelongAgentBench fallback scoring."""

from types import SimpleNamespace

from loguru import logger as loguru_logger

from vectorcode.src.evals.scorers import lifelong_agent_scorer as scorer_module


def test_scorer_uses_loguru_logger() -> None:
    assert scorer_module.logger is loguru_logger


def test_os_evaluations_use_distinct_container_names(monkeypatch) -> None:
    container_names: list[str] = []

    def fake_run(command, **kwargs):
        if command[:3] == ["docker", "run", "-d"]:
            container_names.append(command[command.index("--name") + 1])
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(scorer_module.subprocess, "run", fake_run)

    for _ in range(2):
        assert scorer_module._evaluate_os_in_docker(
            {},
            ["true"],
            {"command": "true"},
            {},
        )

    assert len(container_names) == 2
    assert container_names[0] != container_names[1]
    assert all(name.startswith("lifelong-agent-os-eval-") for name in container_names)


if __name__ == "__main__":
    test_scorer_uses_loguru_logger()
