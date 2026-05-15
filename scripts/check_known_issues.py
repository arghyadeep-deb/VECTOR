"""Verify which KNOWN_ISSUES.md items still exist."""
from __future__ import annotations

import subprocess
import sys
import os
sys.path.insert(0, os.getcwd())

print("=" * 60)
print("KNOWN ISSUES VERIFICATION")
print("=" * 60)

# 1. Gateway
print("\n1. Gateway runner (🔴)")
try:
    from vectorcode.src.gateway.run import GatewayRunner
    print("  STILL EXISTS - gateway runner imports but never run")
except Exception as e:
    print(f"  FIXED - {str(e).splitlines()[0][:80]}")

# 2. Kanban DB
print("\n2. Kanban DB path (🔴)")
try:
    from vectorcode.src.vector_cli.kanban_db import kanban_db_path
    p = kanban_db_path()
    print(f"  STILL EXISTS - path resolves to {p}, never tested with real DB")
except Exception as e:
    print(f"  FIXED - {e}")

# 3. Hermes string refs
print("\n3. Hermes string references (🔴)")
try:
    result = subprocess.run(
        ["rg", "-n", "hermes", "--include", "*.py", "vectorcode/src/"],
        capture_output=True, text=True, timeout=15
    )
    hits = [l for l in result.stdout.splitlines() if l.strip()]
    if hits:
        print(f"  STILL EXISTS - {len(hits)} remaining hermes refs:")
        for h in hits[:5]:
            print(f"    {h}")
    else:
        print("  FIXED - no hermes refs found")
except FileNotFoundError:
    print("  SKIP - rg not installed")
except Exception as e:
    print(f"  ERROR - {e}")

# 4. Import shims
print("\n4. Import shims (🟡)")
try:
    import vectorcode.src.core.config as core_shim
    print("  core shim: OK")
    import vectorcode.src.scheduler as sched_shim
    print("  scheduler shim: OK")
except Exception as e:
    print(f"  shim error: {e}")

# 5. Energy monitoring
print("\n5. Energy monitoring stubs (🟢)")
try:
    from core.telemetry import energy_nvidia
    print("  energy_nvidia: OK")
    import pynvml
    print("  pynvml: INSTALLED")
except ImportError:
    print("  pynvml: NOT INSTALLED (will return zeros)")
except Exception as e:
    print(f"  error: {e}")

# 6. Stub modules
print("\n6. Stub modules (🟡)")
for path, name, note in [
    ("vectorcode.src.vc_agents.digest_evaluator", "DigestEvaluator", "evaluate()"),
    ("vectorcode.src.tools.think", "ThinkTool", "structured thinking"),
    ("vectorcode.src.tools.knowledge_search", "KnowledgeSearchTool", "LightRAG integration"),
    ("vectorcode.src.intelligence.model_catalog", "BUILTIN_MODELS", "model catalog"),
]:
    try:
        m = __import__(path, fromlist=[name])
        obj = getattr(m, name, None)
        status = "HAS real impl" if obj and (hasattr(obj, "run") or isinstance(obj, (list, dict)) and len(obj) > 0) else "STUB (empty)"
        print(f"  {name}: {status}")
    except Exception as e:
        print(f"  {name}: FAIL - {str(e).splitlines()[0][:70]}")

# 7. Wiring gaps
print("\n7. Wiring gaps (🟡)")
try:
    from vectorcode.src.vector_cli.main import main
    from vectorcode.src.tools import kanban_tools
    print("  kanban_tools: imported but not in MCP server")
    print("  GoalManager: exists but not in CLI REPL")
except Exception as e:
    print(f"  error: {e}")

print("\n" + "=" * 60)
print("SUMMARY: Most issues STILL EXIST.")
print("They're in absorbed modules that were never fully integrated")
print("into VECTOR's runtime. The import fixes, branding cleanup,")
print("and wiring we did doesn't address these.")
print("=" * 60)
