"""Fix ALL remaining issues across VECTOR codebase."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(ROOT))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vectorcode" / "src"))

print("=" * 60)
print("FIX EVERYTHING — comprehensive repair")
print("=" * 60)

# ── 1. Hermes docstring sweep ────────────────────────────
print("\n--- 1. Hermes docstring sweep ---")
count = 0
for root, dirs, files in os.walk("vectorcode/src"):
    if "__pycache__" in root:
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        fp = os.path.join(root, f)
        text = open(fp, encoding="utf-8", errors="replace").read()
        original = text
        for pattern, replacement in [
            ("hermes tools", "vector tools"),
            ("hermes doctor", "vector doctor"),
            ("hermes setup", "vector setup"),
            ("hermes-cli", "vector-cli"),
            ("hermes/openclaw", "vector/openclaw"),
            ("hermes_constants", "vectorcode.src.vector_constants"),
            ("hermes_cli", "vectorcode.src.vector_cli"),
        ]:
            text = text.replace(pattern, replacement)
        if text != original:
            open(fp, "w", encoding="utf-8").write(text)
            count += 1
            print(f"  {os.path.relpath(fp, ROOT)}")

print(f"  {count} files updated")

# ── 2. Comprehensive import scan ─────────────────────────
print("\n--- 2. Comprehensive import scan ---")
modules_to_scan = []
for root, dirs, files in os.walk("vectorcode/src"):
    if "__pycache__" in root:
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        fp = Path(os.path.join(root, f))
        rel = fp.relative_to(ROOT / "vectorcode" / "src")
        mod_name = "vectorcode.src." + str(rel.with_suffix("")).replace(os.sep, ".")
        modules_to_scan.append(mod_name)

# Also scan core modules
for root, dirs, files in os.walk("core"):
    if "__pycache__" in root:
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        fp = Path(os.path.join(root, f))
        rel = fp.relative_to(ROOT)
        mod_name = str(rel.with_suffix("")).replace(os.sep, ".")
        modules_to_scan.append(mod_name)

total = len(modules_to_scan)
ok = 0
fail = 0
errors: dict[str, list[tuple[str, str]]] = {}

for i, mod_name in enumerate(modules_to_scan):
    if i % 500 == 0 and i > 0:
        print(f"  progress: {i}/{total}")
    try:
        importlib.import_module(mod_name)
        ok += 1
    except Exception as e:
        fail += 1
        err_msg = str(e).splitlines()[0][:100]
        err_type = err_msg.split(":")[0] if ":" in err_msg else err_msg
        if err_type not in errors:
            errors[err_type] = []
        errors[err_type].append((mod_name, err_msg))

print(f"\n  Total: {total}, OK: {ok}, FAIL: {fail}")
if errors:
    print(f"\n  Error breakdown:")
    for err_type, mods in sorted(errors.items(), key=lambda x: -len(x[1])):
        print(f"    {err_type}: {len(mods)}")
        for m, e in mods[:3]:
            print(f"      {m}: {e[:80]}")

# ── 3. Wire kanban_tools into MCP ────────────────────────
print("\n--- 3. Wire kanban_tools into MCP ---")
mcp_path = ROOT / "core" / "mcp_server.py"
mcp_text = mcp_path.read_text(encoding="utf-8")
if "kanban" not in mcp_text:
    # Find a good insertion point
    insert_point = mcp_text.find("def recall_memory")
    if insert_point > 0:
        kanban_wiring = '''
    @mcp.tool
    def kanban_board(board_id: str | None = None) -> str:
        """Get kanban board(s) — list all boards or get a specific one."""
        try:
            from vectorcode.src.tools.kanban_tools import KanbanBoardTool
            tool = KanbanBoardTool()
            result = tool.run(board_id=board_id)
            return str(result)
        except Exception as e:
            return f"kanban unavailable: {e}"

'''
        mcp_text = mcp_text[:insert_point] + kanban_wiring + mcp_text[insert_point:]
        mcp_path.write_text(mcp_text, encoding="utf-8")
        print("  kanban_tools wired into MCP server")
    else:
        print("  SKIP - could not find insertion point")
else:
    print("  Already wired")

# ── 4. Install nvidia-ml-py ──────────────────────────────
print("\n--- 4. Install nvidia-ml-py ---")
try:
    import nvidia_ml_py
    print("  Already installed")
except ImportError:
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "nvidia-ml-py"],
        capture_output=True, text=True, timeout=60
    )
    if r.returncode == 0:
        print("  Installed: nvidia-ml-py")
    else:
        print(f"  FAIL: {r.stderr.splitlines()[-2][:80]}")

print("\nDone.")
