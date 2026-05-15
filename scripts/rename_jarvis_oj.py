"""Rename all remaining Jarvis/oj references to VECTOR/vc.

Phase 1: Rename jarvis-named files + update all references.
Phase 2: Rename 9 oj_ directories to vc_ + rewrite 887 import paths.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(ROOT))

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1 — Rename jarvis-named files
# ═══════════════════════════════════════════════════════════════════════════

FILE_RENAMES: list[tuple[str, str]] = [
    ("core/ui/dashboard/src/components/JarvisOverlay.tsx",
     "core/ui/dashboard/src/components/VectorOverlay.tsx"),
    ("vectorcode/src/evals/backends/jarvis_agent.py",
     "vectorcode/src/evals/backends/vector_agent.py"),
    ("vectorcode/src/evals/backends/jarvis_direct.py",
     "vectorcode/src/evals/backends/vector_direct.py"),
    ("tests/test_oj_integration.py",
     "tests/test_absorption_integration.py"),
    ("docs/superpowers/specs/2026-05-12-jarvis-dashboard-design.md",
     "docs/superpowers/specs/2026-05-12-dashboard-design.md"),
    ("brain/wiki/concepts/jarvis-architecture.md",
     "brain/wiki/concepts/vector-architecture.md"),
    ("vectorcode/skills/vc-as-blue-origin/references/project-jarvis.md",
     "vectorcode/skills/vc-as-blue-origin/references/project-vector.md"),
]

# Content replacements to apply across ALL files
CONTENT_REPLACEMENTS: list[tuple[str, str]] = [
    # Class names
    ("JarvisAgentBackend", "VectorAgentBackend"),
    ("JarvisDirectBackend", "VectorDirectBackend"),
    ("JarvisHud", "VectorHud"),
    ("JARVIS_HUD", "VECTOR_HUD"),
    # Import paths
    ("from vectorcode.src.evals.backends.jarvis_agent",
     "from vectorcode.src.evals.backends.vector_agent"),
    ("from vectorcode.src.evals.backends.jarvis_direct",
     "from vectorcode.src.evals.backends.vector_direct"),
    ("import vectorcode.src.evals.backends.jarvis_agent",
     "import vectorcode.src.evals.backends.vector_agent"),
    ("import vectorcode.src.evals.backends.jarvis_direct",
     "import vectorcode.src.evals.backends.vector_direct"),
    # Component names in TSX
    ("import JarvisOverlay", "import VectorOverlay"),
    ("<JarvisOverlay", "<VectorOverlay"),
    ("JarvisOverlay />", "VectorOverlay />"),
    # Doc links
    ("jarvis-architecture", "vector-architecture"),
    ("project-jarvis", "project-vector"),
    # Tags in frontmatter
    ("tags: [jarvis,", "tags: [vector,"),
    ("title: JARVIS", "title: VECTOR"),
    # Class names in the backends
    ("class JarvisDirectBackend", "class VectorDirectBackend"),
    ("class JarvisAgentBackend", "class VectorAgentBackend"),
    # docstring references
    ("JarvisDirect", "VectorDirect"),
    ("JarvisAgent", "VectorAgent"),
]

# Skip these paths during content replacement
SKIP_PATHS = {
    "scripts/absorb_openjarvis.py",
    "scripts/finalize_openjarvis_absorption.ps1",
    "scripts/strip_openjarvis_branding.py",
    "scripts/fix_absorption_imports.py",
    "scripts/fix_oj_imports.py",
    "scripts/rename_jarvis_oj.py",
    "scripts/audit_jarvis_oj.py",
    "RUN_THIS_VECTOR_FINISH.md",
}

EXTENSIONS = {".py", ".md", ".yml", ".yaml", ".toml", ".txt",
              ".ps1", ".sh", ".json", ".html", ".js", ".tsx", ".ts", ".css"}
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "node_modules",
                ".pytest_cache", ".gstack", ".agents", ".tmp", "test_tmp"}


def replace_in_files() -> int:
    """Apply CONTENT_REPLACEMENTS across all eligible files."""
    total_changes = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in EXTENSIONS:
                continue
            fp = os.path.join(root, f)
            rel = os.path.normpath(fp).replace("\\", "/")
            if rel in SKIP_PATHS:
                continue
            try:
                text = open(fp, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            changed = False
            for old, new in CONTENT_REPLACEMENTS:
                if old in text:
                    text = text.replace(old, new)
                    changed = True
                    total_changes += 1
            if changed:
                open(fp, "w", encoding="utf-8").write(text)
    return total_changes


def rename_files() -> int:
    """Rename files on disk."""
    count = 0
    for old_rel, new_rel in FILE_RENAMES:
        old_path = ROOT / old_rel
        new_path = ROOT / new_rel
        if old_path.exists():
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.rename(new_path)
            print(f"  RENAMED: {old_rel} -> {new_rel}")
            count += 1
        else:
            print(f"  [skip] {old_rel} not found")
    return count


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2 — Rename oj_ directories → vc_
# ═══════════════════════════════════════════════════════════════════════════

# The oj_ prefix was used during absorption to avoid name collisions with
# VECTOR's own directories (core/, agents/, tools/, etc.).  Renaming to vc_
# (VectorCode) removes the OpenJarvis-heritage hint while preserving the
# collision-avoidance purpose.

OJ_TO_VC: dict[str, str] = {
    "oj_core": "vc_core",
    "oj_agents": "vc_agents",
    "oj_tools": "vc_tools",
    "oj_engine": "vc_engine",
    "oj_security": "vc_security",
    "oj_system": "vc_system",
    "oj_mcp": "vc_mcp",
    "oj_templates": "vc_templates",
    "oj_traces": "vc_traces",
    "oj_skills": "vc_skills",
    "oj_providers": "vc_providers",
}


def rename_oj_dirs() -> int:
    """Rename 9 subdirectories from oj_X to vc_X."""
    vc_src = ROOT / "vectorcode" / "src"
    count = 0
    for old_name, new_name in OJ_TO_VC.items():
        old_dir = vc_src / old_name
        new_dir = vc_src / new_name
        if old_dir.exists() and not new_dir.exists():
            old_dir.rename(new_dir)
            print(f"  RENAMED DIR: vectorcode/src/{old_name}/ -> vectorcode/src/{new_name}/")
            count += 1
        elif new_dir.exists():
            print(f"  [skip] vectorcode/src/{new_name}/ already exists")
        else:
            print(f"  [skip] vectorcode/src/{old_name}/ not found")
    return count


def rewrite_oj_imports() -> int:
    """Rewrite ALL ``vectorcode.src.oj_X`` import paths to ``vectorcode.src.vc_X``."""
    total = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if not f.endswith(".py"):
                continue
            fp = os.path.join(root, f)
            rel = os.path.normpath(fp).replace("\\", "/")
            if rel in SKIP_PATHS:
                continue
            try:
                text = open(fp, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            changed = False
            for old_name, new_name in OJ_TO_VC.items():
                # Replace import paths: vectorcode.src.oj_X → vectorcode.src.vc_X
                old_import = f"vectorcode.src.{old_name}"
                new_import = f"vectorcode.src.{new_name}"
                if old_import in text:
                    text = text.replace(old_import, new_import)
                    changed = True
                    total += 1
            if changed:
                open(fp, "w", encoding="utf-8").write(text)
    return total


def main() -> int:
    print("=" * 60)
    print("PHASE 1: Renaming jarvis-named files")
    print("=" * 60)
    n = rename_files()
    print(f"  {n} files renamed")

    print("\n" + "=" * 60)
    print("PHASE 1b: Updating content references")
    print("=" * 60)
    n = replace_in_files()
    print(f"  {n} content replacements")

    print("\n" + "=" * 60)
    print("PHASE 2: Renaming oj_ directories to vc_")
    print("=" * 60)
    n = rename_oj_dirs()
    print(f"  {n} directories renamed")

    print("\n" + "=" * 60)
    print("PHASE 2b: Rewriting oj_X import paths to vc_X")
    print("=" * 60)
    n = rewrite_oj_imports()
    print(f"  {n} import paths rewritten")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
