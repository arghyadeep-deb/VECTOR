#!/usr/bin/env python3
"""
scripts/build_skills_manifest.py - Session 1.5

Scans vectorcode/skills/, parses every SKILL.md, outputs data/skills_manifest.json.
Handles two patterns:
  1. Simple: vectorcode/skills/<skill-id>/SKILL.md
  2. Meta (vc-gs-skill): vectorcode/skills/vc-gs-skill/<sub>/SKILL.md -> "vc-gs-skill/<sub>"

Usage: python scripts/build_skills_manifest.py [--output data/skills_manifest.json]
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKILLS_DIR = ROOT / "vectorcode" / "skills"
DEFAULT_OUTPUT = ROOT / "data" / "skills_manifest.json"

CATEGORY_MAP = {
    "vc-sec-": "security",
    "vc-gs-": "general",
    "vc-ec-": "execution",
    "vc-cv-": "compress",
    "vc-cmp-": "compute",
    "vc-ag-": "agent",
    "vc-os-": "os",
    "vc-ui-": "ui",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".slate", ".opencode",
    ".openclaw", ".vector-cache", ".gbrain", ".cursor", ".kiro", ".factory",
    ".agents", "test", "fixtures", "docs", "model-overlays", "openclaw",
}


def get_category(skill_id: str) -> str:
    for prefix, cat in CATEGORY_MAP.items():
        if skill_id.startswith(prefix):
            return cat
    return "other"


def parse_skill_md(skill_md: Path) -> dict:
    try:
        content = skill_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}

    # Title: first H1 or H2
    m = re.search(r"^#{1,2}\s+(.+)$", content, re.MULTILINE)
    name = m.group(1).strip() if m else skill_md.parent.name

    # Description: first 3 non-heading lines after title
    lines = content.splitlines()
    desc, past = [], False
    for line in lines:
        if not past and re.match(r"^#{1,2}\s+", line):
            past = True
            continue
        if past and line.strip() and not line.startswith("#"):
            desc.append(line.strip())
            if len(desc) >= 3:
                break
    description = " ".join(desc)[:300]

    # Triggers: backtick-quoted terms, then headings as fallback
    triggers = []
    for pat in [r"`([^`]{3,50})`", r"^#+\s+(.{3,50})$"]:
        for hit in re.findall(pat, content, re.MULTILINE)[:8]:
            t = hit.strip().lower()
            if t not in triggers:
                triggers.append(t)
        if triggers:
            break

    has_scripts = any(
        f.suffix in {".py", ".sh", ".js", ".ts"}
        for f in skill_md.parent.iterdir()
        if f.is_file()
    )

    return {
        "name": name,
        "description": description,
        "triggers": triggers[:10],
        "has_scripts": has_scripts,
    }


def scan_skills(skills_dir: Path) -> dict:
    manifest: dict = {}

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        if skill_dir.name in SKIP_DIRS:
            continue

        skill_id = skill_dir.name
        category = get_category(skill_id)

        # Pattern 1: SKILL.md at root
        root_md = skill_dir / "SKILL.md"
        if root_md.exists():
            meta = parse_skill_md(root_md)
            if meta:
                manifest[skill_id] = {
                    "skill_id": skill_id,
                    "category": category,
                    "skill_md_path": str(root_md.relative_to(ROOT)),
                    **meta,
                }

        # Pattern 2: sub-skill dirs (vc-gs-skill pattern)
        for sub in sorted(skill_dir.iterdir()):
            if not sub.is_dir() or sub.name in SKIP_DIRS or sub.name.startswith("."):
                continue
            sub_md = sub / "SKILL.md"
            if sub_md.exists():
                sub_id = f"{skill_id}/{sub.name}"
                meta = parse_skill_md(sub_md)
                if meta:
                    manifest[sub_id] = {
                        "skill_id": sub_id,
                        "category": category,
                        "skill_md_path": str(sub_md.relative_to(ROOT)),
                        **meta,
                    }

    return manifest


def main() -> None:
    output_path = (
        Path(sys.argv[sys.argv.index("--output") + 1])
        if "--output" in sys.argv
        else DEFAULT_OUTPUT
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Scanning {SKILLS_DIR} ...")
    manifest = scan_skills(SKILLS_DIR)

    by_cat: dict[str, int] = {}
    for e in manifest.values():
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1

    tmp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent,
            prefix=f".{output_path.name}.", suffix=".tmp", delete=False,
        ) as output:
            tmp_name = output.name
            json.dump(manifest, output, indent=2, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp_name, output_path)
        tmp_name = None
    finally:
        if tmp_name is not None:
            Path(tmp_name).unlink(missing_ok=True)

    print(f"Manifest written to {output_path}")
    print(f"Total skills indexed: {len(manifest)}")
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat:12s}: {n}")


if __name__ == "__main__":
    main()
