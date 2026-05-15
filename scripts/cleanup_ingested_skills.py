"""
Cleanup pass for vectorcode/skills/ after Claude ingestion.

Fixes two naming issues:
  1. Skill folders containing SKILL.md should have the folder renamed (not
     the SKILL.md itself). Files like LICENSE.txt, scripts/, etc. inside a
     skill folder must keep their original names.
  2. Top-level skill folders named `claude-*` should be renamed to `vc-*`
     to match the rest of the project's vc- convention.

Run:
    python scripts/cleanup_ingested_skills.py            # dry run
    python scripts/cleanup_ingested_skills.py --apply    # actually rename
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "vectorcode" / "skills"


def collect_renames() -> tuple[list[tuple[Path, Path]], list[Path]]:
    """Find rename candidates and merge candidates."""
    renames: list[tuple[Path, Path]] = []
    folder_renames: list[tuple[Path, Path]] = []

    # 1) Inside any skill folder (folder containing SKILL.md or vc-SKILL.md),
    #    revert vc-PREFIXED leaf files to their original names.
    for skill_folder in SKILLS.iterdir():
        if not skill_folder.is_dir():
            continue
        # Check if this looks like a skill folder (has SKILL.md somewhere)
        skill_md_present = any(
            p.name in ("SKILL.md", "vc-SKILL.md") for p in skill_folder.rglob("*") if p.is_file()
        )
        if not skill_md_present:
            continue

        for f in skill_folder.rglob("*"):
            if f.is_file() and f.name.startswith("vc-"):
                # Strip the vc- prefix
                new_name = f.name[len("vc-"):]
                target = f.with_name(new_name)
                renames.append((f, target))

    # 2) Top-level folders named claude-* should be renamed to vc-claude-* (preserves heritage)
    for skill_folder in SKILLS.iterdir():
        if skill_folder.is_dir() and skill_folder.name.startswith("claude-"):
            new_name = "vc-" + skill_folder.name  # vc-claude-api, vc-claude-devfleet
            target = SKILLS / new_name
            folder_renames.append((skill_folder, target))

    return renames, folder_renames


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print(f"Cleanup pass on: {SKILLS}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print()

    renames, folder_renames = collect_renames()

    print(f"== File renames (strip vc- prefix from files inside skill folders): {len(renames)} ==")
    for src, dst in renames[:5]:
        print(f"  {src.relative_to(SKILLS)} -> {dst.relative_to(SKILLS)}")
    if len(renames) > 5:
        print(f"  ... and {len(renames) - 5} more")

    print()
    print(f"== Folder renames (claude-* -> vc-claude-*): {len(folder_renames)} ==")
    for src, dst in folder_renames:
        print(f"  {src.name} -> {dst.name}")

    if args.apply:
        # Apply file renames first (so paths still exist before folder rename)
        for src, dst in renames:
            if dst.exists():
                # If dst exists (e.g. SKILL.md was already there), prefer keeping the
                # vc- prefixed (just-ingested) version and skip the duplicate
                if src.read_bytes() != dst.read_bytes():
                    # Different content — keep the freshly-personalized one
                    dst.unlink()
                    src.rename(dst)
                else:
                    src.unlink()  # identical, just drop the duplicate
            else:
                src.rename(dst)

        # Apply folder renames
        for src, dst in folder_renames:
            if dst.exists():
                # Merge contents
                for item in src.rglob("*"):
                    if item.is_file():
                        rel = item.relative_to(src)
                        target_file = dst / rel
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        if not target_file.exists():
                            shutil.move(str(item), str(target_file))
                shutil.rmtree(src, ignore_errors=True)
            else:
                src.rename(dst)

        print()
        print("✅ Cleanup complete.")
    else:
        print()
        print("(dry run — re-run with --apply to rename)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
