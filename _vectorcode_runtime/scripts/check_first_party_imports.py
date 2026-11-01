"""Static check: every `from core.X import ...` / `from districts.X import ...`
(and bare `import core.X`) in first-party code must resolve to a real file or
package. Catches the exact bug class from the 2026-09-24 external review --
a typo'd or stale module path that a broad `except Exception` swallows
silently at runtime, so the feature just does nothing forever.

Scope: core/, districts/, hands/, phone_node/ -- excluding vendored trees
(anything with its own NOTICE.md marking it third-party) and __pycache__.

Usage: python scripts/check_first_party_imports.py
Exit code 0 = clean, 1 = broken imports found (prints each one).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ["core", "districts", "hands", "phone_node"]
FIRST_PARTY_PREFIXES = ("core.", "core", "districts.", "districts", "hands.", "hands")

# Known-broken imports in dead/unreachable code, triaged during the
# 2026-09-24 external review and deliberately left as-is pending an owner
# deletion decision (see docs/design/dead-code-deletion-plan-v2.md). Both
# are standalone `if __name__ == "__main__"` entry points never imported
# by any live code path -- confirmed via full-repo grep. Remove an entry
# here only alongside the actual fix or deletion, never to silence a new
# regression.
KNOWN_DEAD_IMPORTS = {
    "core/mining/vllm_pearl.py": {32, 33},
    "districts/investment/vector_hedgebot/cli.py": {174},
}


def _is_vendored(path: Path) -> bool:
    """A directory is vendored if it or an ancestor (up to repo root) has its
    own NOTICE.md marking it third-party -- the convention this repo already
    uses (see districts/intelligence/vector_social_sim/NOTICE.md etc.)."""
    cur = path if path.is_dir() else path.parent
    while cur != REPO_ROOT and REPO_ROOT in cur.parents:
        if (cur / "NOTICE.md").exists():
            return True
        cur = cur.parent
    return False


def _module_path_exists(dotted: str) -> bool:
    """Does `core.foo.bar` resolve to core/foo/bar.py or core/foo/bar/__init__.py?"""
    rel = Path(*dotted.split("."))
    return (REPO_ROOT / rel).with_suffix(".py").exists() or (REPO_ROOT / rel / "__init__.py").exists()


def _iter_first_party_files():
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _is_vendored(path):
                continue
            yield path


def _check_file(path: Path) -> list[str]:
    problems = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError as e:
        return [f"{path}: SyntaxError parsing file: {e}"]

    rel_key = path.relative_to(REPO_ROOT).as_posix()
    known_dead_lines = KNOWN_DEAD_IMPORTS.get(rel_key, set())

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import -- not in scope, resolves within its own package
            module = node.module or ""
            if not module.startswith(FIRST_PARTY_PREFIXES):
                continue
            if not _module_path_exists(module) and node.lineno not in known_dead_lines:
                problems.append(f"{path}:{node.lineno}: from {module} import ... -- module not found")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if not module.startswith(FIRST_PARTY_PREFIXES):
                    continue
                if not _module_path_exists(module) and node.lineno not in known_dead_lines:
                    problems.append(f"{path}:{node.lineno}: import {module} -- module not found")
    return problems


def main() -> int:
    all_problems: list[str] = []
    for path in _iter_first_party_files():
        all_problems.extend(_check_file(path))

    if all_problems:
        print(f"FAILED: {len(all_problems)} broken first-party import(s):\n")
        for p in sorted(all_problems):
            print(f"  {p}")
        return 1

    print("OK: all first-party imports resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
