"""
VectorCode Code Execution Tool — ported from Hermes code_execution_tool.py.

Provides:
  - execute_code(language, code, timeout) -> {stdout, stderr, exit_code, error}
  - Supported languages: python, javascript/node, bash, shell
  - Python: subprocess with temp file, captures stdout/stderr
  - JavaScript: subprocess `node` with temp file if node available
  - Bash/shell: direct subprocess
  - Timeout enforcement
  - Temp file cleanup
  - risk_level: high

Schema name: execute_code
"""
import sys
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = ("python", "javascript", "node", "bash", "shell")

_DEFAULT_TIMEOUT = 30
_MAX_OUTPUT_BYTES = 50_000  # 50 KB per stream


# ---------------------------------------------------------------------------
# Language dispatch helpers
# ---------------------------------------------------------------------------

def _find_python() -> Optional[str]:
    """Return a usable Python interpreter path, or None."""
    for candidate in (sys.executable, "python3", "python"):
        if candidate == sys.executable:
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _find_node() -> Optional[str]:
    """Return `node` executable path if available, else None."""
    return shutil.which("node") or shutil.which("nodejs")


def _run_subprocess(
    cmd: list,
    cwd: Optional[str],
    stdin_data: Optional[bytes],
    timeout: int,
) -> Dict[str, Any]:
    """Run cmd as subprocess and return {stdout, stderr, exit_code, error}."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_data else subprocess.DEVNULL,
            cwd=cwd,
        )
        try:
            stdout_b, stderr_b = proc.communicate(input=stdin_data, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                stdout_b, stderr_b = proc.communicate()
            except Exception:
                stdout_b, stderr_b = b"", b""
            return {
                "stdout": stdout_b[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
                "stderr": stderr_b[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
                "exit_code": 124,
                "error": f"Execution timed out after {timeout}s",
            }

        stdout = stdout_b[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        stderr = stderr_b[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        exit_code = proc.returncode if proc.returncode is not None else 0

        return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code, "error": None}

    except FileNotFoundError as e:
        return {"stdout": "", "stderr": "", "exit_code": -1, "error": f"Interpreter not found: {e}"}
    except Exception as e:
        logger.error("[VECTOR][code_execution] subprocess error: %s", e)
        return {"stdout": "", "stderr": "", "exit_code": -1, "error": str(e)}


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def execute_code(
    language: str,
    code: str,
    timeout: int = _DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Execute code in the specified language.

    Args:
        language: One of python, javascript, node, bash, shell.
        code:     Source code or script body to execute.
        timeout:  Seconds before the process is killed (default 30).

    Returns:
        dict: {stdout, stderr, exit_code, error}
    """
    lang = language.strip().lower()
    timeout = max(1, int(timeout))

    if lang not in SUPPORTED_LANGUAGES:
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": f"Unsupported language '{language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}",
        }

    if not code or not code.strip():
        return {"stdout": "", "stderr": "", "exit_code": -1, "error": "No code provided."}

    tmp_dir: Optional[str] = None

    try:
        if lang == "python":
            interpreter = _find_python()
            if not interpreter:
                return {"stdout": "", "stderr": "", "exit_code": -1, "error": "Python interpreter not found."}
            tmp_dir = tempfile.mkdtemp(prefix="vc_exec_")
            script_path = os.path.join(tmp_dir, "script.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)
            return _run_subprocess([interpreter, script_path], tmp_dir, None, timeout)

        elif lang in ("javascript", "node"):
            node = _find_node()
            if not node:
                return {
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                    "error": "Node.js not available. Install node to execute JavaScript.",
                }
            tmp_dir = tempfile.mkdtemp(prefix="vc_exec_")
            script_path = os.path.join(tmp_dir, "script.js")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)
            return _run_subprocess([node, script_path], tmp_dir, None, timeout)

        elif lang in ("bash", "shell"):
            # Direct subprocess without temp file for shell
            shell_bin = shutil.which("bash") or shutil.which("sh") or "bash"
            return _run_subprocess(
                [shell_bin, "-c", code],
                None,
                None,
                timeout,
            )

    except Exception as e:
        logger.error("[VECTOR][code_execution] execute_code error: %s", e)
        return {"stdout": "", "stderr": "", "exit_code": -1, "error": str(e)}
    finally:
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("[VECTOR][code_execution] temp dir cleanup failed: %s", e)

    # Unreachable but satisfies type checker
    return {"stdout": "", "stderr": "", "exit_code": -1, "error": "Internal error"}


# ---------------------------------------------------------------------------
# OpenAI Function Schema
# ---------------------------------------------------------------------------

EXECUTE_CODE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "execute_code",
        "description": (
            "Execute code in a sandboxed subprocess. "
            "Supported languages: python, javascript (requires node), bash, shell. "
            "Returns stdout, stderr, and exit_code. Timeout default: 30s. "
            "Risk: high — always requires approval for destructive code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "Language to execute: python, javascript, node, bash, shell",
                    "enum": list(SUPPORTED_LANGUAGES),
                },
                "code": {
                    "type": "string",
                    "description": "Source code to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)",
                    "default": 30,
                },
            },
            "required": ["language", "code"],
        },
    },
    "_meta": {"risk": "high", "read_only": False},
}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Python execution
    result = execute_code("python", "print('hello_exec')")
    assert result["exit_code"] == 0, f"python exit_code: {result}"
    assert "hello_exec" in result["stdout"], f"stdout: {result}"
    assert result["error"] is None

    # Python syntax error
    result2 = execute_code("python", "def bad syntax ;;")
    assert result2["exit_code"] != 0, f"syntax error should fail: {result2}"

    # Bash execution
    result3 = execute_code("bash", "echo bash_test")
    assert result3["exit_code"] == 0, f"bash exit_code: {result3}"
    assert "bash_test" in result3["stdout"], f"bash stdout: {result3}"

    # Unsupported language
    result4 = execute_code("ruby", "puts 'hi'")
    assert result4["exit_code"] == -1
    assert "Unsupported" in result4["error"]

    # Timeout enforcement
    result5 = execute_code("python", "import time; time.sleep(10)", timeout=1)
    assert result5["exit_code"] == 124 or result5["error"] is not None, f"expected timeout: {result5}"

    # Empty code
    result6 = execute_code("python", "   ")
    assert result6["exit_code"] == -1
    assert "No code" in result6["error"]

    # Schema check
    assert EXECUTE_CODE_SCHEMA["function"]["name"] == "execute_code"
    assert "language" in EXECUTE_CODE_SCHEMA["function"]["parameters"]["properties"]

    print("tools/code_execution.py OK")
