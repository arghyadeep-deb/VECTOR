"""
VectorCode Terminal Tool — local subprocess execution, ported from Hermes terminal_tool.py.

Provides:
  - terminal_tool(command, background, timeout, cwd) -> str result
  - Background process registry (id -> subprocess.Popen)
  - cleanup_all_background() registered as atexit hook
  - Interrupt check via threading.Event (_interrupt_event)
  - Output truncation: first 50 + last 50 lines when > 200 lines
  - set_approval_callback / _get_approval_callback (thread-local)
  - OpenAI function schema: name "bash" for registry.py compatibility
  - risk_level: medium for normal, high for destructive patterns
"""
import sys
import atexit
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}


# ---------------------------------------------------------------------------
# Interrupt support
# ---------------------------------------------------------------------------

_interrupt_event: threading.Event = threading.Event()


def is_interrupted() -> bool:
    """Return True if an interrupt has been requested."""
    return _interrupt_event.is_set()


def set_interrupted(value: bool = True) -> None:
    """Set or clear the interrupt flag."""
    if value:
        _interrupt_event.set()
    else:
        _interrupt_event.clear()


# ---------------------------------------------------------------------------
# Thread-local approval callback
# ---------------------------------------------------------------------------

_callback_tls = threading.local()


def _get_approval_callback() -> Optional[Callable]:
    """Return the approval callback for the current thread, or None."""
    return getattr(_callback_tls, "approval", None)


def set_approval_callback(cb: Callable) -> None:
    """Register an approval callback for the current thread."""
    _callback_tls.approval = cb


# ---------------------------------------------------------------------------
# Background process registry
# ---------------------------------------------------------------------------

_bg_registry: Dict[str, subprocess.Popen] = {}
_bg_lock = threading.Lock()
_bg_counter = [0]


def _next_bg_id() -> str:
    with _bg_lock:
        _bg_counter[0] += 1
        return f"bg_{_bg_counter[0]}"


def cleanup_all_background() -> None:
    """Terminate all tracked background processes. Called on atexit."""
    with _bg_lock:
        pids = list(_bg_registry.keys())
    for pid_key in pids:
        try:
            with _bg_lock:
                proc = _bg_registry.pop(pid_key, None)
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            logger.debug("[VECTOR][terminal] cleaned up background process %s", pid_key)
        except Exception as e:
            logger.warning("[VECTOR][terminal] error cleaning background proc %s: %s", pid_key, e)


atexit.register(cleanup_all_background)


# ---------------------------------------------------------------------------
# Destructive pattern detection
# ---------------------------------------------------------------------------

_DESTRUCTIVE_PATTERNS = re.compile(
    r"\b(rm\s+-rf|rmdir|mkfs|dd\s+if=|:\s*\(\)\s*\{|chmod\s+777|"
    r"shutdown|reboot|halt|kill\s+-9|pkill|killall|"
    r"git\s+push\s+--force|git\s+reset\s+--hard|"
    r"DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE)\b",
    re.IGNORECASE,
)


def _is_destructive(command: str) -> bool:
    """Return True if the command matches known destructive patterns."""
    return bool(_DESTRUCTIVE_PATTERNS.search(command))


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------

_TRUNCATE_THRESHOLD = 200  # lines
_HEAD_LINES = 50
_TAIL_LINES = 50


def _truncate_output(output: str) -> str:
    """Keep first 50 + last 50 lines when output exceeds 200 lines."""
    lines = output.splitlines()
    if len(lines) <= _TRUNCATE_THRESHOLD:
        return output
    omitted = len(lines) - _HEAD_LINES - _TAIL_LINES
    head = "\n".join(lines[:_HEAD_LINES])
    tail = "\n".join(lines[-_TAIL_LINES:])
    notice = f"\n\n... [{omitted} lines omitted out of {len(lines)} total] ...\n\n"
    return head + notice + tail


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def terminal_tool(
    command: str,
    background: bool = False,
    timeout: int = 120,
    cwd: Optional[str] = None,
) -> str:
    """Execute a shell command locally.

    Args:
        command:    Shell command string.
        background: If True, spawn in background and return session_id.
        timeout:    Seconds before the foreground command is killed (default 120).
        cwd:        Working directory. Defaults to cwd at call time.

    Returns:
        JSON string: {output, exit_code, error} or {session_id, pid, output, exit_code}.
    """
    if not isinstance(command, str) or not command.strip():
        return json.dumps({"output": "", "exit_code": -1, "error": "Empty or invalid command"})

    effective_cwd = cwd or os.getcwd()
    risk = "high" if _is_destructive(command) else "medium"

    # Approval gate for high-risk commands
    if risk == "high":
        cb = _get_approval_callback()
        if cb is not None:
            try:
                approved = cb(command, risk)
                if not approved:
                    return json.dumps({
                        "output": "",
                        "exit_code": -1,
                        "error": f"Command blocked (risk={risk}): {command[:100]}",
                        "status": "blocked",
                    })
            except Exception as e:
                logger.warning("[VECTOR][terminal] approval callback error: %s", e)

    if background:
        return _run_background(command, effective_cwd)
    else:
        return _run_foreground(command, effective_cwd, timeout)


