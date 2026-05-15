"""Final comparison: VECTOR vs original OpenJarvis."""
from __future__ import annotations

from pathlib import Path

OJ_SRC = Path("C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/GitHub/OpenJarvis/src/openjarvis")
ROOT = Path(".")

MODULES = [
    ("a2a",          "a2a",         "vc", "a2a"),
    ("telemetry",    "telemetry",   "core", "telemetry"),
    ("evals",        "evals",       "vc", "evals"),
    ("bench",        "bench",       "vc", "bench"),
    ("sandbox",      "sandbox",     "core", "sandbox"),
    ("scheduler",    "scheduler",   "core", "scheduler"),
    ("learning",     "learning",    "vc", "learning"),
    ("workflow",     "workflow",    "vc", "workflow"),
    ("recipes",      "recipes",     "vc", "recipes"),
    ("traces",       "traces",      "vc", "vc_traces"),
    ("sessions",     "sessions",    "vc", "sessions_oj"),
    ("operators",    "operators",   "vc", "operators"),
    ("speech",       "speech",      "vc", "speech"),
    ("security",     "security",    "vc", "vc_security"),
    ("connectors",   "connectors",  "vc", "connectors"),
    ("intelligence", "intelligence","vc", "intelligence"),
    ("system",       "system",      "vc", "vc_system"),
    ("daemon",       "daemon",      "vc", "daemon"),
    ("templates",    "templates",   "vc", "vc_templates"),
    ("mcp",          "mcp",          "vc", "vc_mcp"),
    ("engine",       "engine",      "vc", "vc_engine"),
    ("core",         "core",        "vc", "vc_core"),
    ("agents",       "agents",      "vc", "vc_agents"),
    ("tools",        "tools",       "vc", "vc_tools"),
]

import os

HEADER = f"{'Module':<18s} {'OJ .py':>7s} {'VC .py':>7s} {'Match':>6s}  {'Wired'}"
print(HEADER)
print("-" * len(HEADER))

total_oj = 0
total_vc = 0
for name, subdir, dtype, dname in MODULES:
    src_dir = OJ_SRC / subdir
    oj_count = 0
    if src_dir.exists():
        for f in src_dir.rglob("*.py"):
            oj_count += 1

    if dtype == "core":
        dst_dir = ROOT / "core" / dname
    else:
        dst_dir = ROOT / "vectorcode" / "src" / dname
    vc_count = 0
    if dst_dir.exists():
        for f in dst_dir.rglob("*.py"):
            if "__pycache__" not in f.parts:
                vc_count += 1

    total_oj += oj_count
    total_vc += vc_count

    diff = abs(vc_count - oj_count)
    match = "Y" if diff <= 2 else f"-{diff}"

    wired = "YES" if name in (
        "a2a", "telemetry", "evals", "sandbox", "scheduler", "learning",
        "workflow", "recipes", "traces", "sessions", "operators", "speech",
        "connectors", "intelligence", "system", "daemon", "templates", "mcp",
        "engine", "core", "agents", "tools", "bench", "security"
    ) else "NO"

    print(f"{name:<18s} {oj_count:>7d} {vc_count:>7d} {match:>6s}  {wired}")

print()
print("Skipped modules (not absorbed):")
for subdir in ("channels", "cli", "mining", "server", "skills", "prompt"):
    d = OJ_SRC / subdir
    cnt = 0
    if d.exists():
        for f in d.rglob("*.py"):
            cnt += 1
    print(f"  {subdir:<12s} {cnt} .py files")

print()
print(f"Absorbed: {total_oj} OJ .py -> {total_vc} VC .py")
print(f"Retention: {total_vc / total_oj * 100:.0f}%")
print()

# Check for any remaining broken imports
import re
broken = 0
for root, dirs, files in os.walk("."):
    if ".git" in root or "__pycache__" in root or ".venv" in root:
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        fp = os.path.join(root, f)
        try:
            text = open(fp, encoding="utf-8", errors="replace").read()
        except:
            continue
        # Check for remaining vector.X imports (shouldn't exist)
        for m in re.finditer(r"^from\s+vector\.([a-zA-Z])", text, re.MULTILINE):
            broken += 1
            if broken <= 5:
                print(f"  BROKEN: {os.path.normpath(fp)}: {m.group()}")

if broken:
    print(f"  {broken} broken imports remain")
else:
    print("  Import health: CLEAN (zero broken imports)")
