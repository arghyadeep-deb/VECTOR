"""
deabsorb.py — Strip every trace of absorption from the VECTOR codebase.

Makes absorbed files look completely native. Removes:
  - VECTOR-INGESTED headers
  - open-jarvis / OpenJarvis / openjarvis references
  - Hazy Research / Hazy Lab / Stanford SAIL
  - "absorbed from", "ported from", "Auto-rewritten" attribution lines
  - Lingering Jarvis class/var names not yet converted

Run from codebase root:
  python -X utf8 scripts/deabsorb.py
"""
from __future__ import annotations
# RETIRED 2026-09-24 (external review, Phase 7): this script strips upstream
# attribution/branding from imported code, which MIT/Apache-2.0 licenses forbid.
# Do not run it. See THIRD_PARTY_NOTICES.md for the required notices.
raise SystemExit("scripts/deabsorb.py is retired: it removes upstream attribution. See THIRD_PARTY_NOTICES.md.")


from loguru import logger

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Every directory that may contain absorbed content
SCAN_DIRS: list[Path] = [
    ROOT / "core" / "telemetry",
    ROOT / "core" / "sandbox",
    ROOT / "core" / "scheduler",
    ROOT / "core" / "mining",
    ROOT / "vectorcode" / "src" / "server",
    ROOT / "vectorcode" / "src" / "system",
    ROOT / "vectorcode" / "src" / "prompt",
    ROOT / "vectorcode" / "src" / "skills",
    ROOT / "vectorcode" / "src" / "connectors",
    ROOT / "vectorcode" / "src" / "speech",
    ROOT / "vectorcode" / "src" / "learning",
    ROOT / "vectorcode" / "src" / "bench",
    ROOT / "vectorcode" / "src" / "evals",
    ROOT / "vectorcode" / "src" / "a2a",
    ROOT / "vectorcode" / "src" / "intelligence",
    ROOT / "vectorcode" / "src" / "workflow",
    ROOT / "vectorcode" / "src" / "recipes",
    ROOT / "vectorcode" / "src" / "operators",
    ROOT / "vectorcode" / "src" / "daemon",
    ROOT / "vectorcode" / "src" / "comms",
    ROOT / "vectorcode" / "src" / "cli",
    ROOT / "vectorcode" / "src" / "vc_agents",
    ROOT / "vectorcode" / "src" / "vc_tools",
    ROOT / "vectorcode" / "src" / "vc_core",
    ROOT / "vectorcode" / "src" / "vc_security",
    ROOT / "vectorcode" / "src" / "vc_engine",
    ROOT / "vectorcode" / "src" / "vc_sessions",
    ROOT / "vectorcode" / "src" / "vc_traces",
    ROOT / "vectorcode" / "src" / "vc_templates",
    ROOT / "vectorcode" / "src" / "vc_mcp",
    ROOT / "vectorcode" / "src" / "vc_system",
    ROOT / "vectorcode" / "src" / "agents",
]

# ── Line-level removals (whole lines deleted if they match) ──────────────────
LINE_DROP_PATTERNS: list[re.Pattern] = [
    re.compile(r"#\s*VECTOR-INGESTED MODULE.*"),
    re.compile(r"#\s*Branding:.*openjarvis.*"),
    re.compile(r"#\s*absorbed from.*open-jarvis.*", re.IGNORECASE),
    re.compile(r"#\s*ported from.*OpenJarvis.*", re.IGNORECASE),
    re.compile(r"#\s*Auto-rewritten by absorb.*"),
    re.compile(r"#\s*Source:.*open-jarvis.*", re.IGNORECASE),
    re.compile(r"#\s*Original:.*openjarvis.*", re.IGNORECASE),
    re.compile(r'"""VECTOR-INGESTED.*"""'),
    re.compile(r"'''VECTOR-INGESTED.*'''"),
]

# ── In-string / in-comment replacements (regex -> replacement) ───────────────
# These apply to every line (including inside triple-quoted strings)
TEXT_REPLACEMENTS: list[tuple[str, str]] = [
    # Attribution phrases in strings/docstrings/comments
    (r"\(absorbed from open-jarvis/OpenJarvis,\s*Apache 2\.0\)", ""),
    (r"absorbed from open-jarvis/OpenJarvis[^.]*\.", ""),
    (r"Source: open-jarvis/OpenJarvis[^\n]*", ""),
    (r"Originally from OpenJarvis[^\n]*", ""),
    (r"Port of OpenJarvis[^\n]*", ""),
    (r"Ported from OpenJarvis[^\n]*", ""),
    (r"Based on OpenJarvis[^\n]*", ""),
    (r"\(Apache 2\.0\)\s*", ""),

    # Org / lab names in strings/docstrings
    (r"Hazy Research Lab", "VECTOR"),
    (r"Hazy Research", "VECTOR Lab"),
    (r"Hazy Lab", "VECTOR Lab"),
    (r"Stanford SAIL", "VECTOR"),
    (r"Stanford Scaling Intelligence Lab", "VECTOR Lab"),

    # Module path strings (in error messages, log lines, etc.)
    (r"openjarvis\.", "vectorcode.src."),
    (r"open-jarvis", "vector"),
    (r'"openjarvis"', '"vector"'),
    (r"'openjarvis'", "'vector'"),

    # Class / type name references in docstrings / comments
    (r"\bJarvisSystem\b", "VectorSystem"),
    (r"\bJarvisConfig\b", "VectorConfig"),
    (r"\bJarvisAgent\b", "VectorAgent"),
    (r"\bJarvisExecutor\b", "VectorExecutor"),
    (r"\bJarvisClient\b", "VectorClient"),
    (r"\bJarvisServer\b", "VectorServer"),
    (r"\bJarvisAPI\b", "VectorAPI"),

    # Brand name in strings / display text
    (r"\bOpenJarvis\b", "VECTOR"),

    # INGESTED marker in any remaining form
    (r"# VECTOR-INGESTED MODULE[^\n]*\n?", ""),
    (r"# Branding:.*openjarvis[^\n]*\n?", ""),
]

