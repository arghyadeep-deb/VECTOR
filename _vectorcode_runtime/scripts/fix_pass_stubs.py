"""
Fix pass-only stubs in ABC base classes → raise NotImplementedError.
Also handles specific non-base cases (stop/disconnect/rollback → debug log).

Dry-run by default; pass --apply to write changes.
"""
from __future__ import annotations
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Files where pass is intentional — skip entirely
SKIP_EXACT_FILES = {
    "core/coding_assistant/cli/turn_summary/noop.py",  # named noop, intentional
    "core/coding_assistant/acp/utils.py",              # ACP empty init
    "vectorcode/src/memory/manager.py",                # _FakeProvider test double
    "vectorcode/src/evals/tests/conftest.py",          # MockDataset test fixture
}

# Method names where pass → debug log (not NIE) because they are optional lifecycle hooks
LOG_PASS_METHODS = {
    "stop", "disconnect", "close", "rollback",
    "on_narrator_state_change", "on_transcribe_state_change",
    "on_voice_mode_change", "on_transcribe_text",
    "sync_turn", "queue_prefetch",
    "_before_execute",
    "send_typing", "stop_typing",
    "on_run_start", "on_result", "on_run_end",
    "handle_app_mention", "handle_file_shared", "handle_file_created", "handle_file_change",
    "print", "print_turn_complete",
    "set_seed",
}

# Method names that silence noisy output intentionally — keep as pass
INTENTIONAL_PASS_METHODS = {
    "log_message",  # HTTPServer silence pattern
}

# Method names that are scorer/trainer __init__ — keep pass (empty initializer is fine)
SKIP_INIT_CLASSES_SUBSTR = {"Scorer", "Trainer", "Optimizer"}


def _class_name_at(tree: ast.Module, lineno: int) -> str:
    """Return the class name that contains the function at lineno, or ''."""
    best = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.lineno <= lineno <= node.end_lineno:
                best = node.name
    return best


def _is_pass_only(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return len(body) == 1 and isinstance(body[0], ast.Pass)


def _is_abstract(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Only explicit abstract methods are safe to turn into hard failures."""
    for decorator in node.decorator_list:
        name = decorator.id if isinstance(decorator, ast.Name) else getattr(decorator, "attr", "")
        if name == "abstractmethod":
            return True
    return False


def _fix_file(path: Path, dry_run: bool = True) -> int:
    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    if rel in SKIP_EXACT_FILES:
        return 0

    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception as e:
        print(f"  SKIP (parse error): {rel} — {e}")
        return 0

    lines = src.splitlines(keepends=True)
    changes: list[tuple[int, str, str]] = []  # (lineno of pass, old_line, new_line)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_pass_only(node):
            continue

        fname = node.name
        if fname in INTENTIONAL_PASS_METHODS:
            continue

        if fname not in LOG_PASS_METHODS and not _is_abstract(node):
            continue

        cls_name = _class_name_at(tree, node.lineno)

        # Skip scorer/trainer __init__
        if fname == "__init__" and any(s in cls_name for s in SKIP_INIT_CLASSES_SUBSTR):
            continue

        # Find the `pass` line
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            pass_node = body[1] if len(body) > 1 else None
        else:
            pass_node = body[0] if body else None

        if pass_node is None or not isinstance(pass_node, ast.Pass):
            continue

        pass_lineno = pass_node.lineno  # 1-based
        old_line = lines[pass_lineno - 1]
        indent = re.match(r"(\s*)", old_line).group(1)

        if fname in LOG_PASS_METHODS:
            mod_part = rel.split("/")[-1].replace(".py", "")
            new_line = f'{indent}from loguru import logger\n{indent}logger.debug("[VECTOR][{mod_part}] {fname} called (no-op)")\n'
        else:
            # raise NotImplementedError
            cls_prefix = f"{cls_name}." if cls_name else ""
            new_line = f'{indent}raise NotImplementedError("{cls_prefix}{fname} must be implemented by subclass")\n'

        changes.append((pass_lineno, old_line, new_line))

    if not changes:
        return 0

    print(f"  {len(changes)} fixes in {rel}")
    if dry_run:
        for ln, old, new in changes:
            print(f"    line {ln}: pass  ->  {new.strip()!r}")
        return len(changes)

    # Apply in reverse order so line numbers stay valid
    for ln, old, new in sorted(changes, key=lambda x: x[0], reverse=True):
        lines[ln - 1] = new

    path.write_text("".join(lines), encoding="utf-8")
    return len(changes)


def main() -> None:
    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("DRY RUN — pass --apply to write changes\n")

    total = 0
    target_dirs = [
        "core/research_engine",
        "core/trading/llm_clients",
        "core/scraper",
        "core/stealth_browser",
        "core/video",
        "vectorcode/src/gateway/platforms",
        "vectorcode/src/comms",
        "vectorcode/src/connectors",
        "vectorcode/src/evals",
        "vectorcode/src/learning",
        "vectorcode/src/plugins",
        "vectorcode/src/providers",
        "vectorcode/src/tools/environments",
        "vectorcode/src/memory",
        "vectorcode/src/skills",
        "vectorcode/src/tui_gateway",
        "vectorcode/src/vector_cli",
        "core/coding_assistant/core",
        "core/coding_assistant/cli",
        "districts/coding/vector_mlops",
    ]

    for d in target_dirs:
        dpath = REPO_ROOT / d
        if not dpath.exists():
            continue
        for f in sorted(dpath.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            total += _fix_file(f, dry_run=dry_run)

    print(f"\nTotal {'would fix' if dry_run else 'fixed'}: {total} stubs")


if __name__ == "__main__":
    main()
