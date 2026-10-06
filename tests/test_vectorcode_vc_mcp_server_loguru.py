"""Regression for vectorcode/src/vc_mcp/server.py: the module imported
stdlib `logging` and built its logger via `logging.getLogger(__name__)`
instead of loguru, violating CLAUDE.md's "loguru everywhere, never
print()/stdlib logging" rule. It also used `exc_info=True` (silently
ignored by loguru) and %-style placeholders (silently non-functional
under loguru's {}-style formatting).
"""
from __future__ import annotations

import ast
from pathlib import Path

_SOURCE = Path("vectorcode/src/vc_mcp/server.py").read_text(encoding="utf-8")


def test_server_does_not_import_stdlib_logging() -> None:
    tree = ast.parse(_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name == "logging" for alias in node.names), (
                "vc_mcp/server.py must not import stdlib logging"
            )


def test_server_uses_loguru_logger() -> None:
    from vectorcode.src.vc_mcp import server

    assert type(server.logger).__module__.startswith("loguru")


def test_server_has_no_percent_style_placeholders_or_exc_info() -> None:
    assert "exc_info=True" not in _SOURCE
    assert "%r" not in _SOURCE
    assert "%s" not in _SOURCE
