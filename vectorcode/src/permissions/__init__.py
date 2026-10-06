"""Permission modes for VectorCode — cautious | standard | autonomous | read-only.

Mirrors the spec §7.1 permission system.

Mode       | Reads | File writes | Bash | Destructive
-----------|-------|-------------|------|------------
cautious   |  auto | ask         | ask  | ask
standard   |  auto | auto        | ask  | ask
autonomous |  auto | auto        | auto | ask
read-only  |  auto | block       | block| block
"""

import sys
import fnmatch
import os
from enum import Enum

from loguru import logger


class PermissionMode(str, Enum):
    CAUTIOUS   = "cautious"
    STANDARD   = "standard"
    AUTONOMOUS = "autonomous"
    READ_ONLY  = "read-only"


class PermissionResult:
    def __init__(self, allowed: bool, reason: str = "") -> None:
        self.allowed = allowed
        self.reason  = reason

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"PermissionResult(allowed={self.allowed}, reason={self.reason!r})"


class PermissionSystem:
    """
    Evaluates whether a given tool action is allowed given the current mode,
    allowlist/denylist rules, and risk level.

    Designed to be called synchronously — no async, no blocking prompts.
    When the mode requires a user confirmation, it returns `allowed=False`
    with `reason='requires_approval'` so the caller can prompt the user.
    """

    def __init__(
        self,
        mode: PermissionMode | str = PermissionMode.STANDARD,
        allow_bash: list[str] | None = None,
        deny_bash: list[str] | None = None,
        allow_write_paths: list[str] | None = None,
        deny_write_paths: list[str] | None = None,
    ) -> None:
        if isinstance(mode, str):
            try:
                mode = PermissionMode(mode)
            except ValueError:
                logger.warning(f"[VECTOR][perms] unknown mode '{mode}', defaulting to standard")
                mode = PermissionMode.STANDARD
        self.mode = mode
        self.allow_bash = [] if allow_bash is None else allow_bash
        self.deny_bash = ["rm -rf"] if deny_bash is None else deny_bash
        self.allow_write_paths = [] if allow_write_paths is None else allow_write_paths
        self.deny_write_paths = (
            [".env", "*.pem", "secrets/**"]
            if deny_write_paths is None
            else deny_write_paths
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def check_read(self, path: str = "") -> PermissionResult:
        """Reads are always auto-approved."""
        return PermissionResult(True, "reads always allowed")

    def check_write(self, path: str = "") -> PermissionResult:
        """Check if writing to path is permitted."""
        if self.mode == PermissionMode.READ_ONLY:
            return PermissionResult(False, "read-only mode blocks all writes")

        # Hard denylist
        if self._matches_any(path, self.deny_write_paths):
            return PermissionResult(False, f"path '{path}' in deny_write_paths")

        # Hard allowlist (explicit allow bypasses mode check)
        if self._matches_any(path, self.allow_write_paths):
            return PermissionResult(True, "path in allow_write_paths")

        if self.mode == PermissionMode.CAUTIOUS:
            return PermissionResult(False, "requires_approval")

        # standard / autonomous: auto-approve file writes
        return PermissionResult(True, f"auto-approved by {self.mode.value} mode")

    def check_bash(self, command: str = "") -> PermissionResult:
        """Check if running a shell command is permitted."""
        if self.mode == PermissionMode.READ_ONLY:
            return PermissionResult(False, "read-only mode blocks all bash")

        # Hard denylist — check if any deny pattern is a substring of command
        for pattern in self.deny_bash:
            if pattern.lower() in command.lower():
                return PermissionResult(False, f"command matches deny_bash pattern: {pattern!r}")

        # Allowlist — explicit allow
        for pattern in self.allow_bash:
            if command.lower().startswith(pattern.lower()):
                return PermissionResult(True, f"command in allow_bash")

        if self.mode == PermissionMode.AUTONOMOUS:
            return PermissionResult(True, "auto-approved by autonomous mode")

        # cautious / standard: bash requires approval
        return PermissionResult(False, "requires_approval")

    def check_destructive(self, action: str = "") -> PermissionResult:
        """Destructive actions (delete, push, deploy) always require approval."""
        if self.mode == PermissionMode.READ_ONLY:
            return PermissionResult(False, "read-only mode blocks destructive actions")
        return PermissionResult(False, "requires_approval")

    def check_tool(self, tool_name: str, risk_level: str, **kwargs) -> PermissionResult:
        """
        Unified check by tool name and risk level.
        risk_level: safe | low | medium | high | critical
        """
        if risk_level == "safe":
            return self.check_read()
        if risk_level in ("low", "medium"):
            path = kwargs.get("path", "")
            command = kwargs.get("command", "")
            if command:
                return self.check_bash(command)
            return self.check_write(path)
        if risk_level in ("high", "critical"):
            return self.check_destructive(tool_name)
        logger.warning(
            "[VECTOR][perms] unknown risk level {!r}; denying action {!r}",
            risk_level,
            tool_name,
        )
        return PermissionResult(False, "unknown risk level — defaulting to deny")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _matches_any(path: str, patterns: list[str]) -> bool:
        normalized_path = os.path.normcase(os.path.normpath(path))
        for pat in patterns:
            normalized_pattern = os.path.normcase(os.path.normpath(pat))
            suffix = normalized_pattern.lstrip("*")
            if fnmatch.fnmatch(normalized_path, normalized_pattern) or (
                suffix and normalized_path.endswith(suffix)
            ):
                return True
        return False

    @classmethod
    def from_config(cls, cfg) -> "PermissionSystem":
        """Build from a VectorConfig instance."""
        perms = cfg.get("permissions", default={})
        return cls(
            mode=perms.get("mode", "standard"),
            allow_bash=perms.get("allow_bash", []),
            deny_bash=perms.get("deny_bash", ["rm -rf"]),
            allow_write_paths=perms.get("allow_write_paths", []),
            deny_write_paths=perms.get("deny_write_paths", [".env", "*.pem"]),
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # standard mode
    ps = PermissionSystem(mode="standard")
    assert ps.check_read("any/file.py")
    assert ps.check_write("src/main.py")
    assert not ps.check_bash("npm test")          # standard: bash requires approval
    assert not ps.check_write(".env")              # denylist
    assert not ps.check_bash("rm -rf /")          # denylist

    # autonomous mode
    ps_auto = PermissionSystem(mode="autonomous")
    assert ps_auto.check_bash("npm test")
    assert ps_auto.check_bash("pytest tests/")

    # read-only mode
    ps_ro = PermissionSystem(mode="read-only")
    assert ps_ro.check_read("any.py")
    assert not ps_ro.check_write("src/main.py")
    assert not ps_ro.check_bash("npm test")

    # cautious mode
    ps_caut = PermissionSystem(mode="cautious")
    assert not ps_caut.check_write("src/main.py")  # requires approval

    print("permissions/__init__.py OK")


