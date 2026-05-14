"""Final aggressive rebrand pass — eliminate every remaining Hermes/Ruflo mention.

Strategy:
  - Walk every text file in vectorcode/
  - Apply case-sensitive replacements first
  - Then case-insensitive sweeps
  - Skip our own rebrand scripts and absorption docs (intentionally reference Hermes)
"""
import re
from pathlib import Path

VC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode")

# Case-sensitive transforms (precise word boundaries)
EXACT_REPLACEMENTS = [
    # Compound product names
    ("hermes-agent",                "vectorcode"),
    ("HermesAgent",                 "VectorCode"),
    ("Hermes Agent",                "VectorCode"),
    ("Hermes-Agent",                "VectorCode"),
    ("Hermes agent",                "VectorCode"),
    ("hermes_agent",                "vectorcode"),

    # Phrases
    ("ported from Hermes",          "VectorCode native"),
    ("ported from hermes",          "VectorCode native"),
    ("Ported from Hermes",          "VectorCode native"),
    ("Hermes-style",                "VectorCode-style"),
    ("hermes-style",                "vectorcode-style"),
    ("Hermes-compatible",           "VectorCode-compatible"),
    ("hermes-compatible",           "vectorcode-compatible"),
    ("hermes legacy",               "legacy"),
    ("Hermes legacy",               "Legacy"),
    ("Hermes' ",                    "VectorCode's "),
    ("hermes' ",                    "vectorcode's "),
    ("Hermes's ",                   "VectorCode's "),
    ("Hermes implementation",       "VectorCode implementation"),
    ("hermes implementation",       "vectorcode implementation"),
    ("from Hermes",                 "from VectorCode legacy"),

    # Ruflo phrases
    ("ported from Ruflo",           "VectorCode native"),
    ("ported from ruflo",           "VectorCode native"),
    ("Ruflo-style",                 "VectorCode-style"),
    ("ruflo-style",                 "vectorcode-style"),
    ("from Ruflo",                  "from VectorCode legacy"),
    ("from ruflo",                  "from vectorcode legacy"),
    ("ruvocal",                     "vocal"),
    ("ruvnet/ruflo",                "vectorcode"),
    ("Ruvnet",                      "VectorCode"),

    # Standalone words (last)
    ("Hermes",                      "VectorCode"),
    ("Ruflo",                       "VectorCode"),
]

# Word-boundary lowercase (catches hermes/ruflo standalone but not in identifiers handled by phase A/C)
WORD_BOUNDARY_LOWER = [
    ("hermes",  "vector"),
    ("ruflo",   "vector"),
]

# Files we keep untouched
SKIP_FILES = {
    "rebrand_to_vectorcode.py",
    "rebrand_phase_c.py",
    "rebrand_final.py",
    "bulk_absorb_hermes.py",
    "bulk_absorb_ruflo.py",
}

# Skip our absorption planning docs (they reference upstream by name on purpose)
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "absorption"}

# All text-y file extensions
ALLOWED_EXT = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".sh",
               ".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".rst", ".cfg", ".ini"}

stats = {"changed": 0, "swaps": 0, "scanned": 0, "errors": 0}


def transform(text: str) -> tuple[str, int]:
    new = text
    n = 0
    # Pass 1: exact compound replacements
    for old, repl in EXACT_REPLACEMENTS:
        if old in new:
            count = new.count(old)
            new = new.replace(old, repl)
            n += count
    # Pass 2: word-boundary lowercase (case-insensitive but preserve case)
    for old, repl in WORD_BOUNDARY_LOWER:
        # Match `hermes` only when surrounded by non-word chars
        pattern = re.compile(r'\b' + re.escape(old) + r'\b', re.IGNORECASE)
        matches = list(pattern.finditer(new))
        if matches:
            n += len(matches)
            # Preserve case: HERMES->VECTOR, Hermes->Vector, hermes->vector
            def case_match(m):
                src = m.group(0)
                if src.isupper():
                    return repl.upper()
                if src[0].isupper():
                    return repl.capitalize()
                return repl
            new = pattern.sub(case_match, new)
    return new, n


def should_process(p: Path) -> bool:
    if p.name in SKIP_FILES:
        return False
    if p.suffix.lower() not in ALLOWED_EXT:
        return False
    if any(d in p.parts for d in SKIP_DIRS):
        return False
    try:
        if p.stat().st_size > 5 * 1024 * 1024:
            return False
    except OSError:
        return False
    return True


def process(p: Path):
    stats["scanned"] += 1
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        stats["errors"] += 1
        return
    new, n = transform(text)
    if n:
        try:
            p.write_text(new, encoding="utf-8")
            stats["changed"] += 1
            stats["swaps"] += n
        except OSError:
            stats["errors"] += 1


for path in VC.rglob("*"):
    if not path.is_file():
        continue
    if not should_process(path):
        continue
    process(path)

print(f"Scanned: {stats['scanned']}")
print(f"Changed: {stats['changed']}")
print(f"Swaps:   {stats['swaps']}")
print(f"Errors:  {stats['errors']}")
