"""Absorb VectorCode high-value modules into VECTOR.

Source: GitHub/VectorCode/src/vector/<module>/
Target: vectorcode/src/<module>/  or  core/<module>/

For each module:
  1. Copy every .py and asset file
  2. Branding: vector -> vector, VectorCode -> VectorCode, Jarvis -> VECTOR
  3. Rewrite imports `from vector.X` -> `from vectorcode.src.<dest>`
     where <dest> is `oj_X` if X collides with VECTOR's existing dirs.
  4. Add VECTOR-INGESTED header.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\VectorCode\src\vector")
DST_VC = ROOT / "vectorcode" / "src"
DST_CORE = ROOT / "core"

# Modules to absorb. (source_subdir, "core"|"vc", target_subdir)
MODULES: list[tuple[str, str, str]] = [
    # Tier 1 — highest novel value
    ("telemetry",   "core", "telemetry"),
    ("evals",       "vc",   "evals"),
    ("bench",       "vc",   "bench"),
    ("sandbox",     "core", "sandbox"),
    ("a2a",         "vc",   "a2a"),
    # Tier 2 — fill real gaps
    ("scheduler",   "core", "scheduler"),
    ("learning",    "vc",   "learning"),
    ("workflow",    "vc",   "workflow"),
    ("recipes",     "vc",   "recipes"),
    ("traces",      "vc",   "oj_traces"),
    ("sessions",    "vc",   "sessions_oj"),
    ("operators",   "vc",   "operators"),
    # Tier 3 — extensions
    ("speech",      "vc",   "speech"),
    ("security",    "vc",   "oj_security"),
    ("connectors",  "vc",   "connectors"),
    ("intelligence","vc",   "intelligence"),
    ("system",      "vc",   "oj_system"),
    ("daemon",      "vc",   "daemon"),
    ("templates",   "vc",   "oj_templates"),
    ("mcp",         "vc",   "oj_mcp"),
    ("engine",      "vc",   "oj_engine"),
    # Colliding-namespace modules (needed by everything else)
    ("core",        "vc",   "oj_core"),
    ("agents",      "vc",   "oj_agents"),
    ("tools",       "vc",   "oj_tools"),
]

# OJ submodule names that collide with VECTOR's existing vectorcode/src/ dirs.
# When OJ code does `from vector.<name>`, redirect to vectorcode.src.oj_<name>.
COLLIDING = {
    "core", "agents", "tools", "engine", "system", "mcp", "security",
    "templates", "traces", "skills", "memory", "providers",
}

# Modules that VECTOR places under core/ rather than vectorcode/src/
CORE_MODULES = {"telemetry", "sandbox", "scheduler"}

REPLACEMENTS_TEXT = [
    (r"\bVectorCode\b", "VectorCode"),
    (r"\bvector\b", "vector"),
    (r"\bvector\b", "vector"),
    (r"\bvector\b", "vector"),
    (r"\bJarvis\b", "VECTOR"),
    (r"\bjarvis\b", "vector"),
    (r"\bIntelligence Per Watt\b", "VECTOR Per Watt"),
    (r"\bHazy Research\b", "VECTOR Lab"),
]


def header(src_path: str) -> str:
    return (
        f"# VECTOR-INGESTED MODULE\n"
        f"# Source: github/vector/VectorCode/src/vector/{src_path}\n"
        f"# Personalized for VECTOR runtime.\n"
        f"# Owner: Arghyadeep Deb\n"
        f"# Ingested: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n"
    )


def _redirect(name: str, in_core_module: bool) -> str:
    """Map `vector.<name>` (post-rename) to its real VECTOR target."""
    if name in COLLIDING:
        return f"vectorcode.src.oj_{name}"
    if name in CORE_MODULES:
        return f"core.{name}"
    return f"vectorcode.src.{name}"


def personalize(text: str, src_module: str, src_file: str) -> str:
    out = text
    for pattern, repl in REPLACEMENTS_TEXT:
        out = re.sub(pattern, repl, out)

    in_core = src_module in CORE_MODULES

    out = re.sub(
        r"^from vector\.([a-zA-Z_][a-zA-Z0-9_]*)",
        lambda m: f"from {_redirect(m.group(1), in_core)}",
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(
        r"^import vector\.([a-zA-Z_][a-zA-Z0-9_]*)",
        lambda m: f"import {_redirect(m.group(1), in_core)}",
        out,
        flags=re.MULTILINE,
    )
    out = re.sub(r"^from vector import", "from vectorcode.src import", out, flags=re.MULTILINE)
    out = re.sub(r"^import vector(\s|$)", r"import vectorcode.src\1", out, flags=re.MULTILINE)

    if not out.lstrip().startswith("# VECTOR-INGESTED"):
        out = header(f"{src_module}/{src_file}") + out
    return out


def absorb_module(src_subdir: str, dst_root: str, dst_subdir: str) -> tuple[int, int]:
    src_dir = SRC / src_subdir
    if not src_dir.exists():
        print(f"  [skip] {src_subdir} not in source")
        return 0, 0

    target_root = DST_CORE if dst_root == "core" else DST_VC
    dst_dir = target_root / dst_subdir
    dst_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for src_file in src_dir.rglob("*"):
        if src_file.is_dir():
            continue
        rel = src_file.relative_to(src_dir)
        dst_file = dst_dir / rel
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            if src_file.suffix == ".py":
                text = src_file.read_text(encoding="utf-8")
                dst_file.write_text(
                    personalize(text, src_subdir, str(rel).replace("\\", "/")),
                    encoding="utf-8",
                )
            else:
                shutil.copy2(src_file, dst_file)
            copied += 1
        except Exception as e:
            print(f"    [warn] {src_file}: {e}")
            skipped += 1
    return copied, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if not SRC.exists():
        print(f"ERROR: {SRC} not found")
        return 1

    print(f"VectorCode -> VECTOR absorption")
    print(f"  Source: {SRC}")
    print(f"  Target: vectorcode/src/ + core/")
    print()

    total_copied = 0
    total_skipped = 0
    for src_subdir, dst_root, dst_subdir in MODULES:
        c, s = absorb_module(src_subdir, dst_root, dst_subdir)
        target = f"{'core' if dst_root == 'core' else 'vectorcode/src'}/{dst_subdir}"
        print(f"  [{src_subdir:>14}] -> {target:<35}  copied={c:>4}  skipped={s}")
        total_copied += c
        total_skipped += s

    print()
    print(f"TOTAL: {total_copied} files ported, {total_skipped} skipped")

    if args.delete:
        oj_root = SRC.parent.parent.parent
        if oj_root.exists():
            print(f"\nDeleting source: {oj_root}")
            try:
                import stat
                def _rm_readonly(func, path, _):
                    try:
                        Path(path).chmod(stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass
                shutil.rmtree(oj_root, onerror=_rm_readonly)
                print("Deleted.")
            except Exception as e:
                print(f"  [warn] could not delete: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
