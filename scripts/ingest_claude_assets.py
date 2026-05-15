"""
Ingest Claude assets (skills/agents/commands/hooks/rules) into VectorCode.

What this script does:
  1. Reads every file in .claude/{skills,agents,commands,hooks,rules}
  2. Personalizes content for VECTOR/VectorCode (replaces Claude references,
     adds vc- prefix, injects VECTOR context)
  3. Writes to vectorcode/{skills,agents,commands,hooks,rules}
  4. Generates a manifest of what was ingested

Run:
    python scripts/ingest_claude_assets.py           # dry run — shows plan
    python scripts/ingest_claude_assets.py --apply   # actually copy + transform
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_CLAUDE = ROOT / ".claude"
DST_VC = ROOT / "vectorcode"

# Subfolders to ingest (Claude → VectorCode)
INGEST_MAP = {
    "skills": "skills",        # .claude/skills → vectorcode/skills
    "agents": "agents",        # .claude/agents → vectorcode/agents
    "commands": "commands",    # .claude/commands → vectorcode/commands
    "hooks": "hooks",          # .claude/hooks → vectorcode/hooks
    "rules": "rules",          # .claude/rules → vectorcode/rules
}

# Existing VectorCode skill prefix
VC_PREFIX = "vc-"

# Personalization replacements (case-insensitive where appropriate)
TEXT_REPLACEMENTS = [
    # Branding
    (r"\bClaude Code\b", "VectorCode"),
    (r"\bClaude\.ai\b", "VECTOR.ai"),
    (r"\bClaude API\b", "VectorCode API (local Ollama)"),
    (r"\bAnthropic API\b", "Local Ollama"),
    (r"\bclaude-sonnet[^\s\"`)]*", "vector-coder"),
    (r"\bclaude-opus[^\s\"`)]*", "vector-chairman"),
    (r"\bclaude-haiku[^\s\"`)]*", "vector-fast"),
    # Folder paths
    (r"\.claude/skills/", "vectorcode/skills/"),
    (r"\.claude/agents/", "vectorcode/agents/"),
    (r"\.claude/commands/", "vectorcode/commands/"),
    (r"\.claude/hooks/", "vectorcode/hooks/"),
    (r"\.claude/rules/", "vectorcode/rules/"),
    (r"`\.claude`", "`vectorcode`"),
    # Identity (keep "Claude" only when discussing the model itself in technical
    # benchmark context — most refs are about the agent/tool, which becomes VECTOR)
]

# Header injected at top of every personalized markdown asset
VECTOR_HEADER = """<!-- VECTOR-INGESTED ASSET
  Source: .claude/{src_subfolder}/{src_name}
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: {timestamp}
-->

"""


# ── Filename personalization ────────────────────────────────────────────────


def _personalize_skill_name(name: str) -> str:
    """Add vc- prefix to skill names that don't already have it."""
    stem = Path(name).stem
    suffix = Path(name).suffix
    if stem.startswith("vc-") or stem.startswith("vector-"):
        return name
    return f"{VC_PREFIX}{stem}{suffix}"


def _personalize_agent_name(name: str) -> str:
    """Agents already mostly have 'vector-' or descriptive names; standardize."""
    stem = Path(name).stem
    suffix = Path(name).suffix
    if stem.startswith("vector-") or stem.startswith("vc-"):
        return name
    return f"vector-{stem}{suffix}"


def _personalize_command_name(name: str) -> str:
    """Commands keep their names — they're invoked as /command-name."""
    return name


def _personalize_hook_name(name: str) -> str:
    """Hooks keep filenames; they're imported by path."""
    return name


def _personalize_rule_name(name: str) -> str:
    """Rules keep filenames; they're imported by path."""
    return name


PERSONALIZE_NAME = {
    "skills": _personalize_skill_name,
    "agents": _personalize_agent_name,
    "commands": _personalize_command_name,
    "hooks": _personalize_hook_name,
    "rules": _personalize_rule_name,
}


# ── Content personalization ─────────────────────────────────────────────────


def personalize_text(text: str) -> str:
    """Apply VECTOR-specific text transformations."""
    out = text
    for pattern, replacement in TEXT_REPLACEMENTS:
        out = re.sub(pattern, replacement, out)
    return out


