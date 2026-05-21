# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/hooks/auto_test.py

#!/usr/bin/env python3
"""
VECTOR Auto-Test Hook — Stop
Runs pytest after every session ends. Non-blocking — prints results, never exits 2.
Adapted from article's "auto deploy" — VECTOR doesn't use Vercel.
"""
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
    logger.debug("[VECTOR] suppressed exception", exc_info=True)
except subprocess.TimeoutExpired:
    print("[VECTOR TESTS] ⚠️ Timeout — tests took >2 min")
except Exception:
    logger.debug("[VECTOR] suppressed exception", exc_info=True)

sys.exit(0)
