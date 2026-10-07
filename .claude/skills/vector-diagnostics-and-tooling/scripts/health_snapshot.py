"""VECTOR health snapshot — one command, machine-readable pass/fail lines.

Prints OK/FAIL for: Python+torch+CUDA, config load, memory-DB size. Kept
dependency-light on purpose so it runs even on a half-set-up box. Part of the
vector-diagnostics-and-tooling skill.

Usage:  python .claude/skills/vector-diagnostics-and-tooling/scripts/health_snapshot.py
"""
import os
import subprocess
import sys
from pathlib import Path

# Repo root = four parents up from this file (.claude/skills/<name>/scripts/).
ROOT = Path(__file__).resolve().parents[4]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def line(ok: bool, label: str, detail: str = "") -> None:
    print(f"{'OK  ' if ok else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")


def check_smoke_tests() -> tuple[bool, str]:
    """Run the repository smoke gate and return its machine-readable status."""
    smoke_script = ROOT / "scripts" / "smoke_test.py"
    try:
        result = subprocess.run(
            [sys.executable, str(smoke_script)],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=ROOT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"execution failed: {exc}"
    output = (result.stdout or result.stderr).strip()
    detail = output.splitlines()[-1] if output else f"exit code {result.returncode}"
    return result.returncode == 0, detail


def main() -> bool:
    all_ok = True

    # 1. Python + torch + CUDA
    try:
        import torch  # noqa
        cuda = torch.cuda.is_available()
        line(True, "python", sys.version.split()[0])
        line(cuda, "torch/cuda", f"{torch.__version__} cuda={cuda}")
        all_ok = all_ok and cuda
    except Exception as e:  # torch optional on a bare box
        line(False, "torch", f"import failed: {e}")
        all_ok = False

    # 2. Config loads
    try:
        from core.config import CONFIG  # noqa
        line(True, "config", "core.config.CONFIG loaded")
    except Exception as e:
        line(False, "config", f"load failed: {e}")
        all_ok = False

    # 3. Memory DB size (watch for GB-scale bloat)
    db = ROOT / "vector_memory.db"
    if db.exists():
        mb = db.stat().st_size / (1024 * 1024)
        bloated = mb > 1024  # >1GB is the known-bad signal
        line(not bloated, "memory_db", f"{mb:.0f}MB{' (BLOAT — see debugging-playbook)' if bloated else ''}")
        all_ok = all_ok and not bloated
    else:
        line(True, "memory_db", "absent (VECTOR not yet run — expected on a fresh box)")

    # 4. Repository smoke gate advertised by the diagnostic skill.
    smoke_ok, smoke_detail = check_smoke_tests()
    line(smoke_ok, "smoke", smoke_detail)
    all_ok = all_ok and smoke_ok

    print("SNAPSHOT:", "OK" if all_ok else "DEGRADED")
    return all_ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
