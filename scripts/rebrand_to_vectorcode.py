"""Rebrand VectorCode codebase: strip Hermes/Ruflo branding, replace with VectorCode.

Two-phase approach:
  Phase A: In-file string replacements across all .py, .md, .yaml, .json, .toml, .txt
  Phase B: Rename hermes_cli/ directory and other branded directories

Identifier rules (precedence top→bottom):
  hermes-agent          → vectorcode
  Hermes Agent          → VectorCode
  HermesAgent           → VectorCode
  hermes_cli            → vector_cli
  hermes_constants      → vector_constants
  hermes_state          → vector_state
  hermes_logging        → vector_logging
  hermes_time           → vector_time
  HERMES_HOME           → VECTOR_HOME
  HERMES_               → VECTOR_  (other env vars like HERMES_TIMEZONE, etc.)
  ~/.hermes             → ~/.vectorcode
  .hermes/              → .vectorcode/
  hermes:               → vectorcode:
  hermes-               → vectorcode-
  Hermes                → VectorCode
  hermes                → vector
  RuvnetRuflo / Ruflo   → VectorCode
  ruflo-                → vectorcode-
  ruflo                 → vector  (only in identifiers, not in `ruflo/` path itself)
  RUFLO_                → VECTOR_
"""
import re
import shutil
from pathlib import Path

VC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode")

# Order matters — apply most specific patterns first.
REPLACEMENTS = [
    # Compound product names
    ("hermes-agent",        "vectorcode"),
    ("Hermes Agent",        "VectorCode"),
    ("Hermes-Agent",        "VectorCode"),
    ("HermesAgent",         "VectorCode"),
    ("HermesACPAgent",      "VectorCodeACPAgent"),

    # Module names (must come BEFORE generic 'hermes' replacement)
    ("hermes_cli",          "vector_cli"),
    ("hermes_constants",    "vector_constants"),
    ("hermes_state",        "vector_state"),
    ("hermes_logging",      "vector_logging"),
    ("hermes_time",         "vector_time"),

    # Env vars
    ("HERMES_HOME",         "VECTOR_HOME"),
    ("HERMES_PROFILE",      "VECTOR_PROFILE"),
    ("HERMES_TIMEZONE",     "VECTOR_TIMEZONE"),
    ("HERMES_LOG",          "VECTOR_LOG"),
    ("HERMES_DEBUG",        "VECTOR_DEBUG"),
    ("HERMES_CONFIG",       "VECTOR_CONFIG"),
    ("HERMES_API_KEY",      "VECTOR_API_KEY"),
    ("HERMES_WRITE_SAFE_ROOT", "VECTOR_WRITE_SAFE_ROOT"),

    # Paths
    ("~/.hermes",           "~/.vectorcode"),
    ("/.hermes/",           "/.vectorcode/"),
    (".hermes/",            ".vectorcode/"),

    # Generic env-var prefix (catch any HERMES_FOO not handled above)
    ("HERMES_",             "VECTOR_"),

    # Title case standalone "Hermes"
    ("Hermes",              "VectorCode"),
    # Lowercase standalone hermes (use word boundary via regex below)

    # Ruflo
    ("ruvnet/ruflo",        "vectorcode"),
    ("Ruflo",               "VectorCode"),
    ("RUFLO_",              "VECTOR_"),
]

# Lowercase replacements with word-boundary protection
WORD_BOUNDARY_REPLACEMENTS = [
    ("hermes",              "vector"),
    ("ruflo",               "vector"),
]

# Files we should NOT rebrand (they identify external services / refs)
SKIP_FILES = {
    "bulk_absorb_hermes.py",  # the absorb script itself
    "bulk_absorb_ruflo.py",
    "rebrand_to_vectorcode.py",
}

# Skip these directories entirely
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "dist", ".pytest_cache",
             "absorption"}  # absorption plan docs reference Hermes/Ruflo by name intentionally

