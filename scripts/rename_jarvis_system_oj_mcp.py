"""Rename JarvisSystem -> VectorSystem and _OJ_MCP_AVAILABLE -> _VC_MCP_AVAILABLE."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(ROOT))

REPLACEMENTS: list[tuple[str, str, str]] = [
    # (pattern, replacement, label)
    # Class renames (in code + strings)
    ("JarvisSystem", "VectorSystem", "class JarvisSystem -> VectorSystem"),
    # Variable rename
    ("_OJ_MCP_AVAILABLE", "_VC_MCP_AVAILABLE", "var _OJ_MCP_AVAILABLE -> _VC_MCP_AVAILABLE"),
]

EXTENSIONS = {".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".json"}
EXCLUDE = {".git", "__pycache__", ".venv", "node_modules"}

# Files to skip (migration scripts)
SKIP = {
    "scripts/absorb_openjarvis.py",
    "scripts/finalize_openjarvis_absorption.ps1",
    "scripts/strip_openjarvis_branding.py",
    "scripts/fix_absorption_imports.py",
    "scripts/fix_oj_imports.py",
    "scripts/rename_jarvis_oj.py",
    "scripts/rename_jarvis_system_oj_mcp.py",
    "scripts/audit_jarvis_oj.py",
}

total = 0
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in EXCLUDE]
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in EXTENSIONS:
            continue
        fp = os.path.join(root, f)
        rel = os.path.normpath(fp).replace("\\", "/")
        if rel in SKIP:
            continue
        try:
            text = open(fp, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        changed = False
        for old, new, label in REPLACEMENTS:
            if old in text:
                text = text.replace(old, new)
                changed = True
        if changed:
            open(fp, "w", encoding="utf-8").write(text)
            count = sum(text.count(new) for _, new, _ in REPLACEMENTS)
            total += 1
            print(f"  {rel}")

print(f"\n{total} files updated")
