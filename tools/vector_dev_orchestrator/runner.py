"""Deterministic command and test runner for the VECTOR dev orchestrator."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class CommandRunner:
    """Run approved deterministic commands inside the VECTOR repository."""

    def __init__(
        self,
        repo_root: Path,
        timeout_seconds: int = 1800,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        command: list[str],
        *,
        timeout_seconds: int | None = None,
    ) -> CommandResult:
        if not command:
            raise ValueError("Command must not be empty")

        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self.timeout_seconds
        )

        try:
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=command,
                exit_code=None,
                stdout=self._decode_timeout_stream(exc.stdout),
                stderr=self._decode_timeout_stream(exc.stderr),
                timed_out=True,
            )

        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def run_pytest(
        self,
        test_targets: list[str],
        *,
        quiet: bool = True,
    ) -> CommandResult:
        if not test_targets:
            raise ValueError("At least one pytest target is required")

        command = [
            sys.executable,
            "-m",
            "pytest",
        ]

        if quiet:
            command.append("-q")

        command.extend(test_targets)

        return self.run(command)

    def run_ci_gate(self) -> CommandResult:
        return self.run(
            [
                sys.executable,
                "tools/ci_gate.py",
            ],
            timeout_seconds=3600,
        )

    @staticmethod
    def _decode_timeout_stream(
        value: str | bytes | None,
    ) -> str:
        if value is None:
            return ""

        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")

        return value


def _self_test() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    runner = CommandRunner(repo_root)

    result = runner.run(
        [
            sys.executable,
            "-c",
            "print('VECTOR_RUNNER_OK')",
        ]
    )

    assert result.passed
    assert result.exit_code == 0
    assert "VECTOR_RUNNER_OK" in result.stdout

    failed = runner.run(
        [
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ]
    )

    assert not failed.passed
    assert failed.exit_code == 7


if __name__ == "__main__":
    _self_test()
