"""
Port the 5 OpenCLI skills into VectorCode as personalized VECTOR skills.

Source: github/OpenCLI/skills/opencli-{adapter-author,autofix,browser,usage,smart-search}/
Target: vectorcode/skills/vc-opencli-{...}/SKILL.md
"""
from __future__ import annotations
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "github" / "OpenCLI" / "skills"
DST = ROOT / "vectorcode" / "skills"

SKILLS = [
    "opencli-adapter-author",
    "opencli-autofix",
    "opencli-browser",
    "opencli-usage",
    "smart-search",
]

REPLACEMENTS = [
    (r"\bOpenCLI\b", "VECTOR-OpenCLI"),
    (r"\bopencli\b", "vc-opencli"),  # lowercase command prefix
    (r"@jackwener/opencli", "@vector/opencli"),
    (r"\bClaude Code\b", "VectorCode"),
    (r"\bCursor\b(?!\s+/)", "VectorCode"),
]


def personalize(text: str, src_name: str) -> str:
    out = text
    for pattern, repl in REPLACEMENTS:
        out = re.sub(pattern, repl, out)
    header = (
        f"<!-- VECTOR-INGESTED ASSET\n"
        f"  Source: github/OpenCLI/skills/{src_name}/SKILL.md\n"
        f"  Personalized for VECTOR runtime — wraps existing browser_tool/opencli_tool.\n"
        f"  Owner: Arghyadeep Deb\n"
        f"  Ingested: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"-->\n\n"
    )
    return header + out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not SRC.exists():
        print(f"ERROR: source not found: {SRC}")
        return 1

    ported = 0
    for slug in SKILLS:
        src_dir = SRC / slug
        if not src_dir.is_dir():
            print(f"  [skip] {slug} not found")
            continue

        # New name: prefix with vc-, but smart-search stays smart-search since it's generic
        new_slug = f"vc-{slug}" if not slug.startswith("opencli-") else f"vc-{slug}"
        if slug == "smart-search":
            new_slug = "vc-smart-search"

        dst_dir = DST / new_slug
        dst_dir.mkdir(parents=True, exist_ok=True)

        for src_file in src_dir.rglob("*"):
            if src_file.is_dir():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            if src_file.suffix.lower() in {".md", ".markdown"}:
                try:
                    text = src_file.read_text(encoding="utf-8")
                    dst_file.write_text(personalize(text, slug), encoding="utf-8")
                except Exception as e:
                    print(f"  [warn] {src_file}: {e}")
                    shutil.copy2(src_file, dst_file)
            else:
                shutil.copy2(src_file, dst_file)
        ported += 1
        print(f"  [ok] {slug} -> {new_slug}/")

    print(f"\nPorted {ported} OpenCLI skills.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
