# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Subprocess sandbox — secure process execution with environment isolation."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional

from loguru import logger

# Safe environment variables to pass through
_SAFE_ENV_VARS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "TERM",
        "SHELL",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "TZ",
    }
)

@dataclass(slots=True)
class SandboxResult:
    """Result of a sandboxed subprocess execution."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = -1
    timed_out: bool = False
    killed: bool = False

def build_safe_env(
    passthrough: Optional[List[str]] = None,
    extra: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build a sanitized environment dict.

    Only copies safe vars from current env, plus any in passthrough list.
    Extra vars are added directly.
    """
    env: Dict[str, str] = {}
    allowed = _SAFE_ENV_VARS | frozenset(passthrough or [])
    for key in allowed:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    if extra:
        env.update(extra)
    return env

def kill_process_tree(pid: int) -> None:
    """Kill a process and all its children (best effort)."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            logger.debug("Failed to terminate Windows process tree {}: {}", pid, exc)
        return

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, ProcessLookupError) as exc:
        logger.debug("Failed to terminate process {}: {}", pid, exc)
    try:
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError) as exc:
        logger.debug("Failed to kill process {}: {}", pid, exc)

def run_sandboxed(
    command: str,
    *,
    timeout: float = 30.0,
    working_dir: Optional[str] = None,
    env_passthrough: Optional[List[str]] = None,
    env_extra: Optional[Dict[str, str]] = None,
    max_output_bytes: int = 102_400,
) -> SandboxResult:
    """Execute a command in a sandboxed subprocess.

    Features:
    - Clean environment (only safe vars passed through)
    - Timeout enforcement with process tree kill
    - Output truncation
    - New process group for clean cleanup
    """
    env = build_safe_env(passthrough=env_passthrough, extra=env_extra)
    cwd = working_dir if working_dir and os.path.isdir(working_dir) else None

    result = SandboxResult()
    try:
        process_group_options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"preexec_fn": os.setsid}
        )
        proc = subprocess.Popen(
            shlex.split(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=cwd,
            **process_group_options,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            result.stdout = stdout[:max_output_bytes] if stdout else ""
            result.stderr = stderr[:max_output_bytes] if stderr else ""
            result.returncode = proc.returncode
        except subprocess.TimeoutExpired:
            kill_process_tree(proc.pid)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # The process survived SIGKILL/taskkill (e.g. stuck in an
                # uninterruptible syscall) -- don't let this second timeout
                # propagate uncaught and crash the caller; the sandbox has
                # already done everything it can to stop it.
                logger.warning(
                    "Process {} did not exit within 5s of being killed", proc.pid
                )
            result.timed_out = True
            result.killed = True
            result.returncode = -1
            result.stdout = "(timed out)"
            result.stderr = ""
    except OSError as exc:
        result.stderr = f"Execution error: {exc}"
        result.returncode = -1

    return result

__all__ = ["SandboxResult", "build_safe_env", "kill_process_tree", "run_sandboxed"]
