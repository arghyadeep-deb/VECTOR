"""Strip all remaining VectorCode branding from the VECTOR codebase.

Replaces every trace of "vector" / "VectorCode" / "VECTOR" across
all files so the codebase reads as purely VECTOR. Skips .git, __pycache__,
venv, node_modules, and binary/image file types.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# File extensions to process
EXTENSIONS = {".py", ".md", ".yml", ".yaml", ".toml", ".cfg", ".txt",
              ".ps1", ".sh", ".bat", ".json", ".html", ".js", ".tsx",
              ".ts", ".css", ".ini", ".lock"}

# Directories to exclude
EXCLUDE = {".git", "__pycache__", ".venv", "venv", "node_modules",
           ".pytest_cache", ".gstack", ".agents", ".mypy_cache",
           ".ruff_cache", ".cursor", ".claude"}

# Tiered replacements — ordered from longest prefix to shortest so regex
# doesn't clip partial matches.
REPLACEMENTS: list[tuple[str, str]] = [
    # Source header line (entirely)
    (r"^# Source: github/vector/VectorCode/src/vector/.*$",
     "# VECTOR module — ported from VectorCode"),
    (r"^# Source: github/vector/VectorCode/src/vector",
     "# VECTOR module — ported from VectorCode"),

    # Protocol URLs
    (r"vector://", "vector://"),

    # Output sentinels
    (r"---VECTOR_OUTPUT_START---", "---VECTOR_OUTPUT_START---"),
    (r"---VECTOR_OUTPUT_END---", "---VECTOR_OUTPUT_END---"),

    # Env vars and constants
    (r"VECTOR_CONFIG", "VECTOR_CONFIG"),
    (r"VECTOR_SKIP_VERSION_CHECK", "VECTOR_SKIP_VERSION_CHECK"),
    (r"VECTOR_SKIP_FIRST_RUN", "VECTOR_SKIP_FIRST_RUN"),

    # Config dir paths
    (r"\.vector", ".vector"),

    # Runner / container names
    (r"vector-pearl-miner", "vector-pearl-miner"),
    (r"vector_twitter_bot", "vector_twitter_bot"),

    # Function / var names
    (r"_vector_home\b", "_vector_home"),

    # Function / var names (no word boundary — underscore is a word char)
    (r"vector_commit\b", "vector_commit"),
    (r"vector_home\b", "vector_home"),
    (r"vector_", "vector_"),

    # Bare branding (case variants)
    (r"VectorCode", "VectorCode"),
    (r"VECTOR", "VECTOR"),
    (r"vector", "vector"),
    (r"vector", "vector"),
    (r"vector", "vector"),

    # App names in docstrings
    (r"VectorCode \(OJ\)", "VECTOR"),
]

# Pre-compile with MULTILINE and IGNORECASE where appropriate
_COMPILED: list[tuple[re.Pattern, str]] = []
for pat, repl in REPLACEMENTS:
    flags = re.MULTILINE
    # Case-sensitive patterns
    if pat.startswith(r"vector://"):
        flags |= re.IGNORECASE
    elif pat == r"\bvector\b":
        flags |= re.IGNORECASE
    elif pat == "vector":
        flags |= re.IGNORECASE
    elif pat == "vector":
        pass  # already exact case
    _COMPILED.append((re.compile(pat, flags), repl))


def strip_file(path: Path) -> int:
    """Strip branding from *path*.  Returns number of replacements made."""
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            original = path.read_text(encoding="latin-1")
        except Exception:
            return 0

    changed = 0
    text = original
    for pat, repl in _COMPILED:
        new_text = pat.sub(repl, text)
        if new_text != text:
            changed += 1
            text = new_text

    if changed:
        path.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    total_files = 0
    total_changes = 0

    for f in sorted(ROOT.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() not in EXTENSIONS:
            continue
        # Check exclusion
        if any(part in EXCLUDE for part in f.parts):
            continue
        n = strip_file(f)
        if n:
            total_files += 1
            total_changes += n
            print(f"  {f.relative_to(ROOT)} — {n} patterns matched")

    print(f"\n{total_files} files changed, {total_changes} total replacements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
