"""Bulk copy Ruflo repo into VectorCode preserving structure.

Strategy:
  - Copy Ruflo into vectorcode/ruflo/ (TS stays as TS — they're not running yet)
  - Skip vendored npm bundles (@claude-flow/), node_modules, .git, dist
  - Copy: ruflo/, v2/, v3/, agents/, plugins/, plugin/, scripts/, bin/, docs/
  - Copy .ts, .js, .md, .yaml, .yml, .json, .toml files
  - Skip: lock files, build artifacts, large binaries
"""
import shutil
from pathlib import Path

RUFLO = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\ruvnet_ruflo\repo")
VC    = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\ruflo")

# Directories to copy entirely
DIRS_TO_COPY = ["ruflo", "v2", "v3", "agents", "plugins", "plugin", "scripts", "bin", "docs", "tests"]

# Top-level files to copy
ROOT_FILES = ["README.md", "CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "SECURITY.md",
              "package.json", "tsconfig.json"]

# Skip these subdirs (vendored deps, build artifacts)
SKIP_DIRS = {"node_modules", "@claude-flow", "dist", "build", ".git", ".next",
             "coverage", "__pycache__", ".cache", "out", "_internal"}

# Allowed file extensions
ALLOWED_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
               ".md", ".yaml", ".yml", ".json", ".toml",
               ".py", ".sh", ".rs", ".html", ".css"}

# Skip these specific files
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock"}

stats = {"copied": 0, "skipped": 0, "bytes": 0}


def should_skip_dir(rel: Path) -> bool:
    return any(skip in rel.parts for skip in SKIP_DIRS)


def should_copy_file(p: Path) -> bool:
    if p.name in SKIP_FILES:
        return False
    if p.suffix.lower() not in ALLOWED_EXT:
        return False
    if p.stat().st_size > 5 * 1024 * 1024:  # skip files > 5 MB
        return False
    return True


def copy_dir(src_root: Path, dst_root: Path, label: str) -> None:
    if not src_root.exists():
        print(f"  [skip] {label} — not present")
        return
    files = []
    for p in src_root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src_root)
        if should_skip_dir(rel):
            stats["skipped"] += 1
            continue
        if not should_copy_file(p):
            stats["skipped"] += 1
            continue
        files.append((p, rel))
    print(f"  [{label}] {len(files)} files")
    for src, rel in files:
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        stats["copied"] += 1
        stats["bytes"] += src.stat().st_size


# 1. Copy named directories
for d in DIRS_TO_COPY:
    src_dir = RUFLO / d
    dst_dir = VC / d
    copy_dir(src_dir, dst_dir, d)

# 2. Copy root files
print("  [root]")
for f in ROOT_FILES:
    src = RUFLO / f
    if not src.exists():
        continue
    dst = VC / f
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    stats["copied"] += 1
    stats["bytes"] += src.stat().st_size

print()
print(f"  Copied:  {stats['copied']} files")
print(f"  Skipped: {stats['skipped']} files (vendored / unsupported)")
print(f"  Bytes:   {stats['bytes']:,} ({stats['bytes']/1024/1024:.1f} MB)")
