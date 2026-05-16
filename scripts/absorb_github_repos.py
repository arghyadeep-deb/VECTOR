"""
Mass-port all SKILL.md files from GitHub/<repo>/repo/ trees into
vectorcode/skills/ with VECTOR personalization.

For each repo in PORT_TARGETS:
  1. Recursively find all SKILL.md files
  2. Determine a unique vc-* slug from the parent folder
  3. Personalize content (Claude -> VECTOR, opus -> vector-chairman, etc.)
  4. Write to vectorcode/skills/<slug>/SKILL.md (or skip if already exists)
  5. Copy any siblings (LICENSE, references/, scripts/, etc.) verbatim

After porting, run with --delete to remove the source repo trees.
"""
from __future__ import annotations
import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB_DIR = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub")
DST = ROOT / "vectorcode" / "skills"
AGENTS_DST = ROOT / "vectorcode" / "agents"

# Repos to absorb skills from. 'agents' flag means port markdown files
# directly to vectorcode/agents/ instead of vectorcode/skills/.
PORT_TARGETS: list[dict] = [
    {"name": "mukul975_Anthropic-Cybersecurity-Skills", "max_files": 800, "prefix": "sec-"},
    {"name": "nextlevelbuilder_ui-ux-pro-max-skill", "max_files": 50, "prefix": "ui-"},
    {"name": "sickn33_antigravity-awesome-skills", "max_files": 1500, "prefix": "ag-"},
    {"name": "forrestchang_andrej-karpathy-skills", "max_files": 20, "prefix": "kp-"},
    {"name": "kepano_obsidian-skills", "max_files": 20, "prefix": "obs-"},
    {"name": "gsd-build_get-shit-done", "max_files": 30, "prefix": "gsd-"},
    {"name": "JuliusBrussee_caveman", "max_files": 20, "prefix": "cv-"},
    {"name": "msitarzewski_agency-agents", "max_files": 200, "prefix": "ag-", "agents": True},
    {"name": "K-Dense-AI_karpathy", "max_files": 200, "prefix": "kpsci-"},
    {"name": "affaan-m_everything-claude-code", "max_files": 250, "prefix": "ec-"},
    {"name": "theneoai_awesome-skills", "max_files": 1000, "prefix": "as-"},
    {"name": "ComposioHQ_awesome-claude-skills", "max_files": 800, "prefix": "cmp-"},
    {"name": "VoltAgent_awesome-agent-skills", "max_files": 1500, "prefix": "va-"},
    {"name": "instavm_open-skills", "max_files": 30, "prefix": "os-"},
    {"name": "garrytan_gstack", "max_files": 50, "prefix": "gs-"},
]

# Repos to just delete (no porting — reference material, awesome-lists,
# already-absorbed, or no useful artifacts).
DELETE_ONLY: list[str] = [
    "anthropics_claude-code",        # already absorbed (commit e9b1dba1)
    "anthropics_skills",             # already in vectorcode/skills/ (pdf, docx, etc.)
    "anthropics_claude-plugins-official",
    "obra_superpowers",              # already in vectorcode/skills/
    "addyosmani_agent-skills",       # already in vectorcode/skills/
    "NousResearch_hermes-agent",     # already in vectorcode/src/comms/
    "ruvnet_vector",                  # absorbed into vectorcode/src (swarm, neural, reasoning_bank)
    "lyogavin_airllm",               # already in integrations/airllm/
    "kyegomez_OpenMythos",           # already in integrations/openmythos/
    "tirth8205_code-review-graph",   # already in integrations/code_review_graph/
    "hesreallyhim_awesome-claude-code",
    "asgeirtj_system_prompts_leaks",
    "public-apis_public-apis",       # already in integrations/public_apis_catalog.py
    "Gitlawb_openclaude",
    "danny-avila_LibreChat",
    "openclaw_openclaw",
    "Comfy-Org_ComfyUI",
    "Comfy-Org_ComfyUI-Manager",
    "ValueCell-ai_valuecell",
    "she-llac_claude-counter",
    "JCodesMore_ai-website-cloner-template",
    "abhigyanpatwari_GitNexus",
]

