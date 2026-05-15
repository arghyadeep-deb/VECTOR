"""Fix incomplete import rewrites from VectorCode absorption.

The absorption script renamed vector→vector (branding) but left ~400+
``from vector.X`` references that should be ``from vectorcode.src.oj_X``
or ``from core.X``.  This script batch-fixes them, then wraps orphan
references (channels, mining, server, _rust_bridge) in try/except.

Safe to re-run — idempotent within each file.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Directories to scan — all absorbed module locations
SCAN_DIRS = [
    ROOT / "vectorcode" / "src",
    ROOT / "core" / "telemetry",
    ROOT / "core" / "sandbox",
    ROOT / "core" / "scheduler",
]

# ---- Import redirect map ---------------------------------------------------
# When the absorption script encountered `from vector.<X>` it was supposed
# to redirect to the VECTOR target.  The branding step turned `vector` into
# `vector`, but the redirect was incomplete.  This map completes it.

COLLIDING = {"core", "agents", "tools", "engine", "system", "mcp", "security",
             "templates", "traces", "skills", "memory", "providers"}

CORE_MODULES = {"telemetry", "sandbox", "scheduler"}

# Modules that were NOT absorbed — existing references must be wrapped in
# try/except ImportError so they degrade gracefully.
NOT_ABSORBED = {"channels", "mining", "server", "prompt", "cli"}

# Modules whose top-level dir name differs from the redirect target
RENAME = {
    "traces": "oj_traces",
    "sessions": "sessions_oj",
    "mcp": "oj_mcp",
    "system": "oj_system",
    "security": "oj_security",
    "templates": "oj_templates",
    "skills": "oj_skills",  # may or may not exist
    "providers": "oj_providers",
}


def _target(mod: str) -> str | None:
    """Return the correct VECTOR import path for *mod*, or None if orphan."""
    if mod in NOT_ABSORBED:
        return None
    if mod in COLLIDING:
        return f"vectorcode.src.oj_{mod}"
    if mod in CORE_MODULES:
        return f"core.{mod}"
    if mod in RENAME:
        return f"vectorcode.src.{RENAME[mod]}"
    # Most absorbed modules keep their name
    return f"vectorcode.src.{mod}"


# ---- Line-level fixers -----------------------------------------------------

_RE_FROM_VECTOR = re.compile(
    r"^(from\s+)vector\.([a-zA-Z_][a-zA-Z0-9_.]*)(\s+import\s+.+)$",
    re.MULTILINE,
)
_RE_IMPORT_VECTOR = re.compile(
    r"^(import\s+)vector\.([a-zA-Z_][a-zA-Z0-9_.]*)(.*)$",
    re.MULTILINE,
)
_RE_FROM_VECTOR_ROOT = re.compile(
    r"^(from\s+)vector(\s+import\s+.+)$",
    re.MULTILINE,
)
_RE_RUST_BRIDGE = re.compile(
    r"^(from\s+(?:vector|vectorcode\.src)\._rust_bridge\s+import\s+.+)$",
    re.MULTILINE,
)


def _rewrite_from_vector(line: str) -> str | None:
    """Rewrite a ``from vector.xxx`` line.  Returns new line or None if no-op."""
    m = _RE_FROM_VECTOR.match(line)
    if not m:
        return None
    prefix, path, suffix = m.group(1), m.group(2), m.group(3)
    parts = path.split(".")
    mod = parts[0]
    tgt = _target(mod)
    if tgt is None:
        return None  # orphan — caller wraps in try/except
    rest = ".".join(parts[1:])
    if rest:
        return f"{prefix}{tgt}.{rest}{suffix}"
    return f"{prefix}{tgt}{suffix}"


def _rewrite_import_vector(line: str) -> str | None:
    """Rewrite an ``import vector.xxx`` line."""
    m = _RE_IMPORT_VECTOR.match(line)
    if not m:
        return None
    prefix, path, suffix = m.group(1), m.group(2), m.group(3)
    parts = path.split(".")
    mod = parts[0]
    tgt = _target(mod)
    if tgt is None:
        return None  # orphan
    rest = ".".join(parts[1:])
    if rest:
        return f"{prefix}{tgt}.{rest}{suffix}"
    return f"{prefix}{tgt}{suffix}"


def _rewrite_from_vector_root(line: str) -> str | None:
    """Rewrite ``from vector import xxx`` -> ``from vectorcode.src import xxx``."""
    m = _RE_FROM_VECTOR_ROOT.match(line)
    if not m:
        return None
    return f"{m.group(1)}vectorcode.src{m.group(2)}"


# ---- File-level processing -------------------------------------------------

def _get_indent(line: str) -> str:
    return line[:len(line) - len(line.lstrip())]


def fix_file(path: Path) -> int:
    """Fix all broken imports in *path*.  Returns number of lines changed."""
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            original = path.read_text(encoding="latin-1")
        except Exception:
            return 0
    lines = original.splitlines(keepends=True)
    changed = 0
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        indent = _get_indent(raw)

        # ---- _rust_bridge: wrap in try/except -------------------------------
        m = _RE_RUST_BRIDGE.match(stripped)
        if m:
            # Check it's not already wrapped
            if i > 0 and lines[i - 1].strip().startswith("try:"):
                i += 1
                continue
            # Wrap: try: <line> \n except ImportError: pass
            before = lines[:i]
            after = lines[i:]
            content = m.group(1)
            # If the import is inside a function/class body, match indent
            wrapper = [
                f"{indent}try:\n",
                f"{indent}    {content}\n",
                f"{indent}except ImportError:\n",
                f"{indent}    pass\n",
            ]
            lines = before + wrapper + after[1:]
            changed += 1
            i += len(wrapper)
            continue

        # ---- from vector.xxx -------------------------------------------------
        result = _rewrite_from_vector(stripped)
        if result is not None:
            lines[i] = f"{indent}{result}\n"
            changed += 1
            i += 1
            continue

        # ---- import vector.xxx -----------------------------------------------
        result = _rewrite_import_vector(stripped)
        if result is not None:
            lines[i] = f"{indent}{result}\n"
            changed += 1
            i += 1
            continue

        # ---- from vector import xxx ------------------------------------------
        result = _rewrite_from_vector_root(stripped)
        if result is not None:
            lines[i] = f"{indent}{result}\n"
            changed += 1
            i += 1
            continue

        # ---- Orphan modules: wrap in try/except -----------------------------
        orphan = _check_orphan(stripped)
        if orphan is not None:
            if i > 0 and lines[i - 1].strip().startswith("try:"):
                i += 1
                continue
            before = lines[:i]
            after = lines[i + 1:]
            wrapper = [
                f"{indent}try:\n",
                f"{indent}    {stripped}\n",
                f"{indent}except ImportError:\n",
                f"{indent}    pass\n",
            ]
            lines = before + wrapper + after
            changed += 1
            i += len(wrapper)
            continue

        i += 1

    if changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


_ORPHAN_RE = re.compile(
    r"^(?:from\s+vector\.(channels|mining|server|prompt|cli)(?:\.\w+)*\s|import\s+vector\.(channels|mining|server|prompt|cli))",
)


def _check_orphan(stripped: str) -> str | None:
    m = _ORPHAN_RE.match(stripped)
    return m.group(0) if m else None


# ---- Main ------------------------------------------------------------------

def main() -> int:
    total_changed = 0
    fixed_files: list[Path] = []
    for d in SCAN_DIRS:
        if not d.exists():
            print(f"  [skip] {d} not found")
            continue
        for f in sorted(d.rglob("*.py")):
            # Skip .venv and __pycache__
            if ".venv" in f.parts or "__pycache__" in f.parts:
                continue
            n = fix_file(f)
            if n:
                total_changed += n
                fixed_files.append(f)
                print(f"  {f.relative_to(ROOT)} — {n} changes")

    print(f"\n{len(fixed_files)} files modified, {total_changed} import lines fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
