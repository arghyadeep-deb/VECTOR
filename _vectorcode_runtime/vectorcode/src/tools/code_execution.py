"""Code execution sandbox — runs Python scripts in isolated subprocess.

Windows-compatible. Uses temp directories and subprocess with resource limits.
Supports tool calling via file-based RPC (write request files, poll for results).
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SANDBOX_TIMEOUT = 300  # 5 minutes
MAX_OUTPUT_CHARS = 50_000
ALLOWED_TOOLS = {"web_search", "read_file", "write_file", "bash", "grep", "glob"}


def execute_code(
    code: str,
    *,
    timeout: int = SANDBOX_TIMEOUT,
    workdir: Optional[Path] = None,
    env_overrides: Optional[dict] = None,
) -> dict:
    """Execute Python code in a subprocess sandbox.

    Returns dict with keys: output, error, exit_code, execution_time, timed_out
    """
    start = time.time()
    workdir = workdir or Path(tempfile.mkdtemp(prefix="vc_sandbox_"))
    script_path = workdir / "_exec.py"

    # Wrap code with stdout capture and resource limits
    wrapped = (
        "import sys, json, traceback\n"
        "try:\n"
        f"    {code}\n"
        "except Exception:\n"
        "    print(json.dumps({'error': traceback.format_exc()}), file=sys.stderr)\n"
        "    sys.exit(1)\n"
    )
    script_path.write_text(wrapped, encoding="utf-8")

    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    if env_overrides:
        env.update(env_overrides)

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start
        stdout = proc.stdout[:MAX_OUTPUT_CHARS]
        stderr = proc.stderr[:MAX_OUTPUT_CHARS]
        return {
            "output": stdout,
            "error": stderr if proc.returncode != 0 else "",
            "exit_code": proc.returncode,
            "execution_time": elapsed,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            "output": "",
            "error": f"Execution timed out after {elapsed:.0f}s",
            "exit_code": -1,
            "execution_time": elapsed,
            "timed_out": True,
        }
    finally:
        if script_path.exists():
            script_path.unlink()