def _run_foreground(command: str, cwd: str, timeout: int) -> str:
    """Run command in the foreground and return JSON result."""
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
        )

        deadline = time.monotonic() + timeout
        chunks = []

        while proc.poll() is None:
            if is_interrupted():
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return json.dumps({
                    "output": _truncate_output("".join(chunks)),
                    "exit_code": -1,
                    "error": "Command interrupted",
                })
            if time.monotonic() > deadline:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return json.dumps({
                    "output": _truncate_output("".join(chunks)),
                    "exit_code": 124,
                    "error": f"Command timed out after {timeout}s",
                })
            try:
                line = proc.stdout.readline()
                if line:
                    chunks.append(line)
            except Exception:
                break
            time.sleep(0.05)

        # Drain remaining output
        try:
            remaining = proc.stdout.read()
            if remaining:
                chunks.append(remaining)
        except Exception:
            pass

        output = _truncate_output("".join(chunks))
        return json.dumps({
            "output": output.rstrip(),
            "exit_code": proc.returncode if proc.returncode is not None else 0,
            "error": None,
        })

    except FileNotFoundError as e:
        return json.dumps({"output": "", "exit_code": -1, "error": f"Command not found: {e}"})
    except Exception as e:
        logger.error("[VECTOR][terminal] foreground execution error: %s", e)
        return json.dumps({"output": "", "exit_code": -1, "error": str(e)})


def _run_background(command: str, cwd: str) -> str:
    """Spawn command in background and register it. Returns JSON with session_id."""
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
        )
        session_id = _next_bg_id()
        with _bg_lock:
            _bg_registry[session_id] = proc
        logger.info("[VECTOR][terminal] background process started: %s (pid=%s)", session_id, proc.pid)
        return json.dumps({
            "output": "Background process started",
            "session_id": session_id,
            "pid": proc.pid,
            "exit_code": 0,
            "error": None,
        })
    except Exception as e:
        logger.error("[VECTOR][terminal] background spawn error: %s", e)
        return json.dumps({"output": "", "exit_code": -1, "error": str(e)})


# ---------------------------------------------------------------------------
# OpenAI Function Schema (name: "bash" for registry compatibility)
# ---------------------------------------------------------------------------

BASH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Execute a shell command locally. Returns stdout+stderr. "
            "Default timeout: 60s. Use background=true for long-lived processes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "background": {
                    "type": "boolean",
                    "description": "Run in background, returns session_id (default: false)",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 60, max: 120)",
                    "default": 60,
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (default: project dir)",
                },
            },
            "required": ["command"],
        },
    },
    "_meta": {"risk": "medium", "read_only": False},
}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile, json as _json

    # Foreground test
    result = terminal_tool("echo hello_vector")
    data = _json.loads(result)
    assert data["exit_code"] == 0, f"exit_code should be 0, got {data}"
    assert "hello_vector" in data["output"], f"expected hello_vector in output: {data}"

    # Non-zero exit code test
    result2 = terminal_tool("exit 42", timeout=5)
    data2 = _json.loads(result2)
    assert data2["exit_code"] != 0, f"expected non-zero exit, got {data2}"

    # Background test
    result3 = terminal_tool("echo bg_test", background=True)
    data3 = _json.loads(result3)
    assert "session_id" in data3, f"expected session_id in: {data3}"
    assert data3["exit_code"] == 0, f"background spawn should succeed: {data3}"

    # Truncation test
    long_output = "\n".join(str(i) for i in range(300))
    truncated = _truncate_output(long_output)
    assert "lines omitted" in truncated, "expected truncation notice"

    # Destructive detection
    assert _is_destructive("rm -rf /"), "rm -rf should be destructive"
    assert not _is_destructive("ls -la"), "ls should not be destructive"

    # Schema check
    assert BASH_SCHEMA["function"]["name"] == "bash"

    print("tools/terminal.py OK")
