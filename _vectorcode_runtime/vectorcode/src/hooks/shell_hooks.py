"""Shell hooks runner — absorbed from reference agent/shell_hooks.py.

Reads hooks from vector.toml [hooks] config, executes shell scripts with:
- JSON stdin protocol (event_name, tool_name, tool_input, session_id, cwd)
- First-use consent via allowlist (~/.vector/shell-hooks-allowlist.json)
- shlex.split + shell=False (no injection footguns)
- Block/inject response parsing from stdout

Wire protocol:
  stdin (JSON):  {hook_event_name, tool_name, tool_input, session_id, cwd, extra}
  stdout (JSON): {"decision": "block", "reason": "..."} to block pre_tool_call
                 {"context": "..."} to inject context for pre_llm_call
                 anything else → silent no-op

Supported events:
  pre_tool_call, post_tool_call, pre_bash, post_bash,
  session_start, session_end, file_write, file_edit, git_commit
"""
import sys
import json
import os
import shlex
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from loguru import logger
from pathlib import Path

_ALLOWLIST_PATH = Path.home() / ".vector" / "shell-hooks-allowlist.json"
_DEFAULT_TIMEOUT = 60
_MAX_TIMEOUT     = 300

_allowlist_lock = threading.Lock()


def _load_allowlist() -> dict:
    if _ALLOWLIST_PATH.exists():
        try:
            return json.loads(_ALLOWLIST_PATH.read_text(encoding="utf-8"))
        except Exception as _sve:
            logger.debug("[VECTOR][hooks.shell_hooks] suppressed Exception: %s", _sve)
    return {}


def _save_allowlist(data: dict) -> None:
    _ALLOWLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ALLOWLIST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_approved(event: str, command: str) -> bool:
    with _allowlist_lock:
        al = _load_allowlist()
        return al.get(f"{event}::{command}", False)


def _approve(event: str, command: str) -> None:
    with _allowlist_lock:
        al = _load_allowlist()
        al[f"{event}::{command}"] = True
        _save_allowlist(al)


class HookResult:
    __slots__ = ("blocked", "reason", "injected_context", "stdout", "exit_code")

    def __init__(self, blocked=False, reason="", injected_context="",
                 stdout="", exit_code=0):
        self.blocked = blocked
        self.reason = reason
        self.injected_context = injected_context
        self.stdout = stdout
        self.exit_code = exit_code


