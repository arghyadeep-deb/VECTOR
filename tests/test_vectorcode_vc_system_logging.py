"""Regression checks for VECTOR's loguru-only vc_system policy."""

import ast
from pathlib import Path


VC_SYSTEM = Path("vectorcode/src/vc_system")


def test_vc_system_does_not_use_stdlib_logging() -> None:
    for path in VC_SYSTEM.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports_logging = any(
            isinstance(node, ast.Import)
            and any(alias.name == "logging" for alias in node.names)
            for node in ast.walk(tree)
        )
        assert not imports_logging, f"stdlib logging import remains in {path}"


def test_vc_system_has_no_stdlib_logging_kwargs_or_percent_placeholders() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in VC_SYSTEM.glob("*.py")
    )
    assert "exc_info=True" not in combined
    for placeholder in ("%s", "%d", "%r"):
        assert placeholder not in combined
