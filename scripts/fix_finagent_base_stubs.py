"""Fix pass-only stubs in finagent base classes -> raise NotImplementedError."""
from __future__ import annotations
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FINAGENT = REPO_ROOT / "districts/investment/vector_finagent"

# Only fix files whose name contains 'base'
LOG_PASS_METHODS = {"disconnect", "close", "test_connection"}


def _class_name_at(tree: ast.Module, lineno: int) -> str:
    best = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.lineno <= lineno <= node.end_lineno:
                best = node.name
    return best


def _is_pass_only(node):
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _is_abstract(node) -> bool:
    for decorator in node.decorator_list:
        name = decorator.id if isinstance(decorator, ast.Name) else getattr(decorator, "attr", "")
        if name == "abstractmethod":
            return True
    return False


def fix_file(path: Path, dry_run: bool = True) -> int:
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except Exception as e:
        print(f"  SKIP: {path.name} — {e}")
        return 0

    lines = src.splitlines(keepends=True)
    changes = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_pass_only(node):
            continue

        fname = node.name
        if fname not in LOG_PASS_METHODS and not _is_abstract(node):
            continue
        cls_name = _class_name_at(tree, node.lineno)

        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            pass_node = body[1] if len(body) > 1 else None
        else:
            pass_node = body[0] if body else None

        if pass_node is None or not isinstance(pass_node, ast.Pass):
            continue

        pass_lineno = pass_node.lineno
        old_line = lines[pass_lineno - 1]
        indent = re.match(r"(\s*)", old_line).group(1)

        if fname in LOG_PASS_METHODS:
            mod = path.stem
            new_line = f'{indent}from loguru import logger\n{indent}logger.debug("[VECTOR][{mod}] {fname} called (no-op)")\n'
        else:
            cls_prefix = f"{cls_name}." if cls_name else ""
            new_line = f'{indent}raise NotImplementedError("{cls_prefix}{fname} must be implemented by subclass")\n'

        changes.append((pass_lineno, new_line))

    if not changes:
        return 0

    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    print(f"  {len(changes)} fixes in {rel}")
    if dry_run:
        return len(changes)

    for ln, new_line in sorted(changes, key=lambda x: x[0], reverse=True):
        lines[ln - 1] = new_line

    path.write_text("".join(lines), encoding="utf-8")
    return len(changes)


def main():
    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("DRY RUN — pass --apply to write\n")

    total = 0
    for f in sorted(FINAGENT.rglob("*base*.py")):
        if "__pycache__" in f.parts:
            continue
        total += fix_file(f, dry_run=dry_run)

    print(f"\nTotal {'would fix' if dry_run else 'fixed'}: {total}")


if __name__ == "__main__":
    main()
