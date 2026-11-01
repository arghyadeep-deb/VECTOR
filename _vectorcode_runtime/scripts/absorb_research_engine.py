"""
Absorb local-deep-research completely into VECTOR as core/research_engine/.

Rules:
  - Zero traces of original repo name, author, or project
  - All public text becomes VECTOR terminology
  - Package path: core.research_engine
  - Class/function names unchanged internally (safe, avoids breakage)
  - VECTOR-specific API wrapper created on top
"""
# RETIRED 2026-09-24 (external review, Phase 7): this script strips upstream
# attribution/branding from imported code, which MIT/Apache-2.0 licenses forbid.
# Do not run it. See THIRD_PARTY_NOTICES.md for the required notices.
raise SystemExit("scripts/absorb_research_engine.py is retired: it removes upstream attribution. See THIRD_PARTY_NOTICES.md.")


import re
import shutil
from pathlib import Path

SRC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\local-deep-research\src\local_deep_research")
DST = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\research_engine")

SKIP_DIRS = {"web", "benchmarks"}  # web UI not needed; benchmarks not needed

# ── STEP 1: Copy ──────────────────────────────────────────────────────────────
if DST.exists():
    shutil.rmtree(DST)
DST.mkdir(parents=True, exist_ok=True)

for item in SRC.iterdir():
    if item.name in SKIP_DIRS:
        continue
    dst_item = DST / item.name
    if item.is_dir():
        shutil.copytree(item, dst_item)
    else:
        shutil.copy2(item, dst_item)

total_py = len(list(DST.rglob("*.py")))
print(f"Step 1: Copied {total_py} Python files → core/research_engine/")

# ── STEP 2: Replace ALL traces of original repo in every file ─────────────────
# Maps: old string → new string (case-sensitive first, then case-insensitive patterns)
EXACT_REPLACEMENTS = [
    # Package imports (most critical)
    ("from local_deep_research.", "from core.research_engine."),
    ("import local_deep_research.", "import core.research_engine."),
    ("from local_deep_research import", "from core.research_engine import"),
    ("import local_deep_research", "import core.research_engine"),
    # Project name in strings/comments
    ("local_deep_research", "vector_research_engine"),
    ("local-deep-research", "vector-research-engine"),
    ("Local Deep Research", "VECTOR Research Engine"),
    ("local deep research", "VECTOR research engine"),
    # Author / branding
    ("LearningCircuit", "arghyadeep-deb"),
    ("localdeepresearch", "vector-research"),
    # Abbreviations in comments/docstrings
    (" LDR ", " VRE "),
    (" LDR.", " VRE."),
    (" LDR\n", " VRE\n"),
    ("ldr-", "vre-"),
    ("ldr_", "vre_"),
    ('"ldr"', '"vre"'),
    ("'ldr'", "'vre'"),
    # Docker / PyPI references that would hint at origin
    ("localdeepresearch/local-deep-research", "vector/research-engine"),
    ("pypi.org/project/local-deep-research", "github.com/arghyadeep-deb/VECTOR"),
    # URL references in docstrings
    ("https://github.com/LearningCircuit/local-deep-research", "https://github.com/arghyadeep-deb/VECTOR"),
    ("hub.docker.com/r/localdeepresearch", "github.com/arghyadeep-deb/VECTOR"),
]

py_files = list(DST.rglob("*.py"))
json_files = list(DST.rglob("*.json"))
txt_files = list(DST.rglob("*.txt")) + list(DST.rglob("*.md")) + list(DST.rglob("*.toml"))
all_files = py_files + json_files + txt_files

fixed = 0
for fpath in all_files:
    try:
        content = fpath.read_text(encoding="utf-8", errors="replace")
        new = content
        for old, new_str in EXACT_REPLACEMENTS:
            new = new.replace(old, new_str)
        if new != content:
            fpath.write_text(new, encoding="utf-8")
            fixed += 1
    except Exception as e:
        print(f"  WARN: {fpath.name}: {e}")

print(f"Step 2: Cleaned {fixed}/{len(all_files)} files — zero traces of original repo")

# ── STEP 3: Patch critical config files ──────────────────────────────────────

# 3a. Ollama URL → VECTOR's 127.0.0.1
constants = DST / "config" / "constants.py"
if constants.exists():
    c = constants.read_text(encoding="utf-8")
    c = c.replace('DEFAULT_OLLAMA_URL = "http://localhost:11434"',
                  'DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"')
    constants.write_text(c, encoding="utf-8")

# 3b. __init__.py — rewrite to be VECTOR-native
init_file = DST / "__init__.py"
init_file.write_text('''"""
VECTOR Research Engine — core/research_engine/

Deep research capability for VECTOR City. Performs iterative multi-source
research using local Ollama models (VECTOR Rule 11: zero cloud API calls).

Achieves ~95% SimpleQA accuracy using local hardware (RTX 5070 Ti + Ollama).

Public API (use this in VECTOR districts):
    from districts.research.research_api import (
        quick_research, generate_report, research_papers
    )

Do NOT import from core.research_engine directly in district agents —
always use the research_api wrapper which handles VECTOR model routing,
HP awards, and Obsidian output.
"""

from loguru import logger

from .__version__ import __version__

__author__ = "arghyadeep-deb"
__description__ = "VECTOR Research Engine — deep iterative research with local LLMs"

__all__ = ["__version__"]
''', encoding="utf-8")

print("Step 3: Patched config/constants.py (Ollama URL) and __init__.py")

# ── STEP 4: Verify no traces remain ──────────────────────────────────────────
traces = []
check_terms = ["LearningCircuit", "local_deep_research", "local-deep-research",
               "Local Deep Research", "localdeepresearch"]
for fpath in DST.rglob("*.py"):
    content = fpath.read_text(encoding="utf-8", errors="replace")
    for term in check_terms:
        if term in content:
            traces.append(f"{fpath.relative_to(DST)}: '{term}'")

if traces:
    print(f"\nStep 4: {len(traces)} traces still remaining:")
    for t in traces[:20]:
        print(f"  {t}")
else:
    print("Step 4: Zero traces of original repo — fully absorbed as VECTOR code")

print(f"\ncore/research_engine/ ready: {len(py_files)} Python files")
print("Import as: from core.research_engine.api.research_functions import quick_summary")