# File extensions to process
ALLOWED_EXT = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".sh",
               ".ts", ".tsx", ".js", ".jsx", ".html", ".css"}

stats = {"files_changed": 0, "replacements": 0, "files_scanned": 0}


def transform_text(text: str) -> tuple[str, int]:
    """Apply all replacements. Return (new_text, count)."""
    count = 0
    new = text
    for old, new_repl in REPLACEMENTS:
        if old in new:
            n = new.count(old)
            new = new.replace(old, new_repl)
            count += n

    # Word-boundary lowercase replacements
    for old, new_repl in WORD_BOUNDARY_REPLACEMENTS:
        # Match `hermes` only when surrounded by non-alphanumeric (or boundaries)
        # but NOT inside identifiers like `hermes_xyz` (already handled above)
        pattern = r'\b' + re.escape(old) + r'\b'
        matches = list(re.finditer(pattern, new))
        if matches:
            count += len(matches)
            new = re.sub(pattern, new_repl, new)
    return new, count


def should_process(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return False
    if path.suffix.lower() not in ALLOWED_EXT:
        return False
    parts = path.parts
    if any(p in SKIP_DIRS for p in parts):
        return False
    if path.stat().st_size > 5 * 1024 * 1024:  # skip files > 5MB
        return False
    return True


def process_file(path: Path) -> None:
    stats["files_scanned"] += 1
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    new_text, count = transform_text(text)
    if count == 0:
        return
    path.write_text(new_text, encoding="utf-8")
    stats["files_changed"] += 1
    stats["replacements"] += count


# Phase A: in-file replacements
print("Phase A: in-file string replacements")
for path in VC.rglob("*"):
    if not path.is_file():
        continue
    if not should_process(path):
        continue
    process_file(path)

print(f"  Scanned:     {stats['files_scanned']} files")
print(f"  Changed:     {stats['files_changed']} files")
print(f"  Total swaps: {stats['replacements']}")

# Phase B: rename hermes_cli/ → vector_cli/
print()
print("Phase B: directory renames")
hermes_cli_dir = VC / "python" / "vectorcode" / "hermes_cli"
vector_cli_dir = VC / "python" / "vectorcode" / "vector_cli"
if hermes_cli_dir.exists():
    if vector_cli_dir.exists():
        # Merge — copy all from hermes_cli into vector_cli, then remove
        for item in hermes_cli_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(hermes_cli_dir)
                dst = vector_cli_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)
        shutil.rmtree(hermes_cli_dir)
        print("  Merged hermes_cli/ into existing vector_cli/")
    else:
        hermes_cli_dir.rename(vector_cli_dir)
        print("  Renamed: hermes_cli/ -> vector_cli/")
else:
    print("  hermes_cli/ - already renamed or not present")

# Phase C: check for hermes_constants.py file
hermes_constants_file = VC / "python" / "vectorcode" / "hermes_constants.py"
vector_constants_file = VC / "python" / "vectorcode" / "vector_constants.py"
if hermes_constants_file.exists():
    if vector_constants_file.exists():
        # vector_constants.py already exists — just delete hermes_constants.py
        hermes_constants_file.unlink()
        print("  Removed redundant hermes_constants.py (vector_constants.py already exists)")
    else:
        hermes_constants_file.rename(vector_constants_file)
        print("  Renamed: hermes_constants.py -> vector_constants.py")

# Same for hermes_state, hermes_logging, hermes_time
for old, new in [("hermes_state", "vector_state"),
                  ("hermes_logging", "vector_logging"),
                  ("hermes_time", "vector_time")]:
    old_p = VC / "python" / "vectorcode" / f"{old}.py"
    new_p = VC / "python" / "vectorcode" / f"{new}.py"
    if old_p.exists():
        if new_p.exists():
            old_p.unlink()
            print(f"  Removed redundant {old}.py")
        else:
            old_p.rename(new_p)
            print(f"  Renamed: {old}.py -> {new}.py")

print()
print("Rebrand complete.")
