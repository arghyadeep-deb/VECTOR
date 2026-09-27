"""Static guard: async functions must not call blocking subprocess / sleep primitives inline.

The API, the autonomous loop and the HUD websockets share one event loop; one `subprocess.run` inside an `async def` freezes all of
them for its duration (found 2026-09-27: docker info, nvidia-smi, the nightly compileall + smoke run of up to 15 minutes, and the
emergency / incident / resilience paths). Wrap the call in `await asyncio.to_thread(...)` (or use `asyncio.sleep`).
Vendored trees (shadowbroker, vector_mlops) are excluded.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

_BLOCKING = {("time", "sleep"), ("subprocess", "run"), ("subprocess", "check_output"), ("subprocess", "call"),
             ("subprocess", "check_call")}
_SKIP = ("shadowbroker", "vector_mlops", "__pycache__")


def _inline_blocking_calls():
    hits = []
    for base in ("core", "districts"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if any(s in rel for s in _SKIP):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.AsyncFunctionDef):
                    continue
                stack = list(fn.body)
                while stack:
                    node = stack.pop()
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                        continue        # a nested sync def is its own scope (typically the body handed to to_thread)
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and isinstance(node.func.value, ast.Name)
                            and (node.func.value.id, node.func.attr) in _BLOCKING):
                        hits.append(f"{rel}:{node.lineno} in async {fn.name}: {node.func.value.id}.{node.func.attr}")
                    stack.extend(ast.iter_child_nodes(node))
    return sorted(hits)


def test_no_async_function_calls_a_blocking_primitive_inline():
    hits = _inline_blocking_calls()
    assert not hits, "blocking calls inside async functions (wrap in asyncio.to_thread):\n" + "\n".join(hits)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
