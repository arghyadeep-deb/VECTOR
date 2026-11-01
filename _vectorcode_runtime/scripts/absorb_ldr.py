"""
Absorb local-deep-research into core/ldr/ in VECTOR.

Steps:
  1. Copy src/local_deep_research/ → core/ldr/ (skip web/ and benchmarks/)
  2. Replace all absolute 'from local_deep_research.' with 'from core.ldr.'
  3. Patch Ollama URL to VECTOR's 127.0.0.1
"""
import re
import shutil
from pathlib import Path

SRC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\local-deep-research\src\local_deep_research")
DST = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\core\ldr")

# Subpackages to skip (web UI + benchmarks not needed in VECTOR)
SKIP = {"web", "benchmarks"}

# ── Step 1: Copy ──────────────────────────────────────────────────────────────
if DST.exists():
    shutil.rmtree(DST)
DST.mkdir(parents=True, exist_ok=True)

copied_files = 0
skipped_dirs = 0

for item in SRC.iterdir():
    if item.name in SKIP:
        skipped_dirs += 1
        continue
    dst_item = DST / item.name
    if item.is_dir():
        shutil.copytree(item, dst_item)
    else:
        shutil.copy2(item, dst_item)
    copied_files += 1

print(f"Step 1: Copied {copied_files} items, skipped {skipped_dirs} dirs ({', '.join(SKIP)})")

# ── Step 2: Fix absolute imports ──────────────────────────────────────────────
py_files = list(DST.rglob("*.py"))
fixed_files = 0
total_replacements = 0

for py_file in py_files:
    content = py_file.read_text(encoding="utf-8", errors="replace")
    new_content = content.replace("from local_deep_research.", "from core.ldr.")
    new_content = new_content.replace("import local_deep_research.", "import core.ldr.")
    # Also handle 'from local_deep_research import' style
    new_content = new_content.replace("from local_deep_research import", "from core.ldr import")
    if new_content != content:
        count = content.count("local_deep_research")
        total_replacements += count
        py_file.write_text(new_content, encoding="utf-8")
        fixed_files += 1

print(f"Step 2: Fixed {fixed_files} files ({total_replacements} replacements)")

# ── Step 3: Patch Ollama URL to VECTOR's 127.0.0.1 ───────────────────────────
constants_file = DST / "config" / "constants.py"
if constants_file.exists():
    content = constants_file.read_text(encoding="utf-8")
    # VECTOR uses 127.0.0.1 not localhost (OLLAMA_HOST env var)
    new_content = content.replace(
        'DEFAULT_OLLAMA_URL = "http://localhost:11434"',
        'DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"'
    )
    if new_content != content:
        constants_file.write_text(new_content, encoding="utf-8")
        print("Step 3: Patched Ollama URL → 127.0.0.1:11434")
    else:
        print("Step 3: Ollama URL already correct or not found — check manually")

# ── Step 4: Patch __init__.py to not suppress logging ─────────────────────────
init_file = DST / "__init__.py"
if init_file.exists():
    content = init_file.read_text(encoding="utf-8")
    # Remove logger.disable so VECTOR's loguru config controls logging
    new_content = content.replace(
        'logger.disable("local_deep_research")',
        '# logger.disable disabled — VECTOR controls logging via loguru config'
    )
    if new_content != content:
        init_file.write_text(new_content, encoding="utf-8")
        print("Step 4: Patched __init__.py — logging no longer suppressed")

# ── Step 5: Write core/ldr/__init__.py update ────────────────────────────────
# Add a note so VECTOR developers know where this came from
header_addition = '''"""
VECTOR Research Engine — absorbed from local-deep-research
Source: https://github.com/LearningCircuit/local-deep-research
~95% SimpleQA accuracy using local Ollama models.

Usage in VECTOR:
    from districts.research.ldr_config import make_ldr_settings
    from core.ldr.api.research_functions import quick_summary, generate_report

    settings = make_ldr_settings(mode="quick")
    result = quick_summary("KIIT attendance policy", settings_snapshot=settings)
"""
'''
if init_file.exists():
    existing = init_file.read_text(encoding="utf-8")
    if "VECTOR Research Engine" not in existing:
        init_file.write_text(header_addition + existing, encoding="utf-8")

# ── Final report ──────────────────────────────────────────────────────────────
total_py = len(list(DST.rglob("*.py")))
total_all = len(list(DST.rglob("*")))
print(f"\ncore/ldr/ created: {total_py} Python files, {total_all} total files")
print(f"Package path: core.ldr")
print(f"API entry: core.ldr.api.research_functions")
print("Done.")
