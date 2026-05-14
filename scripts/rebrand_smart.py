"""Smart final rebrand — preserve model API identifiers, rename code identifiers.

Strategy:
  - For identifiers (function names, var names): rename to vector_*
  - For string literals containing model names (nous-hermes, hermes3:70b, etc.):
    keep them as-is (they're real Nous Research model API names)
  - Comments: rebrand
"""
import re
from pathlib import Path

VC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode")

# Identifier-only renames (will only apply outside string literals)
# These are local vars / function names / etc.
IDENTIFIER_RENAMES = [
    ("hermes_tools",                "vector_tools"),
    ("hermes_host",                 "vector_host"),
    ("hermes_warn",                 "vector_warn"),
    ("hermes_path",                 "vector_path"),
    ("hermes_dir",                  "vector_dir"),
    ("hermes_root",                 "vector_root"),
    ("hermes_dotenv",               "vector_dotenv"),
    ("hermes_model",                "vector_model"),
    ("hermes_id",                   "vector_id"),
    ("hermes_metadata",             "vector_metadata"),
    ("hermes_session",              "vector_session"),
    ("hermes_skill",                "vector_skill"),
    ("hermes_url",                  "vector_url"),
    ("hermes_data",                 "vector_data"),
    ("hermes_account",              "vector_account"),
    ("hermes_user",                 "vector_user"),
    ("HermesACPAgent",              "VectorCodeACPAgent"),
    ("HermesTime",                  "VectorTime"),
    ("HermesState",                 "VectorState"),
    ("HermesLogger",                "VectorLogger"),
    ("HermesError",                 "VectorError"),
    ("HermesException",             "VectorException"),
    ("HermesConfig",                "VectorConfig"),
    ("HermesProvider",              "VectorProvider"),
    ("HermesAgent",                 "VectorCodeAgent"),
]

# In-string phrases (comments, docstrings, error messages) — these we DO replace
COMMENT_PHRASES = [
    ("Hermes",                      "VectorCode"),
    ("hermes-agent",                "vectorcode"),
    ("Hermes Agent",                "VectorCode"),
    ("Hermes' ",                    "VectorCode's "),
    ("Ruflo",                       "VectorCode"),
    ("ruvocal",                     "vocal"),
    ("ruvnet/ruflo",                "vectorcode"),
]

# Skip our scripts
SKIP_FILES = {
    "rebrand_to_vectorcode.py",
    "rebrand_phase_c.py",
    "rebrand_final.py",
    "rebrand_smart.py",
    "bulk_absorb_hermes.py",
    "bulk_absorb_ruflo.py",
}

SKIP_DIRS = {"__pycache__", ".git", "node_modules", "absorption"}

ALLOWED_EXT = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".sh"}

# Don't touch real Nous Research model names — they're API identifiers
PROTECTED_PATTERNS = [
    r'nous-hermes',
    r'NousResearch/Hermes',
    r'hermes3:[0-9]+b',
    r'Hermes-3',
    r'hermes-3',
    r'Hermes3',
    r'NousResearch_hermes',
    r'openrouter/hermes',
    r'hermes-4',
    r'Hermes-4',
]
PROTECTED_RE = re.compile('|'.join(PROTECTED_PATTERNS))

stats = {"changed": 0, "swaps": 0, "scanned": 0}


def transform(text: str) -> tuple[str, int]:
    n = 0
    new = text

    # Step 1: identifier renames — apply directly (these aren't in protected patterns)
    for old, repl in IDENTIFIER_RENAMES:
        if old in new:
            count = new.count(old)
            new = new.replace(old, repl)
            n += count

    # Step 2: phrase replacements — protect model identifiers via placeholder
    placeholders = {}
    for i, m in enumerate(PROTECTED_RE.finditer(new)):
        ph = f"\x00PROTECTED{i}\x00"
        placeholders[ph] = m.group(0)
    # Replace from end to start to preserve offsets
    for i, m in enumerate(reversed(list(PROTECTED_RE.finditer(new)))):
        idx = len(placeholders) - 1 - i
        ph = f"\x00PROTECTED{idx}\x00"
        new = new[:m.start()] + ph + new[m.end():]

    # Now safe to do phrase replacements
    for old, repl in COMMENT_PHRASES:
        if old in new:
            count = new.count(old)
            new = new.replace(old, repl)
            n += count

    # Word-boundary lowercase hermes/ruflo (catches comments like "in hermes the X")
    pattern = re.compile(r'\bhermes\b', re.IGNORECASE)
    matches = list(pattern.finditer(new))
    if matches:
        n += len(matches)
        def case_match(m):
            src = m.group(0)
            if src.isupper(): return "VECTOR"
            if src[0].isupper(): return "VectorCode"
            return "vector"
        new = pattern.sub(case_match, new)

    pattern = re.compile(r'\bruflo\b', re.IGNORECASE)
    matches = list(pattern.finditer(new))
    if matches:
        n += len(matches)
        def case_match(m):
            src = m.group(0)
            if src.isupper(): return "VECTOR"
            if src[0].isupper(): return "VectorCode"
            return "vector"
        new = pattern.sub(case_match, new)

    # Restore protected patterns
    for ph, original in placeholders.items():
        new = new.replace(ph, original)

    return new, n


def should_process(p: Path) -> bool:
    if p.name in SKIP_FILES: return False
    if p.suffix.lower() not in ALLOWED_EXT: return False
    if any(d in p.parts for d in SKIP_DIRS): return False
    try:
        if p.stat().st_size > 5 * 1024 * 1024: return False
    except OSError: return False
    return True


for path in VC.rglob("*"):
    if not path.is_file(): continue
    if not should_process(path): continue
    stats["scanned"] += 1
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    new, n = transform(text)
    if n:
        path.write_text(new, encoding="utf-8")
        stats["changed"] += 1
        stats["swaps"] += n

print(f"Scanned: {stats['scanned']}")
print(f"Changed: {stats['changed']}")
print(f"Swaps:   {stats['swaps']}")
