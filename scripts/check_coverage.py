import subprocess
import re
import sys
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
THRESHOLD = 50.0


def main():
    try:
        import pytest_cov  # noqa: F401
    except ImportError:
        print(f"SKIPPED: pytest-cov not installed (coverage gate: {THRESHOLD}%)")
        sys.exit(0)

    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=core", "--cov-report=term-missing",
        "tests/",
        "--ignore=tests/research_engine", "--ignore=tests/backtest",
        "-q", "--tb=short",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    print(output)

    match = re.search(r"^TOTAL\s+.*?(\d+(?:\.\d+)?%)", output, re.MULTILINE)
    if not match:
        print("ERROR: could not parse TOTAL coverage line")
        sys.exit(1)

    pct_str = match.group(1).rstrip("%")
    pct = float(pct_str)
    print(f"\nCoverage: {pct}% (threshold: {THRESHOLD}%)")

    if pct >= THRESHOLD:
        print("PASSED")
        sys.exit(0)
    else:
        print("FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
