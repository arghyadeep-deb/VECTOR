"""Fix all 'from vector.X' / 'import vector.X' imports across absorbed
VectorCode modules. The original absorb script had a regex bug — `^from vector`
only matched start-of-line, missing indented imports inside try blocks.

This pass uses a fully whitespace-aware regex and applies the same redirection
logic the absorber should have used.

Run:
    cd 'C:\\Users\\Arghyadeep\\Desktop\\V.E.C.T.O.R\\V.E.C.T.O.R. Codebase'
    python scripts/fix_oj_imports.py            # dry run
    python scripts/fix_oj_imports.py --apply    # actually rewrite
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Same maps as the absorb script
COLLIDING = {
    "core", "agents", "tools", "engine", "system", "mcp", "security",
    "templates", "traces", "skills", "memory", "providers",
}
CORE_MODULES = {"telemetry", "sandbox", "scheduler"}

# Directories to scan
SCAN_DIRS = [
    ROOT / "vectorcode" / "src",
    ROOT / "core",
]


def redirect(name: str) -> str:
    if name in COLLIDING:
        return f"vectorcode.src.oj_{name}"
    if name in CORE_MODULES:
        return f"core.{name}"
    return f"vectorcode.src.{name}"


# Match indented OR top-level imports
_RE_FROM = re.compile(r"^(\s*)from vector\.([a-zA-Z_][a-zA-Z0-9_]*)", re.MULTILINE)
_RE_IMPORT = re.compile(r"^(\s*)import vector\.([a-zA-Z_][a-zA-Z0-9_]*)", re.MULTILINE)
_RE_FROM_BARE = re.compile(r"^(\s*)from vector(\s+import\s)", re.MULTILINE)
_RE_IMPORT_BARE = re.compile(r"^(\s*)import vector(\s|$)", re.MULTILINE)


def fix_file(path: Path) -> tuple[int, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return 0, ""

    original = text
    changes = 0

    def _from_repl(m: re.Match) -> str:
        nonlocal changes
        changes += 1
        return f"{m.group(1)}from {redirect(m.group(2))}"

    def _import_repl(m: re.Match) -> str:
        nonlocal changes
        changes += 1
        return f"{m.group(1)}import {redirect(m.group(2))}"

    text = _RE_FROM.sub(_from_repl, text)
    text = _RE_IMPORT.sub(_import_repl, text)

    def _from_bare_repl(m: re.Match) -> str:
        nonlocal changes
        changes += 1
        return f"{m.group(1)}from vectorcode.src{m.group(2)}"

    def _import_bare_repl(m: re.Match) -> str:
        nonlocal changes
        changes += 1
        return f"{m.group(1)}import vectorcode.src{m.group(2)}"

    text = _RE_FROM_BARE.sub(_from_bare_repl, text)
    text = _RE_IMPORT_BARE.sub(_import_bare_repl, text)

    return changes, text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    files_scanned = 0
    files_changed = 0
    total_changes = 0

    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            files_scanned += 1
            n, new_text = fix_file(f)
            if n > 0:
                files_changed += 1
                total_changes += n
                if args.apply:
                    f.write_text(new_text, encoding="utf-8")

    print(f"Scanned {files_scanned} .py files")
    print(f"Files {'changed' if args.apply else 'would change'}: {files_changed}")
    print(f"Total import lines {'rewritten' if args.apply else 'to rewrite'}: {total_changes}")
    if not args.apply:
        print("\n(dry run — re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
