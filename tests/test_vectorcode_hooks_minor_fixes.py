"""Regression for small fixes across vectorcode/hooks/{lint_on_save,
auto_screenshot,auto_test,finish_notification}.py:

(1) lint_on_save.py's linter subprocess calls had no "--" separator before
file_path, so a file named e.g. "-rf" or starting with "-" could be parsed
as an option instead of a path by ruff/pyflakes.
(2) auto_screenshot.py/auto_test.py/finish_notification.py passed
exc_info=True to loguru, which silently ignores that stdlib-logging kwarg
(no traceback is ever actually logged) -- use logger.opt(exception=True).
"""
from __future__ import annotations

import ast
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent / "vectorcode" / "hooks"


def test_lint_on_save_linter_commands_include_separator_before_path():
    source = (HOOKS_DIR / "lint_on_save.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    linters_assign = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "linters" for t in node.targets)
    )
    for cmd_list in linters_assign.value.elts:
        values = [
            elt.value for elt in cmd_list.elts if isinstance(elt, ast.Constant)
        ]
        assert "--" in values, f"missing '--' separator in {values}"


def test_no_exc_info_true_remaining_in_fixed_hooks():
    for name in ("auto_screenshot.py", "auto_test.py", "finish_notification.py"):
        source = (HOOKS_DIR / name).read_text(encoding="utf-8")
        assert "exc_info=True" not in source, f"{name} still uses exc_info=True"
        assert "logger.opt(exception=True)" in source, (
            f"{name} should use logger.opt(exception=True)"
        )