# ── Personalization ──────────────────────────────────────────────────────────

REPLACEMENTS = [
    (r"\bClaude Code\b", "VectorCode"),
    (r"\bClaude\.ai\b", "VECTOR.ai"),
    (r"\bclaude-sonnet[^\s\"`)]*", "vector-coder"),
    (r"\bclaude-opus[^\s\"`)]*", "vector-chairman"),
    (r"\bclaude-haiku[^\s\"`)]*", "vector-fast"),
    (r"\bAnthropic\s+API\b", "Local Ollama"),
    (r"\bClaude\b(?!-(?:sonnet|opus|haiku|3))", "VECTOR"),
    (r"\.claude/skills/", "vectorcode/skills/"),
    (r"\.claude/agents/", "vectorcode/agents/"),
    (r"\.claude/", "vectorcode/"),
    (r"model:\s*opus", "model: vector-chairman"),
    (r"model:\s*sonnet", "model: vector-coder"),
    (r"model:\s*haiku", "model: vector-fast"),
]


def personalize(text: str, src_path: str) -> str:
    out = text
    for pattern, repl in REPLACEMENTS:
        out = re.sub(pattern, repl, out)

    if "<!-- VECTOR-INGESTED" not in out:
        header = (
            f"<!-- VECTOR-INGESTED ASSET\n"
            f"  Source: {src_path}\n"
            f"  Personalized for VECTOR runtime — local Ollama, no paid APIs.\n"
            f"  Owner: Arghyadeep Deb\n"
            f"  Ingested: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
            f"-->\n\n"
        )
        out = header + out
    return out


# ── Slug derivation ──────────────────────────────────────────────────────────


