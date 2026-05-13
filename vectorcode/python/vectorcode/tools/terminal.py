# Ported from GitHub/NousResearch_hermes-agent/repo/tools/terminal_tool.py
"""Terminal tool — execute shell commands with approval gate."""
import json
import os
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from loguru import logger

from .registry import registry
from ..engine.safety import _is_destructive_command

_approval_callback: Optional[Callable] = None
_approval_lock = threading.Lock()

_cwd = os.getcwd()
_cwd_lock = threading.Lock()

_DEFAULT_TIMEOUT = 120  # seconds
_MAX_OUTPUT_CHARS = 50_000


def set_approval_callback(fn: Optional[Callable]) -> None:
    global _approval_callback
    with _approval_lock:
        _approval_callback = fn


def _get_approval_callback() -> Optional[Callable]:
    with _approval_lock:
        return _approval_callback


def _get_cwd() -> str:
    with _cwd_lock:
        return _cwd


def _set_cwd(new_cwd: str) -> None:
    global _cwd
    with _cwd_lock:
        _cwd = new_cwd


def _check_approval(command: str, risk_level: str) -> bool:
    """Check if command is approved. Returns True if approved."""
    cb = _get_approval_callback()
    if cb is None:
        return True  # No callback = auto-approve
    try:
        result = cb(command, risk_level)
        return bool(result)
    except Exception as e:
        logger.warning(f"Approval callback error: {e}")
        return False


def bash(
    command: str,
    timeout: int = _DEFAULT_TIMEOUT,
    cwd: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Execute a shell command and return its output.

    Uses shlex.split + shell=False for injection safety.
    Destructive commands require approval.
    """
    if not command or not command.strip():
        return json.dumps({"error": "Empty command"})

    # Determine risk level
    risk = "high" if _is_destructive_command(command) else "medium"

    # Check approval for destructive commands
    if risk == "high":
        if not _check_approval(command, risk):
            return json.dumps({"error": f"Command blocked by approval gate: {command[:80]}"})

    work_dir = cwd or _get_cwd()

    # Handle cd specially — update tracked cwd
    stripped = command.strip()
    if stripped.startswith("cd "):
        target = stripped[3:].strip().strip("'\"")
        try:
            new_dir = str(Path(work_dir) / target) if not Path(target).is_absolute() else target
            new_dir = str(Path(new_dir).resolve())
            if Path(new_dir).is_dir():
                _set_cwd(new_dir)
                return json.dumps({"stdout": "", "stderr": "", "returncode": 0, "cwd": new_dir})
            else:
                return json.dumps({"error": f"cd: no such directory: {target}"})
        except Exception as e:
            return json.dumps({"error": f"cd error: {e}"})

    try:
        # Use shell=True on Windows for compatibility, shell=False on Unix
        if os.name == "nt":
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=work_dir,
            )
        else:
            try:
                args = shlex.split(command)
            except ValueError:
                args = command.split()
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=work_dir,
            )
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out after {timeout}s", "command": command[:80]})
    except FileNotFoundError as e:
        return json.dumps({"error": f"Command not found: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Execution error: {e}"})

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    # Truncate oversized output
    if len(stdout) > _MAX_OUTPUT_CHARS:
        stdout = stdout[:_MAX_OUTPUT_CHARS] + f"\n[...stdout truncated at {_MAX_OUTPUT_CHARS} chars]"
    if len(stderr) > _MAX_OUTPUT_CHARS:
        stderr = stderr[:_MAX_OUTPUT_CHARS] + f"\n[...stderr truncated at {_MAX_OUTPUT_CHARS} chars]"

    return json.dumps({
        "stdout": stdout,
        "stderr": stderr,
        "returncode": result.returncode,
        "cwd": work_dir,
    })


# ── Register ──────────────────────────────────────────────────────────────────

registry.register(
    name="bash",
    handler=bash,
    schema={
        "description": "Execute a shell command. Returns stdout, stderr, and return code.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)"},
                "description": {"type": "string", "description": "Human-readable description of what this command does"},
            },
            "required": ["command"],
        },
    },
    toolset="coding",
    risk_level="medium",
    emoji="💻",
)
