#!/usr/bin/env python3
"""
scripts/baseline_test_results.py — Phase 0F snapshot.
Run before starting Phase 1 to capture the baseline pass/fail count.
Usage: python scripts/baseline_test_results.py
"""
import subprocess, sys, datetime, pathlib

result = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "--tb=no", "tests/"],
    capture_output=True, text=True,
    cwd=str(pathlib.Path(__file__).parent.parent),
)
out = result.stdout + result.stderr
ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
out_path = pathlib.Path(__file__).parent.parent / f"baseline_test_results_{ts}.txt"
out_path.write_text(out)
print(out[-500:])
print(f"\nBaseline saved to {out_path}")
