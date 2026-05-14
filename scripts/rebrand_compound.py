"""Catches hermes/ruflo even inside compound identifiers like _hermes_now, _KIND_TO_HERMES."""
import re
from pathlib import Path

VC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode")

PROTECTED = re.compile(
    r'nous-hermes|NousResearch/Hermes|hermes3:[0-9]+b|Hermes-[34]|hermes-[34]'
    r'|Hermes3|openrouter/hermes|Hermes_3|hermes_3|Nous-Hermes|nous_hermes',
    re.IGNORECASE,
)

SKIP_FILES = {
    "rebrand_to_vectorcode.py", "rebrand_phase_c.py", "rebrand_final.py",
    "rebrand_smart.py", "rebrand_aggressive.py", "rebrand_compound.py",
    "bulk_absorb_hermes.py", "bulk_absorb_ruflo.py",
}
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "absorption"}
EXTS = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".sh"}

stats = {"changed": 0, "scanned": 0}


def transform(text: str) -> str:
    masked = []
    def mask_repl(m):
        masked.append(m.group(0))
        return f"\x00P{len(masked)-1}\x00"
    work = PROTECTED.sub(mask_repl, text)

    # Catch ANY occurrence of hermes/ruflo, NOT just word boundaries
    # Apply to all four cases
    work = re.sub(r'HERMES', 'VECTOR', work)
    work = re.sub(r'Hermes', 'VectorCode', work)
    work = re.sub(r'hermes', 'vector', work)
    work = re.sub(r'RUFLO', 'VECTOR', work)
    work = re.sub(r'Ruflo', 'VectorCode', work)
    work = re.sub(r'ruflo', 'vector', work)

    # Restore protected
    for i, orig in enumerate(masked):
        work = work.replace(f"\x00P{i}\x00", orig)

    return work


def should_process(p: Path) -> bool:
    if p.name in SKIP_FILES: return False
    if p.suffix.lower() not in EXTS: return False
    if any(d in p.parts for d in SKIP_DIRS): return False
    try:
        if p.stat().st_size > 5 * 1024 * 1024: return False
    except OSError:
        return False
    return True


for path in VC.rglob("*"):
    if not path.is_file(): continue
    if not should_process(path): continue
    stats["scanned"] += 1
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    new = transform(text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        stats["changed"] += 1

print(f"Scanned: {stats['scanned']}")
print(f"Changed: {stats['changed']}")
