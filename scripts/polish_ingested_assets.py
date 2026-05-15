"""
Polish pass — fixes awkward compound replacements from the ingestion script.

Specifically:
  - "Anthropic VectorCode API (local Ollama)" -> "VectorCode API (local Ollama)"
  - "Anthropic Claude" -> "VECTOR"
  - Stray double-replacement artifacts
  - Owner attribution (Anthropic the company isn't relevant in VECTOR docs;
    VECTOR is owned/built by Arghyadeep Deb).

Operates on every .md and .py file under vectorcode/skills/, vectorcode/agents/,
vectorcode/commands/, vectorcode/hooks/, vectorcode/rules/.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    ROOT / "vectorcode" / "skills",
    ROOT / "vectorcode" / "agents",
    ROOT / "vectorcode" / "commands",
    ROOT / "vectorcode" / "hooks",
    ROOT / "vectorcode" / "rules",
]

# Polishing replacements (run AFTER initial ingestion replacements)
POLISH = [
    # Double brand collisions
    (r"Anthropic VectorCode API \(local Ollama\)", "VectorCode API (local Ollama)"),
    (r"Anthropic VectorCode", "VectorCode"),
    (r"Anthropic Claude", "VECTOR"),
    (r"Anthropic`s (Claude|VectorCode)", "VECTOR"),
    (r"Anthropic\s+SDK", "Ollama SDK"),
    # Drop dangling "by Anthropic" / "from Anthropic"
    (r"\s+(by|from|at)\s+Anthropic\b", ""),
    # Remaining bare 'Anthropic' references in non-API context
    (r"\bAnthropic\b(?!\s*(?:Inc|company|Corporation))", "VECTOR Labs"),
    # "Claude" still standing alone (after first pass kept some)
    (r"\bClaude\b(?!-(?:sonnet|opus|haiku|3))", "VECTOR"),
    # Fix model placeholders
    (r"model:\s*opus", "model: vector-chairman"),
    (r"model:\s*sonnet", "model: vector-coder"),
    (r"model:\s*haiku", "model: vector-fast"),
]


def polish_text(text: str) -> str:
    out = text
    for pattern, replacement in POLISH:
        out = re.sub(pattern, replacement, out)
    return out


def process_file(path: Path) -> bool:
    """Returns True if file changed."""
    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return False
    polished = polish_text(original)
    if polished != original:
        path.write_text(polished, encoding="utf-8")
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    total = 0
    changed = 0
    for target in TARGETS:
        if not target.exists():
            continue
        for f in target.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in {".md", ".markdown", ".py", ".tmpl"}:
                continue
            total += 1
            if args.apply:
                if process_file(f):
                    changed += 1
            else:
                # Dry: count what would change
                try:
                    original = f.read_text(encoding="utf-8")
                    if polish_text(original) != original:
                        changed += 1
                except Exception:
                    pass

    print(f"Files scanned: {total}")
    print(f"Files {'changed' if args.apply else 'would change'}: {changed}")
    if not args.apply:
        print("(dry run — re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
