#!/usr/bin/env python3
"""
scripts/baseline_test_results.py — Phase 0F snapshot.
Run before starting Phase 1 to capture the baseline pass/fail count.
Usage: python scripts/baseline_test_results.py
"""
import os
import subprocess, sys, datetime, pathlib, tempfile

result = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "--tb=no", "tests/"],
    capture_output=True, text=True,
    cwd=str(pathlib.Path(__file__).parent.parent),
)
out = result.stdout + result.stderr
ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
out_path = pathlib.Path(__file__).parent.parent / f"baseline_test_results_{ts}.txt"
with tempfile.NamedTemporaryFile(
    mode="w", encoding="utf-8", dir=out_path.parent,
    prefix=f".{out_path.name}.", suffix=".tmp", delete=False,
) as output:
    tmp_path = pathlib.Path(output.name)
    output.write(out)
    output.flush()
    os.fsync(output.fileno())
os.replace(tmp_path, out_path)
print(out[-500:])
print(f"\nBaseline saved to {out_path}")
raise SystemExit(result.returncode)
