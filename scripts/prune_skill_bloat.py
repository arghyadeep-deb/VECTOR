"""
Trim bloat from vectorcode/skills/ by keeping only SKILL.md + small markdown
siblings under 100KB. Removes binaries, screenshots, large fixtures, scripts/,
assets/, etc. that ballooned the skills tree during mass-absorption.

Run:
    python scripts/prune_skill_bloat.py            # dry run (reports)
    python scripts/prune_skill_bloat.py --apply    # actually trim
"""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "vectorcode" / "skills"
MAX_SIBLING_BYTES = 100_000  # 100 KB max per sibling file


def trim_folder(skill_dir: Path, apply: bool) -> tuple[int, int]:
    """Remove anything that's not SKILL.md or a small markdown file.
    Returns (files_kept, bytes_removed).
    """
    bytes_removed = 0
    kept = 0
    for entry in list(skill_dir.iterdir()):
        if entry.name == "SKILL.md":
            kept += 1
            continue
        if entry.is_dir():
            # Recurse — keep small md files, drop the rest
            sub_bytes_removed = _trim_subdir(entry, apply)
            bytes_removed += sub_bytes_removed
            # If empty after pruning, remove the dir
            try:
                if not any(entry.iterdir()):
                    if apply:
                        entry.rmdir()
            except Exception:
                pass
            continue
        # Top-level non-SKILL file
        try:
            size = entry.stat().st_size
        except OSError:
            continue
        suffix = entry.suffix.lower()
        if suffix in {".md", ".markdown", ".txt"} and size < MAX_SIBLING_BYTES:
            kept += 1
            continue
        # Drop it
        bytes_removed += size
        if apply:
            try:
                entry.unlink()
            except Exception:
                pass
    return kept, bytes_removed


def _trim_subdir(d: Path, apply: bool) -> int:
    """Recursively trim a sibling folder. Keep small markdown, drop everything else."""
    bytes_removed = 0
    for entry in list(d.iterdir()):
        if entry.is_dir():
            bytes_removed += _trim_subdir(entry, apply)
            try:
                if not any(entry.iterdir()):
                    if apply:
                        entry.rmdir()
            except Exception:
                pass
            continue
        try:
            size = entry.stat().st_size
        except OSError:
            continue
        suffix = entry.suffix.lower()
        if suffix in {".md", ".markdown", ".txt"} and size < MAX_SIBLING_BYTES:
            continue
        bytes_removed += size
        if apply:
            try:
                entry.unlink()
            except Exception:
                pass
    return bytes_removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not SKILLS.exists():
        print(f"ERROR: {SKILLS} not found")
        return 1

    total_removed = 0
    folders_processed = 0
    for d in SKILLS.iterdir():
        if not d.is_dir():
            continue
        folders_processed += 1
        _, removed = trim_folder(d, args.apply)
        total_removed += removed

    print(f"Processed {folders_processed} skill folders")
    print(f"{'Removed' if args.apply else 'Would remove'}: {total_removed/1024/1024:.1f} MB")
    if not args.apply:
        print("(dry run — re-run with --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
