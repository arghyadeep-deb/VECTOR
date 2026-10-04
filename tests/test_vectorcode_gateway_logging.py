"""Regression coverage for gateway modules using the project loguru contract."""

from __future__ import annotations

import ast
from pathlib import Path


GATEWAY_ROOT = Path("vectorcode/src/gateway")
EXCLUDED = {GATEWAY_ROOT / "run.py"}


def _production_files() -> list[Path]:
    return sorted(
        path
        for path in GATEWAY_ROOT.glob("*.py")
        if path not in EXCLUDED
    ) + sorted((GATEWAY_ROOT / "builtin_hooks").glob("*.py"))


def test_gateway_modules_do_not_use_or_shadow_loguru_with_stdlib_logging() -> None:
    violations: list[str] = []
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                if "logging" in names or getattr(node, "module", None) == "logging":
                    violations.append(f"{path}:{node.lineno}: stdlib logging import")
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "logger" for target in node.targets)
            ):
                violations.append(f"{path}:{node.lineno}: logger reassignment")

    assert not violations, "\n".join(violations)


def test_gateway_loguru_calls_do_not_use_printf_placeholders() -> None:
    violations: list[str] = []
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                continue
            message = node.args[0].value
            if any(token in message for token in ("%s", "%d", "%r", "%i", "%f")):
                violations.append(f"{path}:{node.lineno}: {message!r}")

    assert not violations, "\n".join(violations)


def test_gateway_runtime_modules_do_not_call_print() -> None:
    violations: list[str] = []
    for relative in ("hooks.py", "pairing.py", "session.py"):
        path = GATEWAY_ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                violations.append(f"{path}:{node.lineno}")

    assert not violations, "\n".join(violations)


def test_boot_hook_uses_asyncio_instead_of_threading_module() -> None:
    path = GATEWAY_ROOT / "builtin_hooks" / "boot_md.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert "threading" not in imports
