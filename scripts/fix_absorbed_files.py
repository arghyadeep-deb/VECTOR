"""
Fix encoding/import issues in all absorbed OpenJarvis files.
Run: python -X utf8 scripts/fix_absorbed_files.py
"""
import re
from pathlib import Path

DIRS = [
    Path("vectorcode/src/server"),
    Path("vectorcode/src/system"),
    Path("vectorcode/src/prompt"),
    Path("vectorcode/src/skills"),
    Path("core/mining"),
    Path("vectorcode/src/comms"),
]

EXTRA_FIXES = [
    # Channels import from openjarvis.core -> remapped to vectorcode.src.core but should be vc_core
    (r"from vectorcode\.src\.core\.", "from vectorcode.src.vc_core."),
    (r"import vectorcode\.src\.core\.", "import vectorcode.src.vc_core."),
]

CLEAN_HEADER = "# VECTOR-INGESTED MODULE (absorbed from open-jarvis/OpenJarvis, Apache 2.0)\n"

UNICODE_FIXES = {
    "—": "--",   # em dash
    "–": "-",    # en dash
    "→": "->",   # right arrow
    "←": "<-",   # left arrow
    "═": "=",    # double horizontal
    "’": "'",    # right single quote
    "‘": "'",    # left single quote
    "“": '"',    # left double quote
    "”": '"',    # right double quote
    "•": "*",    # bullet
    "é": "e",    # e with accent
    "è": "e",
    "à": "a",
}


def fix_file(f: Path) -> bool:
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  READ ERR {f.name}: {e}")
        return False

    original = text

    # 1. Fix unicode in comment/header lines
    lines = text.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if line.startswith("#"):
            for uni, asc in UNICODE_FIXES.items():
                line = line.replace(uni, asc)
        new_lines.append(line)
    text = "".join(new_lines)

    # 2. Remove all existing VECTOR-INGESTED markers (may be malformed)
    text = re.sub(r"# VECTOR-INGESTED MODULE[^\n]*\n", "", text)
    text = re.sub(r'"""VECTOR-INGESTED[^"]*"""\n', "", text)

    # 3. Apply extra import remaps
    for pat, rep in EXTRA_FIXES:
        text = re.sub(pat, rep, text)

    # 4. Re-insert clean header correctly (AFTER shebang and __future__ imports)
    lines = text.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (stripped.startswith("#") or
                stripped.startswith("from __future__") or
                stripped == ""):
            insert_at = i + 1
        else:
            break
    lines.insert(insert_at, CLEAN_HEADER)
    text = "".join(lines)

    if text != original:
        f.write_text(text, encoding="utf-8")
        return True
    return False


def main():
    fixed = skipped = errors = 0
    for d in DIRS:
        if not d.exists():
            print(f"  SKIP (no dir): {d}")
            continue
        for f in sorted(d.rglob("*.py")):
            try:
                if fix_file(f):
                    fixed += 1
                    print(f"  [OK] {f.relative_to(Path('.'))}")
                else:
                    skipped += 1
            except Exception as e:
                errors += 1
                print(f"  [ERR] {f.name}: {e}")

    print(f"\nDone: {fixed} fixed, {skipped} unchanged, {errors} errors")


if __name__ == "__main__":
    main()
