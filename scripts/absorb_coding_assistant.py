"""
Absorb mistral-vibe into VECTOR as core/coding_assistant/.

Rules:
  - Zero traces of original repo / branding
  - Package: core.coding_assistant
  - cli/textual_ui/ skipped (VECTOR has own UI)
  - setup/ skipped (not needed)
  - core/nuage/ skipped (Mistral cloud infra)
  - Everything else fully absorbed
"""
# RETIRED 2026-09-24 (external review, Phase 7): this script strips upstream
# attribution/branding from imported code, which MIT/Apache-2.0 licenses forbid.
# Do not run it. See THIRD_PARTY_NOTICES.md for the required notices.
raise SystemExit("scripts/absorb_coding_assistant.py is retired: it removes upstream attribution. See THIRD_PARTY_NOTICES.md.")


import re
import shutil
from pathlib import Path

SRC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\mistral-vibe\vibe")
DST = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\coding_assistant")

# Subdirectories inside vibe/cli/ to skip
CLI_SKIP = {"textual_ui"}
# Top-level directories under vibe/ to skip entirely
TOP_SKIP = {"setup"}
# Subdirs under vibe/core/ to skip
CORE_SKIP = {"nuage", "telemetry"}

# ── STEP 1: Copy with selective skips ────────────────────────────────────────
if DST.exists():
    shutil.rmtree(DST)
DST.mkdir(parents=True, exist_ok=True)

copied = 0
skipped_dirs = []

def copy_dir_selective(src: Path, dst: Path, skip_names: set[str] = frozenset()) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in src.iterdir():
        if item.name in skip_names:
            skipped_dirs.append(str(item.relative_to(SRC.parent)))
            continue
        dst_item = dst / item.name
        if item.is_dir():
            count += copy_dir_selective(item, dst_item)
        else:
            shutil.copy2(item, dst_item)
            count += 1
    return count

for top_item in SRC.iterdir():
    if top_item.name in TOP_SKIP:
        skipped_dirs.append(f"vibe/{top_item.name}/")
        continue
    dst_top = DST / top_item.name
    if top_item.is_dir():
        if top_item.name == "cli":
            copied += copy_dir_selective(top_item, dst_top, skip_names=CLI_SKIP)
        elif top_item.name == "core":
            copied += copy_dir_selective(top_item, dst_top, skip_names=CORE_SKIP)
        else:
            shutil.copytree(top_item, dst_top)
            copied += len(list(dst_top.rglob("*")))
    else:
        shutil.copy2(top_item, dst_top)
        copied += 1

total_py = len(list(DST.rglob("*.py")))
print(f"Step 1: Copied {total_py} Python files → core/coding_assistant/")
print(f"        Skipped: {skipped_dirs}")

# ── STEP 2: Replace ALL traces in every file ──────────────────────────────────
REPLACEMENTS = [
    # Import paths (most critical — must be first)
    ("from vibe.acp.", "from core.coding_assistant.acp."),
    ("from vibe.cli.", "from core.coding_assistant.cli."),
    ("from vibe.core.", "from core.coding_assistant.core."),
    ("from vibe.setup.", "from core.coding_assistant.setup."),
    ("import vibe.acp.", "import core.coding_assistant.acp."),
    ("import vibe.cli.", "import core.coding_assistant.cli."),
    ("import vibe.core.", "import core.coding_assistant.core."),
    # Bare package imports
    ("from vibe import", "from core.coding_assistant import"),
    ("import vibe", "import core.coding_assistant"),
    # String references to package name
    ("vibe.core", "core.coding_assistant.core"),
    ("vibe.acp", "core.coding_assistant.acp"),
    ("vibe.cli", "core.coding_assistant.cli"),
    # Branding in strings/comments/docstrings
    ("mistral-vibe", "vector-coding-assistant"),
    ("mistral_vibe", "vector_coding_assistant"),
    ("MistralVibe", "VectorCodingAssistant"),
    ("Mistral Vibe", "VECTOR Coding Assistant"),
    ("mistral vibe", "VECTOR coding assistant"),
    # Mistral-specific naming in comments/docs
    ("mistralai/mistral-vibe", "arghyadeep-deb/VECTOR"),
    ("mistralai", "arghyadeep-deb"),
    ("MistralAI", "VECTOR"),
    # Path conventions: .vibe/ → .vector_ca/ (VECTOR coding assistant home)
    ('".vibe"', '".vector_ca"'),
    ("'.vibe'", "'.vector_ca'"),
    ("/vibe/", "/vector_ca/"),
    ("VIBE_HOME", "VECTOR_CA_HOME"),
    # Variable/class names in comments
    ("VibeConfig", "VectorCAConfig"),
    ("VibeHome", "VectorCAHome"),
    # Remaining 'vibe' lowercase references in comments/strings
    # (careful not to break Python keywords or variable names that happen to contain 'vibe')
]

all_files = list(DST.rglob("*.py")) + list(DST.rglob("*.toml")) + \
            list(DST.rglob("*.json")) + list(DST.rglob("*.md")) + \
            list(DST.rglob("*.txt"))

fixed = 0
for fpath in all_files:
    try:
        content = fpath.read_text(encoding="utf-8", errors="replace")
        new = content
        for old, new_str in REPLACEMENTS:
            new = new.replace(old, new_str)
        if new != content:
            fpath.write_text(new, encoding="utf-8")
            fixed += 1
    except Exception as e:
        print(f"  WARN {fpath.name}: {e}")

print(f"Step 2: Cleaned {fixed}/{len(all_files)} files")

# ── STEP 3: Write clean __init__.py ──────────────────────────────────────────
(DST / "__init__.py").write_text('''"""
VECTOR Coding Assistant — core/coding_assistant/

A full-featured AI coding assistant engine for VECTOR.
Provides the agent loop, tool implementations, ACP protocol,
session management, hooks, skills parser, and LLM backends
that power VECTOR's coding district.

Subpackages:
    acp/         — Agent Communication Protocol (session-based agent interaction)
    core/        — Core engine (agent_loop, tools, skills, hooks, middleware)
    cli/         — CLI adapters (autocompletion, history, voice)

Key entry points:
    core.coding_assistant.core.programmatic  — programmatic agent execution
    core.coding_assistant.acp.entrypoint     — ACP server entry point
    core.coding_assistant.core.tools         — all tool implementations
"""
''', encoding="utf-8")

print("Step 3: Wrote clean __init__.py")

# ── STEP 4: Zero-trace verification ──────────────────────────────────────────
bad_terms = ["mistralai", "mistral-vibe", "mistral_vibe", "MistralVibe",
             "Mistral Vibe", "from vibe.", "import vibe."]

traces = []
for fpath in DST.rglob("*.py"):
    content = fpath.read_text(encoding="utf-8", errors="replace")
    for term in bad_terms:
        if term in content:
            traces.append(f"{fpath.relative_to(DST)}: {term!r}")

print(f"Step 4: Traces = {len(traces)} (want 0)")
for t in traces[:10]:
    print(f"  {t}")

print(f"\ncore/coding_assistant/ ready: {total_py} Python files")
print("Done.")
