"""Scan pass-only stubs excluding finagent / shadowbroker (domain-specific)."""
from __future__ import annotations
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SKIP_DIRS = {"__pycache__", "vector_finagent", "shadowbroker_server", "vector_backtest"}

def is_pass_only(node):
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return len(body) == 1 and isinstance(body[0], ast.Pass)

results = []
for root_dir in ["core", "districts", "vectorcode/src"]:
    for f in (REPO_ROOT / root_dir).rglob("*.py"):
        if SKIP_DIRS & set(f.parts):
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

print(f"Non-finagent/shadowbroker/backtest pass stubs: {len(results)}\n")
for fp, ln, nm in sorted(results):
    print(f"  {fp}:{ln}  {nm}")
