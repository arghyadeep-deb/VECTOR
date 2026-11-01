"""Safe Claude Code CLI adapter for the VECTOR development orchestrator."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ClaudeResult:
    """Result of one Claude CLI invocation."""

    command: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        if self.exit_code != 0 or self.timed_out:
            return False
        # A clean process exit is not a successful Claude invocation when its
        # structured result explicitly reports a turn/budget/runtime error.
        # Git deltas and tests still independently establish implementation.
        try:
            payload = json.loads(self.stdout)
        except (ValueError, TypeError):
            return True  # Preserve compatibility with older plain-text CLIs.
        if not isinstance(payload, dict):
            return True
        return not (
            payload.get("is_error")
            or str(payload.get("subtype", "")).startswith("error")
            or payload.get("type") == "error"
        )


class ClaudeAdapter:
    """Invoke Claude Code with explicit model, effort and permission controls."""

    ALLOWED_PERMISSION_MODES = {
        "plan",
        "acceptEdits",
    }

    ALLOWED_EFFORTS = {
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }

    def __init__(
        self,
        repo_root: Path,
        timeout_seconds: int = 1800,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.timeout_seconds = timeout_seconds

        executable = shutil.which("claude")
        if executable is None:
            raise RuntimeError("Claude CLI was not found on PATH")

        self.executable = executable

    def build_command(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        permission_mode: str,
    ) -> list[str]:
        if not prompt.strip():
            raise ValueError("Claude prompt must not be empty")

        if not model.strip():
            raise ValueError("Claude model must not be empty")

        if effort not in self.ALLOWED_EFFORTS:
            raise ValueError(
                f"Unsupported Claude effort: {effort}. "
                f"Allowed: {sorted(self.ALLOWED_EFFORTS)}"
            )

        if permission_mode not in self.ALLOWED_PERMISSION_MODES:
            raise ValueError(
                f"Unsupported Claude permission mode: {permission_mode}. "
                f"Allowed: {sorted(self.ALLOWED_PERMISSION_MODES)}"
            )

        return [
            self.executable,
            "-p",
            prompt,
            "--model",
            model,
            "--effort",
            effort,
            "--permission-mode",
            permission_mode,
            "--output-format",
            "json",
        ]

    def run(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        permission_mode: str,
    ) -> ClaudeResult:
        command = self.build_command(
            prompt=prompt,
            model=model,
            effort=effort,
            permission_mode=permission_mode,
        )

        return self._run_command(command)

    def _run_command(
        self,
        command: list[str],
    ) -> ClaudeResult:
        try:
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ClaudeResult(
                command=command,
                exit_code=None,
                stdout=self._decode_timeout_stream(exc.stdout),
                stderr=self._decode_timeout_stream(exc.stderr),
                timed_out=True,
            )

        return ClaudeResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def build_read_only_command(
        self,
        *,
        prompt: str,
        model: str,
        effort: str = "medium",
        json_schema: dict[str, Any] | None = None,
    ) -> list[str]:
        command = self.build_command(
            prompt=prompt,
            model=model,
            effort=effort,
            permission_mode="plan",
        )

        # A read-only review must still be isolated from VECTOR project
        # hooks/settings/customizations (auto-commit, auto-test, etc.) --
        # otherwise a "read-only" review session could still trigger
        # side effects through inherited hooks. Grant only the Read tool
        # so the session stays genuinely read-only.
        command.extend([
            "--safe-mode",
            "--setting-sources",
            "local",
            "--tools",
            "Read",
        ])

        if json_schema is not None:
            # Deterministic structured-output enforcement: constrains the
            # final response to valid JSON matching the schema, so a
            # reviewer cannot omit the machine-readable verdict by
            # forgetting a formatting instruction. execution_cycle.py's
            # structured-review parser still falls back to the legacy
            # FINDING/VERDICT text protocol if this ever produces
            # non-conforming output, so this is purely additive safety.
            command.extend([
                "--json-schema",
                json.dumps(json_schema, separators=(",", ":")),
            ])

        return command

    def build_implementation_command(
        self,
        *,
        prompt: str,
        model: str,
        effort: str = "medium",
    ) -> list[str]:
        command = self.build_command(
            prompt=prompt,
            model=model,
            effort=effort,
            permission_mode="acceptEdits",
        )

        # Do not inherit project/user hooks such as auto-commit or auto-test.
        # The orchestrator owns Git state, tests and cross-provider review.
        command.extend([
            # Deliberately exclude user/project settings. VECTOR's tracked
            # project settings contain hooks such as auto-commit, while fresh
            # orchestrator worktrees have no settings.local.json.
            "--safe-mode",
            "--setting-sources",
            "local",
            "--tools",
            # Bash/Grep/Glob added: acceptEdits only auto-approves file
            # edits, so without an explicit grant here a headless run can
            # never answer the interactive prompt these three would need --
            # the implementer silently has no shell/search access and
            # correctly declines any task needing one (observed on two
            # real backlog items). Edit/Write stay the only auto-accepted
            # side effects; Bash/Grep/Glob are read/search plus commands
            # still confined to this isolated worktree.
            "Read,Edit,Write,Bash,Grep,Glob",
        ])

        return command

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str = "medium",
        json_schema: dict[str, Any] | None = None,
    ) -> ClaudeResult:
        command = self.build_read_only_command(
            prompt=prompt,
            model=model,
            effort=effort,
            json_schema=json_schema,
        )

        return self._run_command(command)

    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
        effort: str = "medium",
    ) -> ClaudeResult:
        command = self.build_implementation_command(
            prompt=prompt,
            model=model,
            effort=effort,
        )

        return self._run_command(command)

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
    adapter = ClaudeAdapter(repo_root)

    command = adapter.build_command(
        prompt="Read only. Reply with OK.",
        model="sonnet",
        effort="medium",
        permission_mode="plan",
    )

    assert "-p" in command
    assert "--model" in command
    assert "sonnet" in command
    assert "--effort" in command
    assert "medium" in command
    assert "--permission-mode" in command
    assert "plan" in command
    assert "--output-format" in command
    assert "json" in command

    dangerous_flags = {
        "--dangerously-skip-permissions",
        "--allow-dangerously-skip-permissions",
        "--bare",
        "--safe-mode",
    }

    assert dangerous_flags.isdisjoint(command)

    try:
        adapter.build_command(
            prompt="test",
            model="sonnet",
            effort="medium",
            permission_mode="bypassPermissions",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "bypassPermissions must be rejected"
        )

    # Issue 4 regression: read-only REVIEW sessions must also get safe
    # isolation from VECTOR project hooks/settings, while remaining
    # genuinely read-only (plan mode, Read tool only).
    read_only_command = adapter.build_read_only_command(
        prompt="Read only. Reply with OK.",
        model="sonnet",
        effort="medium",
    )

    assert "--permission-mode" in read_only_command
    permission_index = read_only_command.index("--permission-mode")
    assert read_only_command[permission_index + 1] == "plan"

    assert "--safe-mode" in read_only_command
    assert "--setting-sources" in read_only_command
    setting_sources_index = read_only_command.index("--setting-sources")
    assert read_only_command[setting_sources_index + 1] == "local"

    assert "--tools" in read_only_command
    tools_index = read_only_command.index("--tools")
    assert read_only_command[tools_index + 1] == "Read"

    bypass_flags = {
        "--dangerously-skip-permissions",
        "--allow-dangerously-skip-permissions",
        "--bare",
    }
    assert bypass_flags.isdisjoint(read_only_command)

    # Isolation must not grant the review session Edit/Write access.
    assert "Edit" not in read_only_command[tools_index + 1]
    assert "Write" not in read_only_command[tools_index + 1]

    # Implementation isolation (already relied upon) must be preserved.
    implementation_command = adapter.build_implementation_command(
        prompt="Implement the change.",
        model="sonnet",
        effort="medium",
    )

    assert "--safe-mode" in implementation_command
    assert "--setting-sources" in implementation_command
    impl_tools_index = implementation_command.index("--tools")
    assert (
        implementation_command[impl_tools_index + 1]
        == "Read,Edit,Write,Bash,Grep,Glob"
    )

    impl_permission_index = implementation_command.index(
        "--permission-mode"
    )
    assert (
        implementation_command[impl_permission_index + 1]
        == "acceptEdits"
    )

    assert bypass_flags.isdisjoint(implementation_command)

    # Structured-output enforcement for reviews (fix for the omitted-
    # VERDICT-line failure mode): --json-schema carries the compact
    # serialized schema when supplied; absent otherwise, with no other
    # part of the isolated command affected.
    example_schema = {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["PASS", "CHANGES_REQUIRED"],
            },
        },
        "required": ["verdict"],
    }

    schema_command = adapter.build_read_only_command(
        prompt="Read only. Review and respond.",
        model="sonnet",
        effort="medium",
        json_schema=example_schema,
    )

    assert "--json-schema" in schema_command
    schema_index = schema_command.index("--json-schema")
    assert json.loads(schema_command[schema_index + 1]) == example_schema

    # Isolation flags are unaffected by adding the schema.
    assert "--safe-mode" in schema_command
    schema_tools_index = schema_command.index("--tools")
    assert schema_command[schema_tools_index + 1] == "Read"
    assert bypass_flags.isdisjoint(schema_command)

    no_schema_command = adapter.build_read_only_command(
        prompt="Read only. Review and respond.",
        model="sonnet",
        effort="medium",
    )

    assert "--json-schema" not in no_schema_command


if __name__ == "__main__":
    _self_test()
