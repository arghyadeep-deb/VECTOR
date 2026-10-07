"""Static recurrence-control for VECTOR's established bug classes.

Post-audit improvement plan, gap 2. The 134-item whole-repo audit found the
same handful of bug classes recurring across dozens of unrelated files.
Codex's round-3 review (docs/plans/2026-10-07-improvement-debate.md) warned
against turning all of them into blocking static rules -- several (phantom
success, fail-open behavior) genuinely can't be caught this way, and the
ones that CAN be caught statically have wildly different existing-violation
counts in this codebase, checked directly before writing this file:

    flask import               ->   0 hand-written-scope files
    pickle import               ->   0 hand-written-scope files
    requests import              ->   9 hand-written-scope files
    threading.Thread()/Timer()    ->  80 hand-written-scope files
    os.environ direct secret read -> 150+ hand-written-scope files
    logger.X(..., exc_info=True) ->  90 hand-written-scope files

Turning the last three into a blocking gate tonight would mean either an
enormous, rushed, unreviewed grandfather list (which could silently miss
real problems) or immediately breaking CI on pre-existing, out-of-scope
debt. So this script has two tiers:

  BLOCKING  (--check, exit 1 on violation): flask, pickle, requests.
            requests keeps a small, explicitly reviewed grandfather list
            for pre-existing files; flask/pickle have none because the
            codebase is already clean.
  ADVISORY  (--report, always exits 0): threading.Thread()/Timer()
            instantiation, direct os.environ reads of secret-shaped names,
            and logger calls with exc_info=True. These print a tracked
            count/location report. Promoting any of them to BLOCKING is a
            separate, deliberate follow-up once a real grandfather list has
            been reviewed file-by-file -- not something to rush.

Usage:
    python scripts/bug_class_lint.py --check <file_or_dir> [...]   # blocking tier
    python scripts/bug_class_lint.py --report <file_or_dir> [...]  # advisory tier
    python scripts/bug_class_lint.py --check --report <dir>        # both

Exit code (--check only): 0 = clean, 1 = blocking violation(s) found.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Vendored / wiring-check-only trees are out of scope for both tiers -- same
# boundary the rest of this audit cycle has used throughout.
VENDORED_MARKERS = (
    "research_engine", "coding_assistant", "shadowbroker_server",
    "vector_social_sim", "vector_backtest", "vector_finagent",
    "vector_hedgebot", "legacy_ported",
)

BANNED_IMPORTS_BLOCKING = {"flask", "pickle", "requests"}

# Explicitly reviewed, 2026-10-07. Each of these predates this check and is
# tracked rather than silently exempted -- remove an entry here only
# alongside an actual migration to httpx, not to silence a new violation.
REQUESTS_GRANDFATHER = {
    "districts/coding/vector_mlops/agent/tools/github_find_examples.py",
    "districts/coding/vector_mlops/agent/tools/github_list_repos.py",
    "districts/coding/vector_mlops/agent/tools/github_read_file.py",
    "districts/coding/vector_mlops/agent/tools/web_search_tool.py",
    "vectorcode/src/tools/browser_camofox.py",
    "vectorcode/src/tools/browser_providers/browserbase.py",
    "vectorcode/src/tools/browser_providers/browser_use.py",
    "vectorcode/src/tools/browser_providers/firecrawl.py",
    "vectorcode/src/tools/browser_tool.py",
}

_SECRET_NAME_RE = re.compile(r"^[A-Z_]*(KEY|TOKEN|SECRET|PASSWORD|PASS)[A-Z_]*$")


@dataclass
class Finding:
    path: Path
    line: int
    rule: str
    message: str


@dataclass
class LintResult:
    blocking: list[Finding] = field(default_factory=list)
    advisory: list[Finding] = field(default_factory=list)


def _is_vendored(path: Path) -> bool:
    parts = set(path.parts)
    return any(marker in parts for marker in VENDORED_MARKERS)


def _relpath(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _iter_py_files(targets: list[Path]):
    for target in targets:
        if target.is_file() and target.suffix == ".py":
            if not _is_vendored(target):
                yield target
            continue
        if not target.is_dir():
            continue
        for path in target.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _is_vendored(path):
                continue
            yield path


def _parse(path: Path) -> ast.Module | None:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None


def _imported_top_level_names(node: ast.AST) -> list[tuple[str, int]]:
    """Return (module_name, lineno) for every import/import-from in a module."""
    names: list[tuple[str, int]] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for alias in n.names:
                names.append((alias.name.split(".")[0], n.lineno))
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                names.append((n.module.split(".")[0], n.lineno))
    return names


def check_banned_imports(path: Path, tree: ast.Module, result: LintResult) -> None:
    rel = _relpath(path)
    for module_name, lineno in _imported_top_level_names(tree):
        if module_name not in BANNED_IMPORTS_BLOCKING:
            continue
        if module_name == "requests" and rel in REQUESTS_GRANDFATHER:
            continue
        result.blocking.append(Finding(
            path, lineno, "banned-import",
            f"import of banned module '{module_name}' (use httpx instead of requests; "
            f"flask/pickle are banned project-wide)",
        ))


def report_threading_thread(path: Path, tree: ast.Module, result: LintResult) -> None:
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        func = n.func
        name = None
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            name = f"{func.value.id}.{func.attr}"
        if name in ("threading.Thread", "threading.Timer"):
            result.advisory.append(Finding(
                path, n.lineno, "threading-instantiation",
                f"{name}(...) -- project policy prefers asyncio; tracked, not yet blocking "
                f"(80-file existing surface, needs a reviewed migration pass, not a rushed ban)",
            ))


def report_env_secret_access(path: Path, tree: ast.Module, result: LintResult) -> None:
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        func = n.func
        if not (isinstance(func, ast.Attribute) and func.attr == "get"):
            continue
        value = func.value
        if not (isinstance(value, ast.Attribute) and value.attr == "environ"):
            continue
        if not n.args:
            continue
        first = n.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            if _SECRET_NAME_RE.match(first.value):
                result.advisory.append(Finding(
                    path, n.lineno, "env-secret-direct-read",
                    f"os.environ.get({first.value!r}) -- secret-shaped name read directly "
                    f"instead of core.security.secrets_manager.get_secret() (keyring-first); "
                    f"tracked, not yet blocking (150+-file existing surface)",
                ))


def report_loguru_exc_info(path: Path, tree: ast.Module, result: LintResult) -> None:
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        func = n.func
        if not (isinstance(func, ast.Attribute) and func.attr in
                ("debug", "info", "warning", "error", "critical", "exception")):
            continue
        for kw in n.keywords:
            if kw.arg == "exc_info":
                result.advisory.append(Finding(
                    path, n.lineno, "loguru-exc-info-misuse",
                    "logger.X(..., exc_info=True) -- loguru silently ignores exc_info; "
                    "use logger.opt(exception=True).X(...) instead; tracked, not yet "
                    "blocking (90-file existing surface, needs per-call-site review)",
                ))


def lint_file(path: Path, result: LintResult, *, check: bool, report: bool) -> None:
    tree = _parse(path)
    if tree is None:
        return
    if check:
        check_banned_imports(path, tree, result)
    if report:
        report_threading_thread(path, tree, result)
        report_env_secret_access(path, tree, result)
        report_loguru_exc_info(path, tree, result)


def run(targets: list[Path], *, check: bool, report: bool) -> LintResult:
    result = LintResult()
    for path in _iter_py_files(targets):
        lint_file(path, result, check=check, report=report)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", default=["core", "districts", "vectorcode/src", "run_vector.py"])
    parser.add_argument("--check", action="store_true", help="run the blocking tier")
    parser.add_argument("--report", action="store_true", help="run the advisory tier")
    args = parser.parse_args(argv)

    if not args.check and not args.report:
        args.check = True  # default to the safe, blocking-only tier

    targets = [REPO_ROOT / t if not Path(t).is_absolute() else Path(t) for t in args.targets]
    result = run(targets, check=args.check, report=args.report)

    if result.blocking:
        print(f"[bug_class_lint] BLOCKING: {len(result.blocking)} violation(s):")
        for f in result.blocking:
            print(f"  {_relpath(f.path)}:{f.line}: [{f.rule}] {f.message}")

    if args.report:
        by_rule: dict[str, int] = {}
        for f in result.advisory:
            by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
        if result.advisory:
            print(f"[bug_class_lint] ADVISORY: {len(result.advisory)} finding(s) ({by_rule}):")
            for f in result.advisory:
                print(f"  {_relpath(f.path)}:{f.line}: [{f.rule}] {f.message}")
        else:
            print("[bug_class_lint] ADVISORY: no findings")

    if result.blocking:
        return 1
    print("[bug_class_lint] BLOCKING tier: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
