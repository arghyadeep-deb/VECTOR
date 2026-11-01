import re
import sys
import os
import stat
import time
import shutil
import subprocess
from pathlib import Path

from run_pytest_shards import SHARDS

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# This is a smoke coverage floor for the stable CI shard set, not a claim that
# VECTOR has production-grade whole-repo coverage yet.
THRESHOLD = float(os.environ.get("VECTOR_COVERAGE_THRESHOLD", "25.0"))
DEFAULT_SHARDS = ("backend-c", "frontend-core", "systems")


def _coverage_paths() -> list[str]:
    raw = os.environ.get("VECTOR_COVERAGE_SHARDS", ",".join(DEFAULT_SHARDS))
    names = [part.strip() for part in raw.split(",") if part.strip()]
    paths: list[str] = []
    for name in names:
        if name not in SHARDS:
            raise SystemExit(f"ERROR: unknown coverage shard {name!r}")
        paths.extend(SHARDS[name])

    seen: set[str] = set()
    unique = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _on_rm_error(func, path, _exc):
    """rmtree onexc handler: clear the read-only bit and retry (Windows).

    Windows refuses os.rmdir/os.remove on read-only files (TLS keys, secret
    fixtures), which is what previously left a half-deleted basetemp behind.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _fresh_basetemp() -> Path:
    """A unique, repo-local pytest basetemp for this run.

    Reusing a single fixed basetemp (`test_tmp/coverage`) was the root cause of
    the WinError 5 cascade: a read-only/locked leftover from the prior run made
    pytest's start-of-run rmtree of that path fail on Windows, leaving the dir
    half-deleted so every later tmp_path fixture errored at setup. A unique path
    per run is never pre-populated, so pytest never has to delete a locked dir.
    Stale `coverage_*` dirs from earlier runs are best-effort cleaned here with a
    read-only-aware rmtree so test_tmp/ does not grow without bound.
    """
    root = Path("test_tmp")
    root.mkdir(parents=True, exist_ok=True)
    for stale in root.glob("coverage_*"):
        if stale.is_dir():
            shutil.rmtree(stale, onexc=_on_rm_error)
    # Legacy fixed dir, if present from before this fix.
    legacy = root / "coverage"
    if legacy.exists():
        shutil.rmtree(legacy, onexc=_on_rm_error)
    return root / f"coverage_{os.getpid()}_{int(time.time())}"


def main():
    try:
        import pytest_cov  # noqa: F401
    except ImportError:
        print(f"SKIPPED: pytest-cov not installed (coverage gate: {THRESHOLD}%)")
        sys.exit(0)

    basetemp = _fresh_basetemp()
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=core", "--cov-report=term-missing",
        f"--cov-fail-under={THRESHOLD}",
        "--basetemp=" + str(basetemp),
        *_coverage_paths(),
        "-q", "--tb=short", "--timeout=60",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    print(output)

    # Best-effort cleanup of this run's basetemp (read-only-aware).
    if basetemp.exists():
        shutil.rmtree(basetemp, onexc=_on_rm_error)

    match = re.search(r"^TOTAL\s+.*?(\d+(?:\.\d+)?%)", output, re.MULTILINE)
    if not match:
        print("ERROR: could not parse TOTAL coverage line")
        sys.exit(1)

    pct_str = match.group(1).rstrip("%")
    pct = float(pct_str)
    print(f"\nCoverage: {pct}% (threshold: {THRESHOLD}%)")

    if pct < THRESHOLD:
        print("FAILED: coverage below threshold")
        sys.exit(1)

    # Coverage is fine — but do NOT report PASSED if pytest itself reported any
    # test failures or collection/setup errors. The previous version gated on
    # coverage % only, so a green "PASSED" could hide real test errors (e.g. a
    # hung test cascading ERRORs across the suite). pytest exits non-zero on any
    # failure or error; --cov-fail-under can't have triggered it here because
    # coverage already passed above.
    if result.returncode != 0:
        print(
            f"FAILED: coverage met ({pct}%) but pytest exited {result.returncode} "
            "— test failures or collection/setup errors are present (see output above)."
        )
        sys.exit(1)

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
