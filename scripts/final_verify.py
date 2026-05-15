"""Final alignment verification before starting server."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")

print("=" * 50)
print("FINAL ALIGNMENT VERIFICATION")
print("=" * 50)

# 1. All key imports
tests = [
    ("A2A router", "core.api.routers.a2a"),
    ("API app factory", None),  # special
    ("Autonomous loop", "core.loop.autonomous_loop"),
    ("Workflow runner", "core.loop.workflow_runner"),
    ("Cron jobs", "core.loop.cron_jobs"),
    ("Ollama safe", "core.inference.ollama_safe"),
    ("SessionStore", "vectorcode.src.vc_sessions.session"),
    ("VectorSystem", "vectorcode.src.vc_system.core"),
    ("TraceCollector", "vectorcode.src.vc_traces.collector"),
    ("OperatorManager", "vectorcode.src.operators.manager"),
    ("BenchmarkSuite", "vectorcode.src.bench._stubs"),
    ("MCP fallback", "core.mcp_server"),
    ("Intelligence catalog", "vectorcode.src.intelligence"),
]

all_ok = True
for name, mod in tests:
    try:
        if mod == "core.api.app":
            __import__("core.api.app").create_app()
        elif mod == "core.mcp_server":
            m = __import__("core.mcp_server")
            assert m._VC_MCP_AVAILABLE is not None
        elif mod == "vectorcode.src.vc_system.core":
            m = __import__("vectorcode.src.vc_system.core")
            assert hasattr(m, "VectorSystem")
        else:
            __import__(mod)
        print(f"  OK  {name}")
    except Exception as e:
        print(f"  FAIL {name}: {str(e).splitlines()[0][:80]}")
        all_ok = False

# 2. A2A routes
app = __import__("core.api.app").create_app()
a2a_routes = [r.path for r in app.routes if "/a2a/" in str(r.path)]
api_routes = [r for r in app.routes if hasattr(r, "methods")]
print(f"  A2A endpoints: {len(a2a_routes)}")
for r in sorted(a2a_routes):
    print(f"    {r}")
print(f"  Total API routes: {len(api_routes)}")

# 3. Frontend
from pathlib import Path
dashboard = Path("core/ui/dashboard/dist/index.html")
hud_assets = Path("core/ui/dashboard/dist/assets")
if dashboard.exists():
    print(f"  Frontend: BUILT ({dashboard.stat().st_size} bytes)")
    print(f"  HUD assets: {len(list(hud_assets.glob('*')))} files")
else:
    print(f"  Frontend: NOT BUILT")

print()
if all_ok:
    print("ALL CHECKS PASSED")
else:
    print("SOME CHECKS FAILED")
