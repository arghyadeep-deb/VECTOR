"""Phase C of rebranding — fix identifiers like get_hermes_home, hermes_home, etc."""
import re
from pathlib import Path

VC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode")

# Identifier renames (function names, attribute names embedded in code)
REPLACEMENTS = [
    ("get_hermes_home",        "get_vector_home"),
    ("display_hermes_home",    "display_vector_home"),
    ("hermes_home",            "vector_home"),
    ("hermes_skills_dir",      "vector_skills_dir"),
    ("hermes_sessions_dir",    "vector_sessions_dir"),
    ("hermes_memory_path",     "vector_memory_path"),
    ("hermes_config_path",     "vector_config_path"),
    ("hermes_data_dir",        "vector_data_dir"),
    ("hermes_session",         "vector_session"),
    ("hermes_account",         "vector_account"),
    ("hermes_dotenv",          "vector_dotenv"),
    ("hermes_user",            "vector_user"),
    ("HERMES_HOME",            "VECTOR_HOME"),  # in case any escaped
    ("Hermes",                 "VectorCode"),
    ("hermes-",                "vectorcode-"),
    ("hermes/",                "vector/"),
]

SKIP_FILES = {"rebrand_to_vectorcode.py", "rebrand_phase_c.py",
              "bulk_absorb_hermes.py", "bulk_absorb_ruflo.py"}
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "absorption"}
ALLOWED_EXT = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt",
               ".ts", ".tsx", ".js", ".html"}

stats = {"changed": 0, "swaps": 0, "scanned": 0}


def transform(text: str) -> tuple[str, int]:
    new = text
    n = 0
    for old, repl in REPLACEMENTS:
        if old in new:
            count = new.count(old)
            new = new.replace(old, repl)
            n += count
    return new, n


def process(p: Path):
    stats["scanned"] += 1
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    new, n = transform(text)
    if n:
        p.write_text(new, encoding="utf-8")
        stats["changed"] += 1
        stats["swaps"] += n


for path in VC.rglob("*"):
    if not path.is_file():
        continue
    if path.name in SKIP_FILES:
        continue
    if path.suffix.lower() not in ALLOWED_EXT:
        continue
    if any(d in path.parts for d in SKIP_DIRS):
        continue
    if path.stat().st_size > 5 * 1024 * 1024:
        continue
    process(path)

print(f"Scanned: {stats['scanned']}")
print(f"Changed: {stats['changed']}")
print(f"Swaps:   {stats['swaps']}")
