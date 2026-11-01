"""Deterministic command and test runner for the VECTOR dev orchestrator."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


_TARGET_PATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
# One node segment: a name, optionally followed by ONE [parameter] group (the only
# place ':' may appear). Empty segments ("a.py::", "a.py:::x") never match.
_TARGET_NODE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-.,=+/]*(?:\[[A-Za-z0-9_\-.,:=+/]*\])?$")


def invalid_test_target_reason(target: object) -> str | None:
    """Why `target` cannot be ONE plain pytest path / node id, or None if it can.

    A target is a single argv element naming a file, directory or
    `file.py::node`. Anything carrying pytest CLI arguments (`-k expr`,
    `--maxfail`, several paths in one string) is rejected: those would
    otherwise reach pytest as one bogus path (exit 4) or, worse, be
    ambiguous between a path and an option. Fails closed.
    """

    if not isinstance(target, str) or not target.strip():
        return "empty target"

    if target != target.strip() or any(ch.isspace() for ch in target):
        return (
            "contains whitespace; embedded pytest arguments such as '-k ...' "
            "or several paths in one string are not a single path/node id"
        )

    norm = target.replace("\\", "/")

    if norm.startswith("-"):
        return "starts with '-' (a pytest option, not a path)"

    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        return "absolute path"

    path_part, _, node_part = norm.partition("::")

    if ".." in path_part.split("/"):
        return "parent traversal"

    if not _TARGET_PATH_RE.match(path_part):
        return "characters outside a plain repository-relative path"

    if "::" in norm and not all(_TARGET_NODE_RE.match(seg) for seg in node_part.split("::")):
        return "malformed pytest node id (empty segment or characters outside a plain node id)"

    return None


def invalid_test_targets(targets: list[str]) -> list[str]:
    """Human-readable reasons for every malformed target (empty if all are fine)."""

    return [
        f"{target!r}: {reason}"
        for target in targets
        if (reason := invalid_test_target_reason(target)) is not None
    ]


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

        problems = invalid_test_targets(test_targets)

        if problems:
            raise ValueError("Invalid pytest target(s): " + "; ".join(problems))

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

    # A pytest target is ONE path / node id; embedded CLI arguments are refused.
    for good in (
        "tests/test_a.py",
        "tests/",
        "tests/sub/test_b.py::test_x",
        "tests/test_c.py::TestK::test_y[param-1]",
        "tests/test_c.py::TestK::test_y[a:b]",
        "test_d.py",
    ):
        assert invalid_test_target_reason(good) is None, good

    for bad in (
        "tests/ -k uploader",
        "tests/test_a.py -k 'executed or failed'",
        "-k uploader",
        "--maxfail=1",
        "tests/a.py tests/b.py",
        "tests/a.py;rm -rf x",
        "tests/a.py|cat",
        "$(whoami)",
        "/etc/passwd",
        "C:\\Windows\\x.py",
        "../outside.py",
        "tests/../../x.py",
        " tests/a.py",
        "",
        "tests/a.py::t -x",
        "tests/a.py::",
        "tests/a.py:::x",
        "tests/a.py::::x",
        "tests/a.py::t[",
        "tests/a.py::t]x",
        "tests/a.py::t[a][b]",
        "tests/a.py::[x]",
        "::x",
    ):
        assert invalid_test_target_reason(bad) is not None, bad

    assert invalid_test_target_reason(None) is not None
    assert invalid_test_target_reason("tests\\test_a.py") is None, "backslash paths normalise"
    assert len(invalid_test_targets(["tests/a.py", "tests/ -k x", "-x"])) == 2

    try:
        runner.run_pytest(["tests/ -k uploader"])
    except ValueError as exc:
        assert "Invalid pytest target" in str(exc)
    else:
        raise AssertionError("run_pytest must refuse an embedded-argument target before running anything")


if __name__ == "__main__":
    _self_test()