def slugify(name: str) -> str:
    """Convert a folder/file name to a safe vc-skill slug."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def find_skills(repo_root: Path) -> list[Path]:
    """Find every SKILL.md (and *.skill.md) under repo_root."""
    return list(repo_root.rglob("SKILL.md")) + list(repo_root.rglob("*.skill.md"))


def find_agents(repo_root: Path) -> list[Path]:
    """Find every agent-style markdown file (no SKILL.md)."""
    out: list[Path] = []
    for f in repo_root.rglob("*.md"):
        if f.name.lower() in {"readme.md", "license.md", "contributing.md", "skill.md", "changelog.md"}:
            continue
        # Detect agent-style by looking for frontmatter `name:` or `description:`
        try:
            head = f.read_text(encoding="utf-8")[:2000]
        except Exception:
            continue
        if re.search(r"^---\s*$.*?(?:\bname:|\bdescription:|\btools:)", head, re.MULTILINE | re.DOTALL):
            out.append(f)
    return out


def port_skill(src: Path, repo_root: Path, prefix: str, dst_dir: Path) -> str | None:
    """Copy + personalize one skill folder. Returns the destination slug, or None if skipped."""
    parent = src.parent
    raw_slug = parent.name if parent != repo_root else src.stem
    slug = "vc-" + prefix + slugify(raw_slug)

    target_dir = dst_dir / slug
    target_skill = target_dir / "SKILL.md"

    # Skip if a skill with this exact slug already exists (in either folder or
    # top-level *.md form)
    if target_skill.exists():
        return None
    if (dst_dir / f"{slug}.md").exists():
        return None
    # Also skip if a non-prefixed equivalent exists (e.g. vc-coder.md from prior absorption)
    plain_slug = "vc-" + slugify(raw_slug)
    if (dst_dir / plain_slug / "SKILL.md").exists() or (dst_dir / f"{plain_slug}.md").exists():
        return None

    target_dir.mkdir(parents=True, exist_ok=True)

    # Personalize SKILL.md itself
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        shutil.copy2(src, target_skill)
        return slug
    src_rel = str(src.relative_to(GITHUB_DIR.parent)).replace("\\", "/")
    target_skill.write_text(personalize(text, src_rel), encoding="utf-8")

    # Copy siblings (references/, scripts/, LICENSE, etc.)
    for sibling in parent.iterdir():
        if sibling == src or sibling.name.lower() == "skill.md":
            continue
        sib_target = target_dir / sibling.name
        try:
            if sibling.is_dir():
                if not sib_target.exists():
                    shutil.copytree(sibling, sib_target, dirs_exist_ok=False)
            elif sibling.is_file():
                if sibling.suffix.lower() in {".md", ".markdown", ".txt"} and sibling.stat().st_size < 200_000:
                    try:
                        sibling_text = sibling.read_text(encoding="utf-8")
                        sib_target.write_text(personalize(sibling_text, str(sibling)), encoding="utf-8")
                    except Exception:
                        shutil.copy2(sibling, sib_target)
                else:
                    shutil.copy2(sibling, sib_target)
        except Exception:
            pass
    return slug


def port_agent(src: Path, prefix: str) -> str | None:
    """Port a single agent markdown file to vectorcode/agents/."""
    raw_slug = src.stem
    slug = f"vector-{prefix}{slugify(raw_slug)}.md"
    target = AGENTS_DST / slug
    if target.exists():
        return None
    AGENTS_DST.mkdir(parents=True, exist_ok=True)
    try:
        text = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        shutil.copy2(src, target)
        return slug
    src_rel = str(src.relative_to(GITHUB_DIR.parent)).replace("\\", "/")
    target.write_text(personalize(text, src_rel), encoding="utf-8")
    return slug


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true", help="Delete source repos after porting")
    ap.add_argument("--only", help="Only process this repo name (for testing)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not GITHUB_DIR.exists():
        print(f"ERROR: {GITHUB_DIR} not found")
        return 1

    grand_total_ported = 0
    grand_total_skipped = 0

    print("=" * 70)
    print(f"PORT phase — source: {GITHUB_DIR}")
    print(f"            target: {DST}")
    print("=" * 70)

    for target in PORT_TARGETS:
        if args.only and target["name"] != args.only:
            continue
        repo_dir = GITHUB_DIR / target["name"]
        if not repo_dir.exists():
            print(f"  [skip] {target['name']} (folder missing)")
            continue
        # Look in repo/ subfolder per the standard layout
        scan_root = repo_dir / "repo"
        if not scan_root.is_dir():
            scan_root = repo_dir

        is_agents = target.get("agents", False)
        files = find_agents(scan_root) if is_agents else find_skills(scan_root)

        cap = target.get("max_files", 1000)
        ported = 0
        skipped = 0
        for f in files[:cap]:
            try:
                if is_agents:
                    res = port_agent(f, target["prefix"])
                else:
                    res = port_skill(f, scan_root, target["prefix"], DST)
                if res:
                    ported += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"    [warn] {f}: {e}")
                skipped += 1
        print(f"  [{target['name']:50s}] {ported:>4} ported, {skipped:>4} skipped (of {len(files)} found)")
        grand_total_ported += ported
        grand_total_skipped += skipped

    print()
    print(f"TOTAL: {grand_total_ported} new entries ported, {grand_total_skipped} skipped")

    if args.delete:
        print()
        print("=" * 70)
        print("DELETE phase — removing source repos")
        print("=" * 70)
        deleted = 0
        for target in PORT_TARGETS + [{"name": n} for n in DELETE_ONLY]:
            repo_dir = GITHUB_DIR / target["name"]
            if repo_dir.exists():
                try:
                    shutil.rmtree(repo_dir, ignore_errors=False)
                    deleted += 1
                    print(f"  [del] {target['name']}")
                except Exception as e:
                    print(f"  [warn] could not delete {target['name']}: {e}")
        print(f"\nDeleted {deleted} folders.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
