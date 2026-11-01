"""Container-side entrypoint for VECTOR's isolated code sandbox (OD-59).

Protocol (matches core/sandbox/runner.py's ContainerRunner):
  stdin:  one JSON object {"cmd": [argv...], "timeout": <seconds>}
  stdout: the sentinel-wrapped JSON result ContainerRunner._parse_output()
          expects: ---VECTOR_OUTPUT_START---<json>---VECTOR_OUTPUT_END---

Runs entirely inside the container (--network none, read-only mounts via
ContainerRunner's own mount allowlist) -- this process never has to be
trusted, only its result is read back by the host.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

_OUTPUT_START = "---VECTOR_OUTPUT_START---"
_OUTPUT_END = "---VECTOR_OUTPUT_END---"

_MAX_OUTPUT_BYTES = 1_048_576


def _truncate(stdout: str, stderr: str) -> tuple[str, str, bool]:
    total = len(stdout) + len(stderr)
    if total <= _MAX_OUTPUT_BYTES:
        return stdout, stderr, False
    half = _MAX_OUTPUT_BYTES // 2
    return stdout[:half], stderr[:half] + "TRUNCATED", True


def main() -> None:
    result: dict = {}
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        cmd = payload.get("cmd")
        timeout = float(payload.get("timeout") or 30.0)

        if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
            result = {
                "content": "invalid payload: 'cmd' must be a non-empty list of strings",
                "error": True,
                "error_type": "protocol",
            }
        else:
            t0 = time.monotonic()
            timed_out = False
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                stderr = ((exc.stderr or "") if isinstance(exc.stderr, str) else "") + "TIMEOUT"
                exit_code = -1
            except Exception as exc:  # never let the container crash without a result
                stdout, stderr, exit_code, timed_out = "", f"{type(exc).__name__}: {exc}", -1, False

            elapsed = time.monotonic() - t0
            stdout, stderr, truncated = _truncate(stdout, stderr)
            result = {
                "success": exit_code == 0 and not timed_out,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "elapsed_secs": elapsed,
                "timed_out": timed_out,
                "truncated": truncated,
            }
    except Exception as exc:  # malformed input, json errors, anything else
        result = {
            "content": f"sandbox entrypoint failure: {type(exc).__name__}: {exc}",
            "error": True,
            "error_type": "entrypoint",
        }

    sys.stdout.write(_OUTPUT_START)
    sys.stdout.write(json.dumps(result))
    sys.stdout.write(_OUTPUT_END)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