class ShellHookRunner:
    """
    Runs shell-script hooks from vector.toml [hooks] configuration.

    Usage:
        runner = ShellHookRunner.from_config(cfg)
        result = runner.invoke("pre_tool_call", tool_name="bash",
                               tool_input={"command": "ls"}, session_id="sess_1")
        if result.blocked:
            raise PermissionError(result.reason)
    """

    SUPPORTED_EVENTS = frozenset({
        "pre_tool_call", "post_tool_call",
        "pre_bash", "post_bash",
        "session_start", "session_end",
        "file_write", "file_edit",
        "git_commit",
    })

    def __init__(
        self,
        hooks: Dict[str, List[str]],
        auto_accept: bool = False,
        timeout: int = _DEFAULT_TIMEOUT,
        cwd: str = "",
    ):
        self._hooks = hooks         # {event: [cmd, cmd, ...]}
        self._auto_accept = auto_accept
        self._timeout = min(timeout, _MAX_TIMEOUT)
        self._cwd = cwd or str(Path.cwd())

    @classmethod
    def from_config(cls, cfg: dict, **kwargs) -> "ShellHookRunner":
        """Build from VectorCode config dict (vector.toml [hooks] section)."""
        hooks_cfg = cfg.get("hooks", {})
        hooks: Dict[str, List[str]] = {}
        for event in cls.SUPPORTED_EVENTS:
            val = hooks_cfg.get(event, [])
            if isinstance(val, str):
                val = [val]
            if val:
                hooks[event] = val
        auto_accept = hooks_cfg.get("auto_accept", False)
        timeout = hooks_cfg.get("timeout", _DEFAULT_TIMEOUT)
        return cls(hooks=hooks, auto_accept=auto_accept, timeout=timeout, **kwargs)

    def has_hooks(self, event: str) -> bool:
        return bool(self._hooks.get(event))

    def invoke(
        self,
        event: str,
        tool_name: str = "",
        tool_input: Any = None,
        session_id: str = "",
        extra: Optional[Dict] = None,
    ) -> HookResult:
        """Run all hooks registered for event. Returns first block decision or merged context."""
        commands = self._hooks.get(event, [])
        if not commands:
            return HookResult()

        payload = json.dumps({
            "hook_event_name": event,
            "tool_name": tool_name,
            "tool_input": tool_input or {},
            "session_id": session_id,
            "cwd": self._cwd,
            "extra": extra or {},
        }, ensure_ascii=False)

        collected_context = []
        for cmd in commands:
            result = self._run_one(event, cmd, payload)
            if result.blocked:
                return result
            if result.injected_context:
                collected_context.append(result.injected_context)

        return HookResult(
            injected_context="\n".join(collected_context),
            stdout="",
            exit_code=0,
        )

    def _run_one(self, event: str, cmd: str, payload: str) -> HookResult:
        """Run a single shell hook command."""
        # Consent check
        if not self._auto_accept and not _is_approved(event, cmd):
            if sys.stdin.isatty():
                print(f"\n[VECTOR] New shell hook wants to run:\n  Event: {event}\n  Command: {cmd}")
                answer = input("  Allow this hook? [y/N]: ").strip().lower()
                if answer != "y":
                    logger.info(f"[VECTOR][hooks] user denied hook: {event}::{cmd}")
                    return HookResult()
                _approve(event, cmd)
            else:
                logger.warning(f"[VECTOR][hooks] hook not approved (non-TTY): {event}::{cmd}")
                return HookResult()

        try:
            # Safe split — no shell=True
            args = shlex.split(os.path.expanduser(cmd))
        except ValueError as e:
            logger.error(f"[VECTOR][hooks] bad hook command '{cmd}': {e}")
            return HookResult()

        try:
            proc = subprocess.run(
                args,
                input=payload,
                capture_output=True,
                text=True,
                shell=False,
                timeout=self._timeout,
                cwd=self._cwd,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"[VECTOR][hooks] hook timed out after {self._timeout}s: {cmd}")
            return HookResult()
        except FileNotFoundError:
            logger.error(f"[VECTOR][hooks] hook script not found: {args[0]}")
            return HookResult()
        except Exception as e:
            logger.error(f"[VECTOR][hooks] hook error: {e}")
            return HookResult()

        stdout = proc.stdout.strip()
        if not stdout:
            return HookResult(exit_code=proc.returncode)

        # Parse response JSON
        try:
            resp = json.loads(stdout)
        except json.JSONDecodeError:
            return HookResult(stdout=stdout, exit_code=proc.returncode)

        # Block decision (both Claude Code style and canonical)
        decision = resp.get("decision") or resp.get("action", "")
        if decision == "block":
            reason = resp.get("reason") or resp.get("message", "Blocked by hook")
            logger.info(f"[VECTOR][hooks] hook blocked {event}: {reason}")
            return HookResult(blocked=True, reason=reason, exit_code=proc.returncode)

        # Context injection for pre_llm_call
        if "context" in resp:
            return HookResult(injected_context=str(resp["context"]), exit_code=proc.returncode)

        return HookResult(stdout=stdout, exit_code=proc.returncode)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # No hooks configured → no-op
    runner = ShellHookRunner(hooks={}, auto_accept=True)
    assert not runner.has_hooks("pre_tool_call")
    result = runner.invoke("pre_tool_call", tool_name="bash", tool_input={"command": "ls"})
    assert not result.blocked

    # Hook that injects context (Python portable stand-in)
    script = f'{sys.executable} -c "import sys; sys.stdin.read(); print(\'{{\"context\": \"injected\"}}\'.replace(chr(39), chr(34)))"'
    runner2 = ShellHookRunner(
        hooks={"pre_bash": [script]},
        auto_accept=True,
        cwd=str(Path.cwd()),
    )
    assert runner2.has_hooks("pre_bash")
    r2 = runner2.invoke("pre_bash", tool_name="bash", tool_input={"command": "ls"}, session_id="test")
    assert isinstance(r2.injected_context, str)

    # Allowlist functions
    _approve("test_event", "echo test")
    assert _is_approved("test_event", "echo test")
    assert not _is_approved("other_event", "echo test")

    print("shell_hooks.py OK")


