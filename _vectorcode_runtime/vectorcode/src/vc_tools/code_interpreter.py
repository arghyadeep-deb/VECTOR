# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Code interpreter tool — safe Python code execution in subprocess."""

from __future__ import annotations

import subprocess
import sys
import os
from typing import Any

from vectorcode.src.vc_core.registry import ToolRegistry
from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec

# FLAGGED for owner awareness, not fixed: this is a literal-substring
# blocklist on raw source text, trivially bypassed without any
# obfuscation -- e.g. `import importlib; importlib.import_module("os")
# .system(...)` contains neither "os.system" nor "subprocess." as a
# literal substring, nor does `getattr(__builtins__, "ex" + "ec")(...)`
# contain "exec(". A real fix is a sandboxed/restricted execution
# environment, not a narrow patch to this list -- the code's own comment
# already treats VECTOR_ENABLE_UNTRUSTED_CODE=1 + "isolated lab
# environment only" as the real security boundary, with this list as a
# cheap speed-bump on top, not the actual defense. Left as-is; whether
# that's an acceptable security posture is an owner decision.
# Dangerous patterns to block
_BLOCKED_PATTERNS = [
    "os.system",
    "os.popen",
    "subprocess.",
    "shutil.rmtree",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "__import__",
    "eval(",
    "exec(",
    "compile(",
    "open(",
]


def _untrusted_code_enabled() -> bool:
    return os.environ.get("VECTOR_ENABLE_UNTRUSTED_CODE", "").strip() == "1"

@ToolRegistry.register("code_interpreter")
class CodeInterpreterTool(BaseTool):
    """Execute Python code in an isolated subprocess."""

    tool_id = "code_interpreter"

    def __init__(self, timeout: int = 30, max_output: int = 10000):
        self._timeout = timeout
        self._max_output = max_output

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="code_interpreter",
            description=(
                "Execute Python code and return the output."
                " Code runs in an isolated subprocess."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute.",
                    },
                },
                "required": ["code"],
            },
            category="code",
        )

    def execute(self, **params: Any) -> ToolResult:
        code = params.get("code", "")
        if not _untrusted_code_enabled():
            return ToolResult(
                tool_name="code_interpreter",
                content=(
                    "Code execution is disabled by default. Set "
                    "VECTOR_ENABLE_UNTRUSTED_CODE=1 only in an isolated lab environment."
                ),
                success=False,
            )
        if not code:
            return ToolResult(
                tool_name="code_interpreter",
                content="No code provided.",
                success=False,
            )

        # Security check
        for pattern in _BLOCKED_PATTERNS:
            if pattern in code:
                return ToolResult(
                    tool_name="code_interpreter",
                    content=f"Blocked: code contains prohibited pattern '{pattern}'",
                    success=False,
                )

        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            output = result.stdout
            if result.stderr:
                output += ("\n" if output else "") + result.stderr
            if len(output) > self._max_output:
                output = output[: self._max_output] + "\n... (output truncated)"
            return ToolResult(
                tool_name="code_interpreter",
                content=output or "(no output)",
                success=result.returncode == 0,
                metadata={"returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="code_interpreter",
                content=f"Execution timed out after {self._timeout} seconds.",
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="code_interpreter",
                content=f"Execution error: {exc}",
                success=False,
            )

__all__ = ["CodeInterpreterTool"]
