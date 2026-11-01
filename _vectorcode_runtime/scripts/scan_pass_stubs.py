"""Scan for functions whose entire body is `pass` (after optional docstring)."""
from __future__ import annotations
import ast
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

def is_pass_only(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = node.body
    # skip docstring
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return len(body) == 1 and isinstance(body[0], ast.Pass)

results: list[tuple[str, int, str]] = []

for root_dir in ["core", "districts", "vectorcode/src"]:
    for f in (REPO_ROOT / root_dir).rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if is_pass_only(node):
                    rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
                    results.append((rel, node.lineno, node.name))

print(f"Total pass-only stubs: {len(results)}\n")

by_file: Counter[str] = Counter(fp for fp, _, _ in results)
print("Top 25 files by count:")
for fp, cnt in by_file.most_common(25):
    print(f"  {cnt:4d}  {fp}")

# Also show by directory
by_dir: Counter[str] = Counter()
for fp, _, _ in results:
    parts = fp.split("/")
    top = "/".join(parts[:3]) if len(parts) >= 3 else fp
    by_dir[top] += 1

print("\nBy directory (top 20):")
for d, cnt in by_dir.most_common(20):
    print(f"  {cnt:4d}  {d}")
