"""Final rename pass — eliminate hermes/ruflo from file/folder names."""
import shutil
import os
from pathlib import Path

VC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode")

# (old_path_relative_to_VC, new_path_relative_to_VC)
RENAMES = [
    # Test directories
    ("python/tests/hermes_ported", "python/tests/legacy_ported"),
    # ALSO rename inside hermes_ported (after the above happens, paths shift):
    # We'll handle these in 2nd pass after the parent is renamed.

    # Skill folders
    ("skills/autonomous-ai-agents/hermes-agent",
     "skills/autonomous-ai-agents/vector-agent"),
    ("skills/optional/mlops/hermes-atropos-environments",
     "skills/optional/mlops/vector-atropos-environments"),
    ("skills/software-development/debugging-hermes-tui-commands",
     "skills/software-development/debugging-vector-tui-commands"),
    ("skills/software-development/hermes-agent-skill-authoring",
     "skills/software-development/vector-agent-skill-authoring"),
    ("skills/optional/migration/openclaw-migration/scripts/openclaw_to_hermes.py",
     "skills/optional/migration/openclaw-migration/scripts/openclaw_to_vector.py"),
    ("skills/productivity/google-workspace/scripts/_hermes_home.py",
     "skills/productivity/google-workspace/scripts/_vector_home.py"),
]


def safe_rename(src_rel: str, dst_rel: str) -> str:
    src = VC / src_rel
    dst = VC / dst_rel
    if not src.exists():
        return f"  [skip] {src_rel} (not found)"
    if dst.exists():
        return f"  [skip] {dst_rel} (target exists)"
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return f"  [ok]   {src_rel} -> {dst_rel}"


print("Pass 1: top-level renames")
for old, new in RENAMES:
    print(safe_rename(old, new))

# Pass 2: rename inside legacy_ported
print()
print("Pass 2: nested renames inside legacy_ported")
nested = [
    ("python/tests/legacy_ported/hermes_cli",
     "python/tests/legacy_ported/vector_cli"),
    ("python/tests/legacy_ported/hermes_state",
     "python/tests/legacy_ported/vector_state"),
    ("python/tests/legacy_ported/test_hermes_constants.py",
     "python/tests/legacy_ported/test_vector_constants.py"),
    ("python/tests/legacy_ported/test_hermes_logging.py",
     "python/tests/legacy_ported/test_vector_logging.py"),
    ("python/tests/legacy_ported/test_hermes_state.py",
     "python/tests/legacy_ported/test_vector_state.py"),
    ("python/tests/legacy_ported/vector_cli/test_nous_hermes_non_agentic.py",
     "python/tests/legacy_ported/vector_cli/test_nous_legacy_non_agentic.py"),
    ("python/tests/legacy_ported/vector_cli/test_setup_hermes_script.py",
     "python/tests/legacy_ported/vector_cli/test_setup_vector_script.py"),
]
for old, new in nested:
    print(safe_rename(old, new))


# Pass 3: nuke __pycache__ everywhere (stale .pyc files reference old names)
print()
print("Pass 3: cleaning __pycache__")
import shutil as _sh
removed = 0
for cache in VC.rglob("__pycache__"):
    if cache.is_dir():
        _sh.rmtree(cache, ignore_errors=True)
        removed += 1
print(f"  Removed {removed} __pycache__ dirs")


# Pass 4: also nuke pycache in the project root
ROOT = VC.parent
print()
print("Pass 4: cleaning root project __pycache__")
removed = 0
for cache in ROOT.rglob("__pycache__"):
    if "vector_legacy" in cache.parts or "GitHub" in cache.parts:
        continue
    if cache.is_dir():
        _sh.rmtree(cache, ignore_errors=True)
        removed += 1
print(f"  Removed {removed} __pycache__ dirs from project root")
