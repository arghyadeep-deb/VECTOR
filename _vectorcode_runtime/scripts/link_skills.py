"""
Port of mattpocock/skills scripts/link-skills.sh — Windows-compatible.
Copies (or re-copies) all skills from a skills repo into ~/.claude/skills/.
Skips deprecated/ subfolder by default.

Usage:
    python scripts/link_skills.py <skills_repo_path>
    python scripts/link_skills.py --list   # list installed skills
"""
import sys
import shutil
import argparse
from pathlib import Path

DEST = Path.home() / ".claude" / "skills"


def list_skills():
    if not DEST.exists():
        print("No skills installed yet.")
        return
    skills = sorted(
        p.name for p in DEST.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    )
    print(f"Installed skills ({len(skills)}):")
    for s in skills:
        desc = ""
        skill_md = DEST / s / "SKILL.md"
        for line in skill_md.read_text(encoding="utf-8").splitlines():
            if line.startswith("description:"):
                desc = line.replace("description:", "").strip()
                if desc.startswith('"') and desc.endswith('"'):
                    desc = desc[1:-1]
                break
        print(f"  {s:<40} {desc[:80]}")


def link_skills(repo_path: Path, include_deprecated: bool = False,
                include_in_progress: bool = True, include_personal: bool = True):
    if not repo_path.exists():
        print(f"ERROR: {repo_path} does not exist")
        sys.exit(1)

    DEST.mkdir(parents=True, exist_ok=True)
    skills_root = repo_path / "skills"
    if not skills_root.exists():
        print(f"ERROR: {skills_root} not found — is this a skills repo?")
        sys.exit(1)

    copied = []
    skipped = []

    skip_buckets = set()
    if not include_deprecated:
        skip_buckets.add("deprecated")
    if not include_in_progress:
        skip_buckets.add("in-progress")
    if not include_personal:
        skip_buckets.add("personal")

    for skill_md in sorted(skills_root.rglob("SKILL.md")):
        # Get the bucket (engineering/, productivity/, etc.)
        rel = skill_md.relative_to(skills_root)
        bucket = rel.parts[0]
        if bucket in skip_buckets:
            skipped.append(skill_md.parent.name)
            continue

        src = skill_md.parent
        name = src.name
        dst = DEST / name

        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        copied.append(name)

    print(f"\nSkills installed to {DEST}")
    print(f"  Copied  : {len(copied)}")
    for s in copied:
        print(f"    + {s}")
    if skipped:
        print(f"  Skipped : {len(skipped)} ({', '.join(sorted(skip_buckets))})")


def main():
    parser = argparse.ArgumentParser(description="Install Claude Code skills")
    parser.add_argument("repo", nargs="?", help="Path to skills repo")
    parser.add_argument("--list", action="store_true", help="List installed skills")
    parser.add_argument("--include-deprecated", action="store_true")
    parser.add_argument("--skip-in-progress", action="store_true")
    parser.add_argument("--skip-personal", action="store_true")
    args = parser.parse_args()

    if args.list:
        list_skills()
        return

    if not args.repo:
        parser.print_help()
        sys.exit(1)

    link_skills(
        Path(args.repo),
        include_deprecated=args.include_deprecated,
        include_in_progress=not args.skip_in_progress,
        include_personal=not args.skip_personal,
    )


if __name__ == "__main__":
    main()
