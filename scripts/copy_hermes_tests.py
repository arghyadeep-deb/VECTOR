"""Bulk copy Hermes test files into VectorCode and rebrand imports."""
import re
import shutil
from pathlib import Path

H_TESTS = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\NousResearch_hermes-agent\repo\tests")
VC_TESTS = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\python\tests\hermes_ported")

# Rebrand patterns (post-copy)
PROTECTED = re.compile(
    r'nous-hermes|NousResearch/Hermes|hermes3:[0-9]+b|Hermes-[34]'
    r'|Hermes3|openrouter/hermes|nous_hermes',
    re.IGNORECASE,
)


def rebrand(text: str) -> str:
    masked = []
    work = PROTECTED.sub(
        lambda m: (masked.append(m.group(0)) or f"\x00P{len(masked)-1}\x00"),
        text,
    )
    # Identifier prefixes
    work = re.sub(r'\bhermes_', 'vector_', work)
    work = re.sub(r'\bHermes_', 'Vector_', work)
    work = re.sub(r'\bHERMES_', 'VECTOR_', work)
    # Standalone words
    work = re.sub(r'\bhermes\b', 'vector', work)
    work = re.sub(r'\bHermes\b', 'VectorCode', work)
    work = re.sub(r'\bHERMES\b', 'VECTOR', work)
    work = re.sub(r'\bruflo\b', 'vector', work)
    work = re.sub(r'\bRuflo\b', 'VectorCode', work)
    # Restore
    for i, orig in enumerate(masked):
        work = work.replace(f"\x00P{i}\x00", orig)
    return work


# Copy
copied = 0
for src in H_TESTS.rglob("*.py"):
    if "__pycache__" in src.parts:
        continue
    rel = src.relative_to(H_TESTS)
    dst = VC_TESTS / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = src.read_text(encoding="utf-8")
    except Exception:
        continue
    new_text = rebrand(text)
    dst.write_text(new_text, encoding="utf-8")
    copied += 1

print(f"Copied + rebranded: {copied} test files")
