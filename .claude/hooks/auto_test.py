#!/usr/bin/env python3
"""
VECTOR Auto-Test Hook — Stop
Runs a fast smoke subset of tests after every session. Non-blocking, never exits 2.
Full suite is too slow for a stop hook — run manually: python -m pytest tests/ -q
"""
import subprocess
import sys
import os
from pathlib import Path

# Force UTF-8 output so emoji/unicode don't crash on Windows CP1252
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Only run if tests/ directory exists
if not Path("tests").exists():
    sys.exit(0)

# Run only the fast smoke tests — full suite takes >2 min and will timeout
FAST_TESTS = [
    "tests/test_voice_cloning.py",
    "tests/test_collections.py",
]
# Filter to tests that actually exist
targets = [t for t in FAST_TESTS if Path(t).exists()]
if not targets:
    sys.exit(0)

try:
    result = subprocess.run(
        ["python", "-m", "pytest", *targets, "-q", "--tb=short", "--no-header", "--timeout=30"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    output = (result.stdout + result.stderr).strip()
    if output:
        print(f"[VECTOR TESTS]\n{output[-800:]}")
    if result.returncode == 0:
        print("[VECTOR TESTS] OK - fast smoke passed")
    else:
        print("[VECTOR TESTS] FAIL - fix before marking district done")
except FileNotFoundError:
    pass
except subprocess.TimeoutExpired:
    print("[VECTOR TESTS] TIMEOUT - fast smoke took >90s (something is hanging)")
except Exception as e:
    print(f"[VECTOR TESTS] hook error: {e}")

sys.exit(0)
