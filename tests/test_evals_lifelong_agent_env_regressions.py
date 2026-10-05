"""Regression tests for LifelongAgentBench environment isolation."""

from types import SimpleNamespace

from vectorcode.src.evals.core.types import EvalRecord
from vectorcode.src.evals.environments import lifelong_agent_env


def test_os_environment_uses_unique_sanitized_container_names(monkeypatch):
    commands = []

    monkeypatch.setattr(lifelong_agent_env.shutil, "which", lambda executable: "docker")

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(lifelong_agent_env.subprocess, "run", fake_run)
    record = EvalRecord(
        record_id="../../shared container",
        problem="task",
        reference="",
        category="agentic",
        metadata={"instruction": "task"},
    )

    first = lifelong_agent_env.OSEnvironment(image="ubuntu:22.04")
    second = lifelong_agent_env.OSEnvironment(image="ubuntu:22.04")
    first.reset(record)
    second.reset(record)

    assert first._container_name != second._container_name
    assert first._container_name.startswith("lifelong-os-..-..-shared-container-")
    assert " " not in first._container_name
    assert ["docker", "rm", "-f", first._container_name] in commands
    assert ["docker", "rm", "-f", second._container_name] in commands


if __name__ == "__main__":
    from pytest import MonkeyPatch

    patch = MonkeyPatch()
    try:
        test_os_environment_uses_unique_sanitized_container_names(patch)
    finally:
        patch.undo()
