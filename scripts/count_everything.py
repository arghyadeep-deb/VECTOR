"""Count all agents, skills, commands, tools in VECTOR."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")

from collections import Counter

print("=" * 60)
print("VECTOR COMPLETE INVENTORY")
print("=" * 60)

# ── 1. DISTRICT AGENTS ─────────────────────────────────────
print("\n--- 1. DISTRICT AGENTS ---")
from run_vector import bootstrap_agents
bootstrap_agents()
from core.city.agent_registry import get_registry
reg = get_registry()
agents = reg.list_all()
print(f"Registered agents: {len(agents)}")
# Group by district
districts = Counter()
for a in agents:
    d = a.get("district", "unknown") if isinstance(a, dict) else getattr(a, "district", "unknown")
    districts[d] += 1
for d, c in sorted(districts.items(), key=lambda x: -x[1]):
    print(f"  {d}: {c}")

# ── 2. OJ ABSORBED AGENTS ─────────────────────────────────
print("\n--- 2. OJ ABSORBED AGENTS ---")
oj_agents = 0
try:
    from vectorcode.src.vc_agents import _stubs as oj_stubs
    # Count registered agent classes
    import inspect
    for name, cls in inspect.getmembers(oj_stubs, inspect.isclass):
        if "Agent" in name or "agent" in name:
            oj_agents += 1
            print(f"  {name}")
except Exception as e:
    print(f"  (oj_agents unavailable: {e})")
print(f"  Total: {oj_agents}")

# ── 3. SKILLS ─────────────────────────────────────────────
print("\n--- 3. SKILLS ---")
skill_files = 0
skill_dirs = 0
for root, dirs, files in os.walk("vectorcode/skills"):
    if ".git" in root: continue
    for f in files:
        if f.endswith((".md", ".toml", ".yaml", ".yml")):
            skill_files += 1
    skill_dirs += len(dirs)
print(f"  Skill files: {skill_files}")
print(f"  Skill directories: {skill_dirs}")

# Also count from OJ absorbed skills
try:
    from vectorcode.src.vc_templates import discover_templates
    templates = discover_templates() or []
    print(f"  Agent templates: {len(templates)}")
except Exception as e:
    print(f"  Agent templates: unavailable ({e})")

# ── 4. COMMANDS / TOOLS ───────────────────────────────────
print("\n--- 4. COMMANDS & TOOLS ---")
oj_tools = 0
try:
    import vectorcode.src.vc_tools as vct
    for name in dir(vct):
        if "Tool" in name or "tool" in name:
            if not name.startswith("_"):
                oj_tools += 1
except:
    pass

cli_commands = 0
try:
    from vectorcode.src.vector_cli.main import main as cli_main
    if hasattr(cli_main, "commands"):
        cli_commands = len(cli_main.commands)
except:
    pass

# API routes
from core.api.app import create_app
app = create_app()
api_routes = [r for r in app.routes if hasattr(r, "methods")]
api_endpoints = len(api_routes)

print(f"  OJ absorbed tools: {oj_tools}")
print(f"  CLI commands: {cli_commands}")
print(f"  API endpoints: {api_endpoints}")
for r in sorted(api_routes, key=lambda x: x.path):
    methods = ",".join(sorted(r.methods))
    print(f"    {methods:8s} {r.path}")

# ── 5. DISTRICTS (from bootstrap code) ──────────────────
print("\n--- 5. DISTRICTS ---")
from run_vector import CORE_DISTRICTS
all_districts = set()
for _, _, d in CORE_DISTRICTS:
    all_districts.add(d)
# Also scan the filesystem
for d in sorted(os.listdir("agents/districts")):
    if os.path.isdir(f"agents/districts/{d}") and not d.startswith("_"):
        all_districts.add(d)
print(f"  Total districts: {len(all_districts)}")
for d in sorted(all_districts):
    print(f"  - {d}")

# ── 6. TOTALS ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  District agents:     {len(agents)}")
print(f"  OJ absorbed agents:  {oj_agents}")
print(f"  Total agents:        {len(agents) + oj_agents}")
print(f"  Districts:           {len(all_districts)}")
print(f"  Skill files:         {skill_files}")
print(f"  Agent templates:     {len(templates) if 'templates' in dir() else 0}")
print(f"  OJ tools:            {oj_tools}")
print(f"  API endpoints:       {api_endpoints}")
