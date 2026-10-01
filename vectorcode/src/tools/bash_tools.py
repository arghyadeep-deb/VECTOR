from core.config import CONFIG

import subprocess
from loguru import logger

ALLOWED_COMMANDS: frozenset = frozenset({
    "python", "python3",
    "pip", "pip3",
    "pytest",
    "git",
    "npm", "node",
    "cargo",
    "go",
    "java", "javac",
    "make", "cmake",
    "docker", "kubectl",
    "ruff", "mypy", "black", "isort",
    "pre-commit",
})

# Each entry is a list of tokens that, if all present as a subsequence in cmd, block the command
BLOCKED_PATTERNS: list = [
    ["rm", "-rf"],
    ["dd", "if="],
    ["mkfs"],
    ["bash", "-c"],
    ["sh", "-c"],
    # Pipe-based download tricks (curl/wget piped to shell) — detect by presence of "|" token
    ["curl", "|"],
    ["wget", "|"],
]


class BashTools:
    """
    Safe subprocess wrapper.
    - Only commands in ALLOWED_COMMANDS may be executed.
    - BLOCKED_PATTERNS are always rejected regardless of allowlist.
    - shell=False is enforced — there is no escape hatch.
    """

    def is_allowed(self, cmd: list) -> bool:
        """Return True if cmd[0] is in ALLOWED_COMMANDS and no blocked pattern matches."""
        if not cmd:
            return False
        if cmd[0] not in ALLOWED_COMMANDS:
            return False
        # Check blocked patterns
        cmd_set = set(cmd)
        for pattern in BLOCKED_PATTERNS:
            # A pattern matches if every token in it appears in cmd (order-insensitive subset check)
            # For two-token patterns like ["bash", "-c"] this is an exact subset check
            if all(tok in cmd_set for tok in pattern):
                return False
        return True

    def run(
        self,
        cmd: list,
        timeout: int = 30,
        cwd: str = None,
    ) -> subprocess.CompletedProcess:
        """
        Execute cmd as a subprocess with shell=False.

        Raises:
            PermissionError: if cmd is not in the allowlist or matches a blocked pattern.
            TimeoutError: if the process exceeds `timeout` seconds.
        """
        if not self.is_allowed(cmd):
            raise PermissionError(
                f"Command not allowed: {cmd}. "
                f"First token must be in ALLOWED_COMMANDS and must not match a blocked pattern."
            )
        logger.debug(f"[VECTOR][bash_tools] run {cmd} (timeout={timeout}s)")
        try:
            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            return result
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"Command timed out after {timeout}s: {cmd}"
            ) from exc


if __name__ == "__main__":
    bt = BashTools()
    result = bt.run(["python", "--version"])
    assert result.returncode == 0
    assert "Python" in (result.stdout + result.stderr)

    try:
        bt.run(["rm", "-rf", "/"])
        assert False, "Should have raised PermissionError"
    except PermissionError as _sve:
        logger.warning("[VECTOR][tools.bash_tools] suppressed PermissionError: {}", _sve)

    try:
        bt.run(["bash", "-c", "whoami"])
        assert False, "Should have raised PermissionError"
    except PermissionError as _sve:
        logger.warning("[VECTOR][tools.bash_tools] suppressed PermissionError: {}", _sve)

    print("bash_tools.py OK")


