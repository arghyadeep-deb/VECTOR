"""Audit any remaining Jarvis, OJ, or OpenJarvis references."""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache",
                ".gstack", ".agents", ".mypy_cache", ".ruff_cache", ".cursor",
                ".claude", ".yarn", ".tmp", "test_tmp"}

ALLOWED_FILES = {
    "scripts/absorb_openjarvis.py",
    "scripts/finalize_openjarvis_absorption.ps1",
    "scripts/strip_openjarvis_branding.py",
    "scripts/fix_absorption_imports.py",
    "scripts/fix_oj_imports.py",
    "scripts/audit_jarvis_oj.py",
    "RUN_THIS_VECTOR_FINISH.md",
}

EXTENSIONS = {".py", ".md", ".yml", ".yaml", ".toml", ".cfg", ".txt",
              ".ps1", ".sh", ".bat", ".json", ".html", ".js", ".tsx",
              ".ts", ".css", ".ini", ".lock", ".rs", ".cjs", ".mjs"}

print("=" * 70)
print("AUDIT: Jarvis / OJ / OpenJarvis references")
print("=" * 70)

# ── 1. File names ────────────────────────────────────────────────────────
print("\n--- 1. FILENAMES containing jarvis/openjarvis/oj_ ---")
file_hits = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
    for f in files:
        fp = os.path.join(root, f)
        rel = os.path.normpath(fp).replace("\\", "/")
        if rel in ALLOWED_FILES:
            continue
        lower = f.lower()
        if "jarvis" in lower or "openjarvis" in lower or "open-jarvis" in lower:
            file_hits.append(rel)
        # Also flag oj_ prefixed dirs in the path
        parts = rel.split("/")
        for p in parts:
            if p.startswith("oj_") and p not in ("oj_core", "oj_agents", "oj_tools",
                   "oj_engine", "oj_security", "oj_system", "oj_mcp",
                   "oj_templates", "oj_traces", "oj_skills", "oj_providers"):
                if rel not in file_hits:
                    file_hits.append(f"{rel}  [dir: {p}]")

for f in sorted(file_hits):
    print(f"  {f}")

# ── 2. Content ──────────────────────────────────────────────────────────
print("\n--- 2. CONTENT references to jarvis / OJ / openjarvis ---")

patterns = [
    ("\\bjarvis\\b", re.IGNORECASE, "word 'jarvis'"),
    ("\\boj\\b", re.IGNORECASE, "word 'oj'"),
    ("openjarvis", re.IGNORECASE, "openjarvis"),
    ("open-jarvis", re.IGNORECASE, "open-jarvis"),
    ("openJarvis", 0, "openJarvis"),
    ("OPENJARVIS", 0, "OPENJARVIS"),
]

found = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in EXTENSIONS:
            continue
        fp = os.path.join(root, f)
        rel = os.path.normpath(fp).replace("\\", "/")
        if rel in ALLOWED_FILES:
            continue
        try:
            text = open(fp, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for pat, flags, label in patterns:
            for m in re.finditer(pat, text, flags):
                line = text[: m.start()].count("\n") + 1
                # Skip common false positives for "oj": Python's .pyo, image formats
                ctx = text[max(0, m.start() - 15) : m.end() + 15].replace("\n", " ")
                found.append((rel, line, m.group(), label, ctx))

for rel, line, match, label, ctx in sorted(found):
    print(f"  {rel}:{line}  {match!r:20s}  ({label})  ...{ctx.strip()}...")

# ── 3. Import paths with oj_ ────────────────────────────────────────────
print("\n--- 3. IMPORT paths referencing vectorcode.src.oj_ ---")
import_hits = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
    for f in files:
        if not f.endswith(".py"):
            continue
        fp = os.path.join(root, f)
        rel = os.path.normpath(fp).replace("\\", "/")
        try:
            text = open(fp, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for m in re.finditer(r"(from\s+vectorcode\.src\.oj_\w+|import\s+vectorcode\.src\.oj_\w+)", text):
            import_hits.append((rel, m.group()))

for rel, imp in sorted(import_hits):
    print(f"  {rel}: {imp}")

print(f"\n{'='*70}")
print(f"Filenames with jarvis/etc: {len(file_hits)}")
print(f"Content references: {len(found)}")
print(f"oj_ import paths: {len(import_hits)}")
