"""
migrate_osgetenv.py — Replace os.getenv( with os.environ.get( in vectorcode/src/

os.environ.get(key, default) is identical to os.getenv(key, default) per Python docs.
This centralises awareness that env reads should go through vc_env.py in future.

Usage:
    python scripts/migrate_osgetenv.py [--dry-run]
"""
from __future__ import annotations

import re
import sys
import pathlib
import argparse

ROOT = pathlib.Path(__file__).parent.parent
TARGET = ROOT / "vectorcode" / "src"

_PATTERN = re.compile(r"\bos\.getenv\(")
_REPLACEMENT = "os.environ.get("


def migrate_file(path: pathlib.Path, dry_run: bool) -> int:
    """Return number of replacements made."""
    try:
        original = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0

    if "os.getenv(" not in original:
        return 0

    updated = _PATTERN.sub(_REPLACEMENT, original)
    count = len(_PATTERN.findall(original))

    if not dry_run and updated != original:
        path.write_text(updated, encoding="utf-8")

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace os.getenv with os.environ.get in vectorcode/src/")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    if not TARGET.exists():
        print(f"ERROR: {TARGET} does not exist")
        sys.exit(1)

    total = 0
    files_changed = 0
    for py_file in sorted(TARGET.rglob("*.py")):
        count = migrate_file(py_file, args.dry_run)
        if count:
            rel = py_file.relative_to(ROOT)
            print(f"  {'[DRY]' if args.dry_run else '[OK ]'}  {count:3d}  {rel}")
            total += count
            files_changed += 1

    verb = "Would replace" if args.dry_run else "Replaced"
    print(f"\n{verb} {total} os.getenv( calls in {files_changed} files")


if __name__ == "__main__":
    main()
