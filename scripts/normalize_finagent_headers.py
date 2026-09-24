"""Replace the inaccurate 3-line 'Copyright VECTOR / MIT / rebranded URL' header in
districts/investment/vector_finagent/**/*.py with an honest derived-from credit.

Comment-only and idempotent. Every file is compiled before and after; a file whose
compiled bytecode would change (or that fails to compile) is left untouched.
Usage: python scripts/normalize_finagent_headers.py [--dry-run]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "districts" / "investment" / "vector_finagent"

OLD = (
    "# Copyright (c) 2024-2026 VECTOR. All rights reserved.\n"
    "# Licensed under the MIT License.\n"
    "# https://github.com/Fincept-Corporation/VectorFinancialTerminal\n"
)
OLD_NO_URL = OLD.rsplit("# https://", 1)[0]  # variant without the rebranded URL line
NEW = (
    "# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.\n"
    "# Adapted for VECTOR (owner's personal-use build).\n"
)


def normalize(text: str) -> str:
    """Return text with the old block replaced; line endings are preserved."""
    crlf = "\r\n" in text
    body = text.replace("\r\n", "\n")
    if OLD not in body and OLD_NO_URL not in body:
        return text
    body = body.replace(OLD, NEW).replace(OLD_NO_URL, NEW)
    return body.replace("\n", "\r\n") if crlf else body


def _same_code(before: str, after: str, name: str) -> bool:
    try:
        return compile(before, name, "exec").co_code == compile(after, name, "exec").co_code
    except SyntaxError:
        return False


def main(dry_run: bool = False) -> tuple[int, int]:
    changed = skipped = 0
    for path in sorted(ROOT.rglob("*.py")):
        try:
            raw = path.read_bytes().decode("utf-8")  # strict: never rewrite files we cannot round-trip
        except UnicodeDecodeError:
            skipped += 1
            continue
        new = normalize(raw)
        if new == raw:
            continue
        if not _same_code(raw, new, str(path)):
            skipped += 1
            continue
        if not dry_run:
            path.write_bytes(new.encode("utf-8"))
        changed += 1
    return changed, skipped


if __name__ == "__main__":
    c, s = main("--dry-run" in sys.argv)
    print(f"changed={c} skipped={s}")