def personalize_file(src: Path, dst: Path, src_subfolder: str) -> str:
    """Read source, personalize content, return transformed text. Adds header for .md/.py."""
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Binary file — copy bytes as-is
        return ""

    personalized = personalize_text(text)

    if src.suffix.lower() in {".md", ".markdown"}:
        header = VECTOR_HEADER.format(
            src_subfolder=src_subfolder,
            src_name=src.name,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        if not personalized.lstrip().startswith("<!-- VECTOR-INGESTED"):
            personalized = header + personalized
    elif src.suffix.lower() == ".py":
        # Add a short docstring header marker — only if not already present
        marker = "# VECTOR-INGESTED — personalized for VectorCode runtime"
        if marker not in personalized:
            personalized = f"{marker}\n# Source: .claude/{src_subfolder}/{src.name}\n\n{personalized}"

    return personalized


# ── Recursive ingestion ─────────────────────────────────────────────────────


def ingest_subfolder(subfolder: str, dst_subfolder: str, apply: bool, manifest: list) -> int:
    """Walk every file in .claude/<subfolder>/ and write to vectorcode/<dst_subfolder>/.
    Returns count of files ingested."""
    src_root = SRC_CLAUDE / subfolder
    dst_root = DST_VC / dst_subfolder
    if not src_root.exists():
        print(f"  [skip] {src_root} does not exist")
        return 0

    name_fn = PERSONALIZE_NAME[subfolder]
    count = 0

    for src_file in src_root.rglob("*"):
        if src_file.is_dir():
            continue
        # Skip OS junk
        if src_file.name in {".DS_Store", "Thumbs.db"}:
            continue

        # Compute destination relative path
        rel = src_file.relative_to(src_root)
        # Personalize the leaf filename
        leaf = name_fn(rel.name)
        dst_rel = rel.parent / leaf
        dst_file = dst_root / dst_rel

        # Skip if destination identical and already ingested (idempotent)
        if dst_file.exists():
            try:
                if dst_file.read_bytes() == src_file.read_bytes():
                    continue
            except Exception:
                pass

        manifest.append({
            "src": str(src_file.relative_to(ROOT)).replace("\\", "/"),
            "dst": str(dst_file.relative_to(ROOT)).replace("\\", "/"),
            "kind": subfolder,
            "size_bytes": src_file.stat().st_size,
        })

        if apply:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            if src_file.suffix.lower() in {".md", ".markdown", ".py"}:
                personalized = personalize_file(src_file, dst_file, subfolder)
                if personalized:
                    dst_file.write_text(personalized, encoding="utf-8")
                else:
                    shutil.copy2(src_file, dst_file)
            else:
                # Binary or unknown — copy raw
                shutil.copy2(src_file, dst_file)

        count += 1

    return count


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest Claude assets into VectorCode")
    ap.add_argument("--apply", action="store_true", help="Actually write files (default: dry run)")
    args = ap.parse_args()

    # Force UTF-8 output on Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("VECTOR -- Claude -> VectorCode asset ingestion")
    print("=" * 60)
    print(f"Source: {SRC_CLAUDE}")
    print(f"Target: {DST_VC}")
    print(f"Mode:   {'APPLY' if args.apply else 'DRY RUN'}")
    print()

    if not SRC_CLAUDE.exists():
        print(f"ERROR: {SRC_CLAUDE} not found.")
        return 1

    manifest: list = []
    totals: dict[str, int] = {}

    for src_sub, dst_sub in INGEST_MAP.items():
        print(f"[{src_sub:>8}] scanning .claude/{src_sub}/ -> vectorcode/{dst_sub}/ ...")
        n = ingest_subfolder(src_sub, dst_sub, args.apply, manifest)
        totals[src_sub] = n
        print(f"           {n} files {'ingested' if args.apply else 'planned'}")

    print()
    print("Summary:")
    for k, v in totals.items():
        print(f"  {k:>8}: {v}")
    print(f"  {'TOTAL':>8}: {sum(totals.values())}")

    # Write manifest
    if args.apply:
        manifest_path = DST_VC / "INGESTION_MANIFEST.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "totals": totals,
                    "files": manifest,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nManifest written: {manifest_path}")
        print("✅ Ingestion complete.")
    else:
        print("\n(dry run — re-run with --apply to copy files)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
