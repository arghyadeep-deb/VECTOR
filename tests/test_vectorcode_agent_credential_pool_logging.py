"""Regression coverage for credential-pool diagnostics using loguru correctly."""

from __future__ import annotations

import ast
from pathlib import Path


MODULE = Path("vectorcode/src/agent/credential_pool.py")


def test_credential_pool_does_not_shadow_loguru_with_stdlib_logging() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))

    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            isinstance(node, ast.Import)
            and any(alias.name == "logging" for alias in node.names)
            or isinstance(node, ast.ImportFrom)
            and node.module == "logging"
        )
        for node in tree.body
    )
    assert not any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "logger" for target in node.targets)
        for node in tree.body
    )


def test_credential_pool_log_calls_do_not_use_printf_placeholders() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    printf_tokens = ("%s", "%d", "%r", "%i", "%f")

    bad_calls: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "logger":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        message = node.args[0].value
        if isinstance(message, str) and any(token in message for token in printf_tokens):
            bad_calls.append((node.lineno, message))

    assert bad_calls == []
