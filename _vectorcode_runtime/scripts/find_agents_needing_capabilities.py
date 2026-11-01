"""Find all district agents that have run() but no self.capabilities."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISTRICTS = ROOT / "districts"

needs_caps = []
has_caps = []

for py_file in sorted(DISTRICTS.rglob("*.py")):
    content = py_file.read_text(encoding="utf-8", errors="replace")

    # Must have async def run(self, task
    if not re.search(r'async def run\(self,\s*task', content):
        continue

    # Skip __init__.py files
    if py_file.name == "__init__.py":
        continue

    rel = py_file.relative_to(ROOT)

    if re.search(r'self\.capabilities\s*=\s*\[', content):
        has_caps.append(str(rel))
    else:
        needs_caps.append(str(rel))

print(f"=== AGENTS WITH run() BUT NO self.capabilities: {len(needs_caps)} ===")
for f in needs_caps:
    print(f"  {f}")

print(f"\n=== AGENTS WITH run() AND self.capabilities: {len(has_caps)} ===")
for f in has_caps:
    print(f"  {f}")
