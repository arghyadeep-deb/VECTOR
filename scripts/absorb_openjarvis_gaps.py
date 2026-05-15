"""
absorb_openjarvis_gaps.py — Absorb remaining OpenJarvis modules into VECTOR.

Handles branding rewrite automatically:
  openjarvis   → vectorcode
  OpenJarvis   → VECTOR
  JarvisSystem → VectorSystem
  JarvisConfig → VectorConfig
  Hazy Research / Hazy Lab → VECTOR Lab
  from openjarvis. → from vectorcode.src.

Run from codebase root:
  python scripts/absorb_openjarvis_gaps.py
"""
from __future__ import annotations
import re
import sys
import shutil
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────
OJ_SRC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\OpenJarvis\src\openjarvis")
VECTOR_ROOT = Path(__file__).parent.parent
VC_SRC = VECTOR_ROOT / "vectorcode" / "src"
CORE = VECTOR_ROOT / "core"

# ── Branding substitutions (order matters) ──────────────────────────────────
REPLACEMENTS: list[tuple[str, str]] = [
    # Imports — most specific first
    (r"from openjarvis\.server",         "from vectorcode.src.server"),
    (r"from openjarvis\.system",         "from vectorcode.src.system"),
    (r"from openjarvis\.prompt",         "from vectorcode.src.prompt"),
    (r"from openjarvis\.mining",         "from core.mining"),
    (r"from openjarvis\.skills",         "from vectorcode.src.skills"),
    (r"from openjarvis\.channels",       "from vectorcode.src.comms"),
    (r"from openjarvis\.core",           "from vectorcode.src.vc_core"),
    (r"from openjarvis\.agents",         "from vectorcode.src.vc_agents"),
    (r"from openjarvis\.tools",          "from vectorcode.src.vc_tools"),
    (r"from openjarvis\.engine",         "from vectorcode.src.vc_engine"),
    (r"from openjarvis\.security",       "from vectorcode.src.vc_security"),
    (r"from openjarvis\.sessions",       "from vectorcode.src.vc_sessions"),
    (r"from openjarvis\.traces",         "from vectorcode.src.vc_traces"),
    (r"from openjarvis\.templates",      "from vectorcode.src.vc_templates"),
    (r"from openjarvis\.",               "from vectorcode.src."),
    (r"import openjarvis\.",             "import vectorcode.src."),
    # Class/system names
    (r"\bJarvisSystem\b",               "VectorSystem"),
    (r"\bJarvisConfig\b",               "VectorConfig"),
    (r"\bJarvisAgent\b",                "VectorAgent"),
    (r"\bOpenJarvis\b",                 "VECTOR"),
    (r"\bopenjarvis\b",                 "vector"),
    # Docs/strings
    (r"OpenJarvis API",                 "VECTOR API"),
    (r"OpenJarvis Server",              "VECTOR Server"),
    (r"Hazy Research Lab",              "VECTOR Lab"),
    (r"Hazy Research",                  "VECTOR Lab"),
    (r"Hazy Lab",                       "VECTOR Lab"),
    (r"Stanford SAIL",                  "VECTOR"),
    (r"openjarvis-server",              "vector-server"),
    (r"JARVIS_",                        "VECTOR_"),
]

HEADER = '"""VECTOR-INGESTED MODULE (absorbed from open-jarvis/OpenJarvis, Apache 2.0).\nBranding: openjarvis→vector, Jarvis→VECTOR. Auto-rewritten by absorb_openjarvis_gaps.py\n"""\n'


def rewrite(text: str) -> str:
    for pattern, replacement in REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    return text


def absorb_file(src: Path, dest: Path) -> bool:
    """Rewrite branding and copy a single file. Returns True if written."""
    if dest.exists():
        # Skip if dest is newer
        if dest.stat().st_mtime >= src.stat().st_mtime:
            return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    # Only rewrite Python files
    if src.suffix == ".py":
        text = rewrite(text)
        # Prepend VECTOR header if not already present
        if "VECTOR-INGESTED" not in text[:200] and not text.strip().startswith("#!"):
            text = HEADER + text
    dest.write_text(text, encoding="utf-8")
    return True


def absorb_dir(src_dir: Path, dest_dir: Path, skip: set[str] | None = None) -> tuple[int, int]:
    """Recursively absorb all files from src_dir to dest_dir. Returns (written, skipped)."""
    written = skipped = 0
    skip = skip or set()
    for src_file in src_dir.rglob("*"):
        if not src_file.is_file():
            continue
        if any(part in skip for part in src_file.parts):
            skipped += 1
            continue
        rel = src_file.relative_to(src_dir)
        dest_file = dest_dir / rel
        if absorb_file(src_file, dest_file):
            written += 1
            print(f"  ✓ {rel}")
        else:
            skipped += 1
    return written, skipped


# ── Absorption manifest ──────────────────────────────────────────────────────
# Each entry: (source_dir_in_OJ, dest_dir_in_VECTOR, description)
TIER1 = [
    # CRITICAL — missing entirely
    (OJ_SRC / "server",  VC_SRC / "server",   "FastAPI REST server (21 files)"),
    (OJ_SRC / "system",  VC_SRC / "system",   "VectorSystem composition layer (7 files)"),
    (OJ_SRC / "prompt",  VC_SRC / "prompt",   "SystemPromptBuilder (2 files)"),
]

