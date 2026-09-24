"""Local/CI code health gate for VECTOR runtime-critical checks."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = ("core", "districts", "phone_node", "vectorcode/src")
FOCUSED_TESTS = (
    "tests/backend/test_multi_db_mesh.py",
    "tests/backend/test_quarantine.py",
    "tests/backend/test_memory_concurrency_safety.py",
    "tests/backend/test_production_honesty.py",
)


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def _iter_runtime_py() -> list[Path]:
    files: list[Path] = []
    for root_name in RUNTIME_ROOTS:
        root = ROOT / root_name
        if root.exists():
            files.extend(
                path
                for path in root.rglob("*.py")
                if not any(part in {".git", ".venv", "__pycache__"} for part in path.parts)
            )
    files.append(ROOT / "run_vector.py")
    return sorted(path for path in files if path.exists())


def _check_compile() -> None:
    errors: list[str] = []
    for path in _iter_runtime_py():
        try:
            compile(path.read_text(encoding="utf-8-sig", errors="ignore"), str(path), "exec")
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
    if errors:
        raise SystemExit("Syntax errors:\n" + "\n".join(errors[:50]))


def _check_no_runtime_silent_swallows() -> None:
    hits: list[str] = []
    for path in _iter_runtime_py():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="ignore"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ExceptHandler)
                and isinstance(node.type, ast.Name)
                and node.type.id == "Exception"
                and len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)
            ):
                hits.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    if hits:
        raise SystemExit("Silent runtime exception swallows found:\n" + "\n".join(hits[:50]))


def _check_repo_hygiene() -> None:
    """Fail if a tracked file is a secret or generated runtime artifact (core.repo_hygiene)."""
    sys.path.insert(0, str(ROOT))
    from core.repo_hygiene import audit_repo_paths

    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    findings = audit_repo_paths(tracked)
    if findings:
        raise SystemExit("Repo hygiene findings in tracked files:" + chr(10) + chr(10).join(
            f"{f.severity}/{f.category}: {f.path} ({f.reason})" for f in findings[:50]))


def main() -> int:
    _check_compile()
    _check_repo_hygiene()
    _check_no_runtime_silent_swallows()
    # 2026-09-24 (external review, Phase 1): catches the exact bug class
    # found this pass -- a typo'd/stale first-party import path silently
    # swallowed by a broad except, so the feature just does nothing.
    _run([sys.executable, "scripts/check_first_party_imports.py"])
    _run([sys.executable, "run_vector.py", "readiness-check"])
    _run([sys.executable, "-m", "pytest", "-q", *FOCUSED_TESTS])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