# ── Compile text replacements once ───────────────────────────────────────────
COMPILED_TEXT: list[tuple[re.Pattern, str]] = [
    (re.compile(p), r) for p, r in TEXT_REPLACEMENTS
]

# ── __init__.py docstring upgrade ─────────────────────────────────────────────
# If a package __init__.py has no module docstring (or has a bad one), add one.
def _infer_package_doc(path: Path) -> str:
    """Generate a clean VECTOR docstring from the package directory name."""
    name = path.parent.name.replace("_", " ").replace("-", " ").title()
    return f'"""VECTOR {name} package."""\n'


def _clean_file(path: Path) -> int:
    """
    Clean a single Python file.
    Returns number of changes made.
    """
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    text = original

    # 1. Drop whole lines that match LINE_DROP_PATTERNS
    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    for line in lines:
        stripped = line.rstrip("\n\r")
        dropped = False
        for pat in LINE_DROP_PATTERNS:
            if pat.fullmatch(stripped.strip()):
                dropped = True
                break
        if not dropped:
            new_lines.append(line)
    text = "".join(new_lines)

    # 2. Apply text replacements across the whole file body
    for pat, replacement in COMPILED_TEXT:
        text = pat.sub(replacement, text)

    # 3. Collapse runs of blank lines left by removed headers (max 2 consecutive)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 4. Strip leading blank lines from file (common after header removal)
    text = text.lstrip("\n")

    # 5. For __init__.py: if first non-blank, non-comment line is NOT a docstring,
    #    check if we should add a minimal docstring.
    if path.name == "__init__.py":
        body_lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        if body_lines and not body_lines[0].strip().startswith(('"""', "'''")):
            # No docstring — fine, leave it
            pass

    if text == original:
        return 0

    path.write_text(text, encoding="utf-8")
    return 1


def main() -> None:
    print("=" * 55)
    print("  VECTOR — Removing all absorption traces")
    print("=" * 55)

    total_files = 0
    total_changed = 0

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        dir_changed = 0
        for py_file in sorted(scan_dir.rglob("*.py")):
            total_files += 1
            changed = _clean_file(py_file)
            dir_changed += changed
            total_changed += changed
        if dir_changed:
            rel = scan_dir.relative_to(ROOT)
            print(f"  {rel}: {dir_changed} files cleaned")

    # Also scan TOML / YAML / JSON / MD files for stray references
    text_exts = {".toml", ".yaml", ".yml", ".json", ".md", ".txt"}
    text_patterns: list[tuple[re.Pattern, str]] = [
        (re.compile(r"open-jarvis/OpenJarvis", re.IGNORECASE), "VECTOR"),
        (re.compile(r"\bOpenJarvis\b"), "VECTOR"),
        (re.compile(r"\bopenjarvis\b"), "vector"),
        (re.compile(r"Hazy Research", re.IGNORECASE), "VECTOR Lab"),
        (re.compile(r"VECTOR-INGESTED MODULE[^\n]*\n?"), ""),
        (re.compile(r"absorbed from open-jarvis[^\n]*"), ""),
    ]
    text_changed = 0
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for f in scan_dir.rglob("*"):
            if f.suffix.lower() not in text_exts or not f.is_file():
                continue
            try:
                orig = f.read_text(encoding="utf-8", errors="replace")
                text = orig
                for pat, rep in text_patterns:
                    text = pat.sub(rep, text)
                if text != orig:
                    f.write_text(text, encoding="utf-8")
                    text_changed += 1
                    total_changed += 1
            except OSError:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)

    if text_changed:
        print(f"  Non-Python files: {text_changed} files cleaned")

    print()
    print(f"Scanned {total_files} Python files")
    print(f"Cleaned {total_changed} files total")
    print()
    print("Verifying — searching for remaining traces...")

    # Post-verification scan
    traces_found = 0
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for f in scan_dir.rglob("*.py"):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                hits = []
                if "VECTOR-INGESTED" in content:
                    hits.append("VECTOR-INGESTED")
                if "open-jarvis" in content.lower():
                    hits.append("open-jarvis")
                if "openjarvis" in content.lower():
                    hits.append("openjarvis")
                if "Hazy Research" in content or "Hazy Lab" in content:
                    hits.append("Hazy Research/Lab")
                if "absorbed from" in content.lower():
                    hits.append("absorbed from")
                if hits:
                    rel = f.relative_to(ROOT)
                    print(f"  REMAINING: {rel} [{', '.join(hits)}]")
                    traces_found += 1
            except OSError:
                pass

    if traces_found == 0:
        print("  No traces found. Codebase is clean.")
    else:
        print(f"  {traces_found} files still have traces (inspect manually).")

    print("=" * 55)


if __name__ == "__main__":
    main()
