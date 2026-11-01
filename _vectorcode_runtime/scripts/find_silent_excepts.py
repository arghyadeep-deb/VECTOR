"""Walk core/, parse AST, find silent except blocks.

Output CSV: file:line:type:category:handler_snippet

Categories:
  CRITICAL  — API routers, governor, event bus (must log error + return structured error)
  HOT_PATH  — autonomous loop intentional catches (keep, but add subsystem tag)
  OPTIONAL  — lazy import guards (keep debug level, add [VECTOR][imports] tag)
  BULK      — research_engine bulk upgrade to logger.warning
"""

import ast
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CORE = HERE / "core"

CATEGORIES = {
    "routers": "CRITICAL",
    "governor": "CRITICAL",
    "event_bus": "CRITICAL",
    "bus.py": "CRITICAL",
    "autonomous_loop": "HOT_PATH",
    "task_queue": "HOT_PATH",
    "obsidian_sync": "HOT_PATH",
    "health_monitor": "HOT_PATH",
    "research_engine": "BULK",
}


def classify(path: Path) -> str:
    rel = str(path.relative_to(HERE))
    for keyword, cat in CATEGORIES.items():
        if keyword in rel:
            return cat
    if "import" in rel or "importer" in rel:
        return "OPTIONAL"
    return "HOT_PATH"


def find_silent_excepts(filepath: Path) -> list[dict]:
    results = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"  [SKIP] {filepath.name}: syntax error - {e}", file=sys.stderr)
        return results

    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if handler.type is None:
                # bare `except:`
                pass
            elif isinstance(handler.type, ast.Name) and handler.type.id in (
                "Exception",
                "BaseException",
                "RuntimeError",
            ):
                pass
            else:
                continue

            body = handler.body
            if not body:
                continue

            first = body[0]
            lines = []
            for stmt in body:
                if isinstance(stmt, ast.Pass):
                    lines.append("pass")
                elif isinstance(stmt, ast.Raise):
                    lines.append("raise")
                elif isinstance(stmt, ast.Return):
                    if stmt.value is None:
                        lines.append("return None")
                    elif isinstance(stmt.value, ast.Constant) and stmt.value.value is None:
                        lines.append("return None")
                    elif isinstance(stmt.value, ast.Dict) and not stmt.value.keys:
                        lines.append("return {}")
                    else:
                        lines.append("return <value>")
                elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    func = stmt.value.func
                    if isinstance(func, ast.Attribute) and func.attr == "debug":
                        lines.append("logger.debug(...)")
                    elif isinstance(func, ast.Attribute) and func.attr == "error":
                        lines.append("logger.error(...)")
                    elif isinstance(func, ast.Attribute) and func.attr == "warning":
                        lines.append("logger.warning(...)")
                    elif isinstance(func, ast.Attribute) and func.attr == "info":
                        lines.append("logger.info(...)")
                    else:
                        lines.append("call")
                else:
                    lines.append("other")

            # Determine if this is truly "silent"
            is_silent = all(
                l in ("pass", "return None", "return {}", "logger.debug(...)") for l in lines
            )
            if not is_silent:
                continue

            category = classify(filepath)
            snippet = "; ".join(lines[:3])
            results.append(
                {
                    "file": str(filepath.relative_to(HERE)),
                    "line": node.lineno,
                    "col": node.col_offset,
                    "handler_line": handler.lineno,
                    "category": category,
                    "snippet": snippet,
                }
            )
    return results


CI_THRESHOLD = 200  # allow up to 200 HOT_PATH debug-only excepts


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true", help="CI mode: exit non-zero if count exceeds threshold")
    args = parser.parse_args()

    all_results = []
    py_files = sorted(CORE.rglob("*.py"))
    total = len(py_files)
    for i, fpath in enumerate(py_files, 1):
        rel = fpath.relative_to(HERE)
        if any(
            part.startswith("__") or part.startswith(".") or part == "venv"
            for part in fpath.parts
        ):
            continue
        print(f"[{i}/{total}] {rel}", file=sys.stderr)
        all_results.extend(find_silent_excepts(fpath))

    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=["file", "line", "col", "handler_line", "category", "snippet"],
    )
    writer.writeheader()
    writer.writerows(all_results)

    total = len(all_results)
    print(f"\nTotal: {total} silent except blocks", file=sys.stderr)
    cat_counts = {}
    for r in all_results:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
    for cat, count in sorted(cat_counts.items()):
        print(f"  {cat}: {count}", file=sys.stderr)

    if args.ci and total > CI_THRESHOLD:
        print(f"\nCI FAIL: {total} silent excepts exceeds threshold of {CI_THRESHOLD}", file=sys.stderr)
        sys.exit(1)
    elif args.ci:
        print(f"\nCI PASS: {total} silent excepts within threshold of {CI_THRESHOLD}", file=sys.stderr)


if __name__ == "__main__":
    main()
