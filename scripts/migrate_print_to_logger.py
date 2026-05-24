"""
migrate_print_to_logger.py — Replace print() with logger.info() in core/

Skips print() calls inside if __name__ == '__main__': blocks.
Ensures 'from loguru import logger' is present in modified files.

Usage:
    python scripts/migrate_print_to_logger.py [--dry-run]
"""
from __future__ import annotations

import ast
import re
import sys
import pathlib
import argparse

ROOT = pathlib.Path(__file__).parent.parent
TARGET = ROOT / "core"

_LOGGER_IMPORT = "from loguru import logger\n"


def get_main_block_lines(source: str) -> set[int]:
    """Return line numbers that are inside if __name__ == '__main__' blocks."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    main_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        lhs_is_name = isinstance(test.left, ast.Name) and test.left.id == "__name__"
        rhs_is_main = any(
            isinstance(c, ast.Constant) and c.value == "__main__"
            for c in test.comparators
        )
        if lhs_is_name and rhs_is_main:
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    main_lines.add(child.lineno)
    return main_lines


def _replace_print_line(line: str) -> str:
    """Replace leading print( with logger.info( on a single line."""
    stripped = line.lstrip()
    if not stripped.startswith("print("):
        return line
    indent = line[: len(line) - len(stripped)]
    # Extract everything after 'print(' up to but not including the trailing ')'
    inner_start = stripped.index("print(") + len("print(")
    # Find matching closing paren (handle nested parens)
    depth = 1
    i = inner_start
    while i < len(stripped) and depth > 0:
        if stripped[i] == "(":
            depth += 1
        elif stripped[i] == ")":
            depth -= 1
        i += 1
    inner = stripped[inner_start : i - 1]
    after = stripped[i:]
    # Rebuild as logger.info(...)
    return f"{indent}logger.info({inner}){after}\n" if line.endswith("\n") else f"{indent}logger.info({inner}){after}"


def migrate_file(path: pathlib.Path, dry_run: bool) -> int:
    """Return number of print() calls replaced."""
    try:
        original = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0

    if "print(" not in original:
        return 0

    main_lines = get_main_block_lines(original)
    lines = original.splitlines(keepends=True)
    count = 0
    new_lines = []

    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if (
            i not in main_lines
            and stripped.startswith("print(")
            and not stripped.startswith("#")
        ):
            new_line = _replace_print_line(line)
            new_lines.append(new_line)
            count += 1
        else:
            new_lines.append(line)

    if count == 0:
        return 0

    updated = "".join(new_lines)

    # Ensure logger is imported
    if "from loguru import logger" not in updated and "import logger" not in updated:
        # Insert after the last import block line or at top after docstring
        insert_pos = 0
        in_docstring = False
        for i, line in enumerate(new_lines):
            stripped_l = line.strip()
            if i == 0 and stripped_l.startswith('"""'):
                in_docstring = True
            if in_docstring:
                if stripped_l.endswith('"""') and i > 0:
                    in_docstring = False
                    insert_pos = i + 1
                continue
            if stripped_l.startswith("import ") or stripped_l.startswith("from "):
                insert_pos = i + 1

        new_lines.insert(insert_pos, _LOGGER_IMPORT)
        updated = "".join(new_lines)

    if not dry_run and updated != original:
        path.write_text(updated, encoding="utf-8")

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replace print() with logger.info() in core/ (outside __main__ blocks)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
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
            print(f"  {'[DRY]' if args.dry_run else '[OK ]'}  {count:2d}  {rel}")
            total += count
            files_changed += 1

    verb = "Would replace" if args.dry_run else "Replaced"
    print(f"\n{verb} {total} print() calls in {files_changed} files")


if __name__ == "__main__":
    main()