# Mining — merge missing files only (some already exist in core/mining)
MINING_FILES = [
    "_miner_loop_main.py",
    "_mps_miner_loop_main.py",
    "apple_mps_pearl.py",
    "cpu_pearl.py",
    "vllm_pearl.py",
    "_pearl_subprocess.py",
    "_metrics.py",
    "_install.py",
]

# Skills — merge missing management files (some already exist)
SKILLS_MISSING = [
    "manager.py",
    "executor.py",
    "parser.py",
    "overlay.py",
    "dependency.py",
    "security.py",
    "tool_adapter.py",
    "tool_translator.py",
    "index.py",
    "importer.py",
]

SKILLS_SOURCES = ["base.py", "github.py", "hermes.py", "openclaw.py"]

# Missing messaging channels
MISSING_CHANNELS = [
    "irc.py",
    "line.py",
    "viber.py",
    "messenger.py",
    "reddit.py",
    "mastodon.py",
    "xmpp.py",
    "rocketchat.py",
    "zulip.py",
    "twitch.py",
    "twitter.py",
    "nostr.py",
    "sendblue.py",
    "twilio_sms.py",
    "gmail_channel.py",
]


def absorb_individual_files(src_dir: Path, dest_dir: Path, filenames: list[str]) -> tuple[int, int]:
    """Absorb only specific files from a directory."""
    written = skipped = 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        src_file = src_dir / name
        if not src_file.exists():
            print(f"  ⚠ MISSING in OJ: {name}")
            skipped += 1
            continue
        dest_file = dest_dir / name
        if absorb_file(src_file, dest_file):
            written += 1
            print(f"  ✓ {name}")
        else:
            skipped += 1
    return written, skipped


def ensure_init(directory: Path) -> None:
    """Ensure __init__.py exists."""
    init = directory / "__init__.py"
    if not init.exists():
        init.write_text(
            '"""VECTOR-INGESTED MODULE (absorbed from open-jarvis/OpenJarvis, Apache 2.0)."""\n',
            encoding="utf-8",
        )


def main() -> None:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    total_written = total_skipped = 0

    print("\n" + "=" * 51)
    print("  VECTOR <- OpenJarvis Gap Absorption")
    print("=" * 51 + "\n")

    # ── TIER 1: Full directory absorptions ────────────────────────────────────
    print("▸ TIER 1 — Full directory absorptions\n")
    for src_dir, dest_dir, desc in TIER1:
        if not src_dir.exists():
            print(f"  ⚠ OJ source missing: {src_dir}")
            continue
        print(f"[{desc}]")
        w, s = absorb_dir(src_dir, dest_dir)
        ensure_init(dest_dir)
        total_written += w
        total_skipped += s
        print(f"  → {w} written, {s} skipped\n")

    # ── TIER 1: Mining missing files ──────────────────────────────────────────
    print("[Mining — missing Pearl loops]")
    oj_mining = OJ_SRC / "mining"
    dest_mining = CORE / "mining"
    if oj_mining.exists():
        w, s = absorb_individual_files(oj_mining, dest_mining, MINING_FILES)
        total_written += w
        total_skipped += s
    else:
        print("  ⚠ OpenJarvis mining/ not found")
    print()

    # ── TIER 1: Skills missing management files ───────────────────────────────
    print("[Skills — missing management files]")
    oj_skills = OJ_SRC / "skills"
    dest_skills = VC_SRC / "skills"
    if oj_skills.exists():
        w, s = absorb_individual_files(oj_skills, dest_skills, SKILLS_MISSING)
        total_written += w
        total_skipped += s
        # Skills sources subdir
        oj_sources = oj_skills / "sources"
        dest_sources = dest_skills / "sources"
        if oj_sources.exists():
            print("  [sources/]")
            w2, s2 = absorb_individual_files(oj_sources, dest_sources, SKILLS_SOURCES)
            ensure_init(dest_sources)
            total_written += w2
            total_skipped += s2
    else:
        print("  ⚠ OpenJarvis skills/ not found")
    print()

    # ── TIER 2: Missing messaging channels ───────────────────────────────────
    print("[Messaging — 13 missing platforms]")
    oj_channels = OJ_SRC / "channels"
    dest_comms = VC_SRC / "comms"
    if oj_channels.exists():
        w, s = absorb_individual_files(oj_channels, dest_comms, MISSING_CHANNELS)
        total_written += w
        total_skipped += s
    else:
        print("  ⚠ OpenJarvis channels/ not found")
    print()

    # ── TIER 2: Tools storage/context.py ─────────────────────────────────────
    print("[Tools storage — context.py]")
    oj_storage = OJ_SRC / "tools" / "storage"
    dest_storage = VC_SRC / "vc_tools" / "storage"
    ctx = oj_storage / "context.py"
    if ctx.exists():
        dest_storage.mkdir(parents=True, exist_ok=True)
        if absorb_file(ctx, dest_storage / "context.py"):
            print("  ✓ context.py")
            total_written += 1
        else:
            print("  → already current")
    else:
        print("  ⚠ context.py not found in OJ tools/storage/")
    print()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("═══════════════════════════════════════════════════")
    print(f"  COMPLETE: {total_written} files written, {total_skipped} skipped")
    print("═══════════════════════════════════════════════════\n")


if __name__ == "__main__":
    main()
