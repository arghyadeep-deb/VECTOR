"""
Fix remaining inline PRAGMA journal_mode=WAL + busy_timeout=5000 sites
in vectorcode/src/ and districts/investment/ by replacing with apply_pragmas().

Skips:
- vectorcode/src/vector_state.py  (custom WAL-fallback logic, must not touch)
- test_backup.py                  (intentionally tests WAL mode)

Handles variants:
  conn.execute("PRAGMA journal_mode=WAL")
  conn.execute("PRAGMA busy_timeout=5000")
  [optional: conn.execute("PRAGMA foreign_keys=ON")]
→ apply_pragmas(conn)  /  apply_pragmas(conn, foreign_keys=True)

Single WAL-only lines (no busy_timeout pair) are left alone — they are
either intentional one-off settings or part of larger custom logic.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_SUFFIXES = (
    "vector_state.py",
    "test_backup.py",
)

# Match the 2-line WAL+busy_timeout block, optionally followed by foreign_keys=ON.
# Uses named groups to capture indent and connection variable.
BLOCK_RE = re.compile(
    r'^(?P<indent>[ \t]*)(?P<conn>[\w.]+)\.execute\("PRAGMA journal_mode=WAL;?"\)\n'
    r'(?P=indent)(?P=conn)\.execute\("PRAGMA busy_timeout=5000;?"\)\n'
    r'(?:(?P=indent)(?P=conn)\.execute\("PRAGMA foreign_keys=ON;?"\)\n)?',
    re.MULTILINE,
)

IMPORT_LINE = "from core.memory.db_utils import apply_pragmas\n"


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    text = original

    matches = list(BLOCK_RE.finditer(text))
    if not matches:
        return False

    # Build replacement pieces (iterate in reverse to preserve offsets)
    for m in reversed(matches):
        indent = m.group("indent")
        conn = m.group("conn")
        has_fk = "foreign_keys=ON" in m.group(0)
        if has_fk:
            replacement = f'{indent}apply_pragmas({conn}, foreign_keys=True)\n'
        else:
            replacement = f'{indent}apply_pragmas({conn})\n'
        text = text[:m.start()] + replacement + text[m.end():]

    # Inject import if not already present
    if "from core.memory.db_utils import apply_pragmas" not in text:
        # Insert after the last stdlib/third-party import block
        lines = text.splitlines(keepends=True)
        insert_at = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                insert_at = i + 1
        lines.insert(insert_at, IMPORT_LINE)
        text = "".join(lines)

    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    root = Path(__file__).parent.parent
    search_roots = [root / "vectorcode" / "src", root / "districts" / "investment"]

    fixed = []
    skipped = []

    for search_root in search_roots:
        for py_file in sorted(search_root.rglob("*.py")):
            if any(py_file.name == s or py_file.name.endswith(s) for s in SKIP_SUFFIXES):
                skipped.append(py_file.relative_to(root))
                continue
            if fix_file(py_file):
                fixed.append(py_file.relative_to(root))

    print(f"Fixed {len(fixed)} files:")
    for f in fixed:
        print(f"  {f}")
    print(f"\nSkipped (intentional): {[str(s) for s in skipped]}")

    # Verify: no inline WAL lines remain (outside skipped files)
    remaining = []
    for search_root in search_roots:
        for py_file in sorted(search_root.rglob("*.py")):
            if any(py_file.name == s for s in SKIP_SUFFIXES):
                continue
            txt = py_file.read_text(encoding="utf-8", errors="ignore")
            lines = [i + 1 for i, l in enumerate(txt.splitlines())
                     if "PRAGMA journal_mode=WAL" in l and "apply_pragmas" not in l
                     and "#" not in l.split("PRAGMA")[0]]
            if lines:
                remaining.append((py_file.relative_to(root), lines))

    if remaining:
        print(f"\nWARNING: {len(remaining)} files still have inline WAL:")
        for f, lns in remaining:
            print(f"  {f}: lines {lns}")
        sys.exit(1)
    else:
        print("\nOK: 0 inline WAL lines remain in fixed scope.")


if __name__ == "__main__":
    main()
