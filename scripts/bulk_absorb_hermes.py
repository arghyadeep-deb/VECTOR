"""Bulk copy Hermes files into VectorCode preserving structure.

Strategy:
  - Copy all .py files from key Hermes directories into vectorcode/python/vectorcode/
  - Skip tests (we have our own), assets, docker, nix, web stuff
  - Hermes wins on conflicts (overwrites my stubs)
  - No import transforms — sys.path makes bare imports work
  - Create alias shims for renamed modules
"""
import shutil
import sys
from pathlib import Path

HERMES = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\NousResearch_hermes-agent\repo")
VC     = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\python\vectorcode")

# Directories to copy entirely (overwrites VC stubs, except for files we explicitly preserve)
DIRS_TO_COPY = ["agent", "gateway", "tools", "hermes_cli", "plugins", "skills",
                "acp_adapter", "cron", "scripts"]

# Files in VC we MUST preserve (don't overwrite)
PRESERVE = {
    "tools/registry.py",      # my registry — Hermes uses it as alternative
    # Don't preserve any others — let Hermes win
}

# Root-level Hermes .py files to copy
ROOT_FILES = [
    "run_agent.py", "model_tools.py", "hermes_state.py", "hermes_logging.py",
    "hermes_time.py", "hermes_constants.py", "utils.py",
    "trajectory_compressor.py", "toolset_distributions.py", "toolsets.py",
    "mcp_serve.py", "mini_swe_runner.py", "batch_runner.py", "rl_cli.py",
]

# Skip these subdirs even when copying parent dirs
SKIP_DIRS = {"__pycache__", "tests", "test", "neutts_samples", "browser_providers",
             "platforms", "builtin_hooks"}

stats = {"copied": 0, "skipped": 0, "preserved": 0, "bytes": 0}

def should_skip(rel: Path) -> bool:
    parts = rel.parts
    for skip in SKIP_DIRS:
        if skip in parts:
            return True
    return False

def copy_file(src: Path, dst: Path, rel_label: str) -> None:
    if rel_label in PRESERVE and dst.exists():
        stats["preserved"] += 1
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    stats["copied"] += 1
    stats["bytes"] += src.stat().st_size

# 1. Copy named directories
for d in DIRS_TO_COPY:
    src_dir = HERMES / d
    if not src_dir.exists():
        print(f"  [skip] {d} — not in Hermes")
        continue
    dst_dir = VC / d
    py_files = [p for p in src_dir.rglob("*.py") if not should_skip(p.relative_to(src_dir))]
    print(f"  [{d}/] {len(py_files)} .py files")
    for py in py_files:
        rel = py.relative_to(src_dir)
        rel_label = f"{d}/{rel}".replace("\\", "/")
        copy_file(py, dst_dir / rel, rel_label)
    # Also copy non-py asset files inside the dir (json, md, yaml)
    for ext in (".json", ".yaml", ".yml", ".toml", ".md", ".txt"):
        for asset in src_dir.rglob(f"*{ext}"):
            if should_skip(asset.relative_to(src_dir)):
                continue
            rel = asset.relative_to(src_dir)
            (dst_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, dst_dir / rel)
            stats["copied"] += 1

# 2. Copy root files
print("  [root] Hermes top-level Python files")
for f in ROOT_FILES:
    src = HERMES / f
    if not src.exists():
        print(f"    [skip] {f}")
        continue
    copy_file(src, VC / f, f)

# 3. Print summary
print()
print(f"  Copied:    {stats['copied']} files")
print(f"  Preserved: {stats['preserved']} files")
print(f"  Bytes:     {stats['bytes']:,} ({stats['bytes']/1024/1024:.1f} MB)")
