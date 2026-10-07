# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/auto_test.py

#!/usr/bin/env python3
"""
VECTOR Auto-Test Hook — Stop
Runs pytest after every session ends. Non-blocking — prints results, never exits 2.
Adapted from article's "auto deploy" — VECTOR doesn't use Vercel.
"""
# --- Windows console UTF-8 safety (VECTOR codemod) ---
import sys as _vsys  # noqa: E402
for _vstream in (_vsys.stdout, _vsys.stderr):
    try:
        if _vstream is not None and hasattr(_vstream, "reconfigure") and (getattr(_vstream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
            _vstream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
# ---------------------------------------------------------------------------

from loguru import logger
import subprocess
import sys
from pathlib import Path

# Only run if tests/ directory exists
if not Path("tests").exists():
    sys.exit(0)

try:
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/", "-q", "--tb=short", "--no-header", "-x"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (result.stdout + result.stderr).strip()
    if output:
        # Trim to last 800 chars to avoid flooding
        print(f"[VECTOR TESTS]\n{output[-800:]}")
    if result.returncode == 0:
        print("[VECTOR TESTS] ✅ All passing")
    else:
        print("[VECTOR TESTS] ❌ Failures — fix before marking district done")
except FileNotFoundError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")
except subprocess.TimeoutExpired:
    print("[VECTOR TESTS] ⚠️ Timeout — tests took >2 min")
except Exception:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

sys.exit(0)
