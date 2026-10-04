"""Regression test for the context compressor's required logging backend."""

from __future__ import annotations

import ast
from pathlib import Path


MODULE = (
    Path(__file__).resolve().parents[1]
    / "vectorcode"
    / "src"
    / "agent"
    / "context_compressor.py"
)


def test_context_compressor_uses_loguru_placeholders_only() -> None:
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            any(alias.name == "logging" for alias in node.names)
            if isinstance(node, ast.Import)
            else node.module == "logging"
        )
        for node in tree.body
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "logger":
            continue
        if isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            message = node.args[0].value
            assert "%s" not in message and "%d" not in message and "%r" not in message
