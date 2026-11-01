"""Safe Codex CLI adapter for the VECTOR development orchestrator."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CodexResult:
    """Result of one Codex CLI invocation."""

    command: list[str]
    exit_code: int | None
    final_message: str
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class CodexAdapter:
    """Invoke Codex with explicit model, workspace and sandbox controls."""

    ALLOWED_SANDBOXES = {
        "read-only",
        "workspace-write",
    }

    def __init__(
        self,
        repo_root: Path,
        timeout_seconds: int = 1800,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.timeout_seconds = timeout_seconds

        executable = shutil.which("codex")
        if executable is None:
            raise RuntimeError("Codex CLI was not found on PATH")

        self.executable = executable

    def build_command(
        self,
        *,
        prompt: str,
        model: str,
        sandbox: str,
        output_file: Path,
        output_schema_file: Path | None = None,
    ) -> list[str]:
        if sandbox not in self.ALLOWED_SANDBOXES:
            raise ValueError(
                f"Unsupported Codex sandbox: {sandbox}. "
                f"Allowed: {sorted(self.ALLOWED_SANDBOXES)}"
            )

        if not prompt.strip():
            raise ValueError("Codex prompt must not be empty")

        if not model.strip():
            raise ValueError("Codex model must not be empty")

        command = [
            self.executable,
            "exec",
            "-C",
            str(self.repo_root),
            "-m",
            model,
            "-s",
            sandbox,
            "--color",
            "never",
            # The sandboxed Codex subprocess does not inherit the
            # parent environment by default, which was observed to
            # leave it without a usable TEMP/TMP directory (a live
            # review explicitly reported "Pytest could not start
            # because the sandbox has no writable temporary
            # directory", and a live IMPLEMENTATION call reported
            # success while writing zero files -- consistent with an
            # internal file-write-apply step silently failing for the
            # same reason). This only controls environment-variable
            # VISIBILITY inside the sandbox; it does not weaken the
            # filesystem/network sandbox itself (still governed by
            # `-s read-only`/`-s workspace-write`) and is documented
            # by Codex's own --help as the example fix for exactly
            # this class of issue.
            "-c",
            "shell_environment_policy.inherit=all",
            "-o",
            str(output_file),
        ]

        if output_schema_file is not None:
            # Deterministic structured-output enforcement: constrains the
            # model's final response to valid JSON matching the schema,
            # so a reviewer cannot omit the machine-readable verdict by
            # forgetting a formatting instruction. execution_cycle.py's
            # structured-review parser still falls back to the legacy
            # FINDING/VERDICT text protocol if this ever produces
            # non-conforming output, so this is purely additive safety.
            command.extend([
                "--output-schema",
                str(output_schema_file),
            ])

        # The prompt is delivered via STDIN (see run()), never as a
        # command-line argument. Root cause of a live failure where a
        # multi-paragraph implementation prompt arrived at Codex
        # truncated to just its first sentence: `codex` resolves to a
        # Windows .CMD shim (confirmed via shutil.which), which Python
        # subprocess can only invoke through cmd.exe -- and cmd.exe's
        # argument-line parsing silently drops everything after the
        # first newline in an argument. Claude is unaffected (resolves
        # to a native .exe, invoked directly, no shell involved).
        # Passing "-" tells Codex explicitly to read the prompt from
        # stdin instead (documented in `codex exec --help`), which is
        # immune to this because stdin is a raw byte stream, never
        # parsed as a shell argument.
        command.append("-")

        return command

    def run(
        self,
        *,
        prompt: str,
        model: str,
        sandbox: str,
        output_schema: dict[str, Any] | None = None,
    ) -> CodexResult:
        with tempfile.TemporaryDirectory(
            prefix="vector-codex-"
        ) as temp_dir:
            output_file = Path(temp_dir) / "final_message.txt"

            output_schema_file: Path | None = None

            if output_schema is not None:
                output_schema_file = Path(temp_dir) / "output_schema.json"
                output_schema_file.write_text(
                    json.dumps(output_schema),
                    encoding="utf-8",
                )

            command = self.build_command(
                prompt=prompt,
                model=model,
                sandbox=sandbox,
                output_file=output_file,
                output_schema_file=output_schema_file,
            )

            try:
                completed = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    check=False,
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                return CodexResult(
                    command=command,
                    exit_code=None,
                    final_message="",
                    stdout=self._decode_timeout_stream(exc.stdout),
                    stderr=self._decode_timeout_stream(exc.stderr),
                    timed_out=True,
                )

            final_message = ""
            if output_file.exists():
                final_message = output_file.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).strip()

            return CodexResult(
                command=command,
                exit_code=completed.returncode,
                final_message=final_message,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict[str, Any] | None = None,
    ) -> CodexResult:
        return self.run(
            prompt=prompt,
            model=model,
            sandbox="read-only",
            output_schema=output_schema,
        )

    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
    ) -> CodexResult:
        return self.run(
            prompt=prompt,
            model=model,
            sandbox="workspace-write",
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
    adapter = CodexAdapter(repo_root)

    output = Path("example-output.txt")

    command = adapter.build_command(
        prompt="Read only. Reply with OK.",
        model="example-model",
        sandbox="read-only",
        output_file=output,
    )

    assert "exec" in command
    assert "-C" in command
    assert "-m" in command
    assert "example-model" in command
    assert "-s" in command
    assert "read-only" in command

    dangerous_flags = {
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
        "--ignore-rules",
    }

    assert dangerous_flags.isdisjoint(command)

    # Environment-inheritance fix (diagnosed from a live run where
    # Codex reported implementation success but wrote zero files, and
    # a live review separately reported "no writable temporary
    # directory"): the sandboxed subprocess must inherit TEMP/TMP.
    # This only affects environment-variable visibility, never the
    # filesystem/network sandbox itself, so it must never appear in
    # (or be confused with) the dangerous-bypass-flag set above.
    assert "-c" in command
    config_index = command.index("-c")
    assert (
        command[config_index + 1]
        == "shell_environment_policy.inherit=all"
    )
    assert "shell_environment_policy.inherit=all" not in dangerous_flags

    try:
        adapter.build_command(
            prompt="test",
            model="example-model",
            sandbox="danger-full-access",
            output_file=output,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "danger-full-access must be rejected"
        )

    # Structured-output enforcement for reviews (fix for the omitted-
    # VERDICT-line failure mode): --output-schema must be present, with
    # its own path, when a schema file is supplied; absent otherwise.
    schema_path = Path("example-schema.json")

    with_schema_command = adapter.build_command(
        prompt="Read only. Review and respond.",
        model="example-model",
        sandbox="read-only",
        output_file=output,
        output_schema_file=schema_path,
    )

    assert "--output-schema" in with_schema_command
    schema_index = with_schema_command.index("--output-schema")
    assert (
        with_schema_command[schema_index + 1] == str(schema_path)
    )
    # The trailing positional argument must be the literal "-"
    # (read-prompt-from-stdin marker), never the prompt text itself.
    assert with_schema_command[-1] == "-"
    assert dangerous_flags.isdisjoint(with_schema_command)

    without_schema_command = adapter.build_command(
        prompt="Read only. Review and respond.",
        model="example-model",
        sandbox="read-only",
        output_file=output,
    )

    assert "--output-schema" not in without_schema_command
    assert without_schema_command[-1] == "-"
    assert without_schema_command == command

    # Regression coverage for the live prompt-truncation bug: a
    # multi-line, multi-paragraph prompt (the actual shape every real
    # implementation/review prompt has) must NEVER appear as literal
    # argv content -- only "-" -- no matter how long or newline-heavy
    # it is. The real text is delivered via subprocess stdin in run()
    # instead (see run()'s `input=prompt`).
    multiline_prompt = (
        "You are the implementation owner for one bounded VECTOR "
        "development task.\n\n"
        "TASK:\nTEST-ONLY TASK. Modify ONLY tests/core/test_config.py."
        "\n\nREQUIRED TEST TARGETS:\n- tests/core/test_config.py\n\n"
        "Rules:\n- Follow AGENTS.md, CLAUDE.md and project rules.\n"
    )

    multiline_command = adapter.build_command(
        prompt=multiline_prompt,
        model="example-model",
        sandbox="workspace-write",
        output_file=output,
    )

    assert multiline_command[-1] == "-"
    assert all(
        "\n" not in arg
        for arg in multiline_command
    )
    assert not any(
        "TEST-ONLY TASK" in arg
        for arg in multiline_command
    )

    # Empty/whitespace-only prompts still fail closed even though the
    # text no longer appears in argv -- build_command must still
    # validate it (it is still required for stdin delivery in run()).
    try:
        adapter.build_command(
            prompt="   ",
            model="example-model",
            sandbox="read-only",
            output_file=output,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Empty/whitespace-only prompt must be rejected"
        )


if __name__ == "__main__":
    _self_test()
