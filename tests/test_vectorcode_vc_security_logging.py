"""Regression tests for vc_security's loguru integration."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

from vectorcode.src.vc_security.subprocess_sandbox import run_sandboxed


SCOPE = Path("vectorcode/src/vc_security")
ENGINE_SCOPE = Path("vectorcode/src/engine")


def test_vc_security_uses_loguru_without_stdlib_logging() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "logging" for alias in node.names
            ):
                offenders.append(str(path))
            if isinstance(node, ast.ImportFrom) and node.module == "logging":
                offenders.append(str(path))
    assert offenders == []


def test_vc_security_loguru_calls_do_not_use_stdlib_exception_keyword() -> None:
    offenders: list[str] = []
    for path in sorted(SCOPE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if any(keyword.arg == "exc_info" for keyword in node.keywords):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == []


def test_subprocess_sandbox_uses_windows_process_group_flag() -> None:
    sentinel = object()
    process = type(
        "Process",
        (),
        {"communicate": lambda self, timeout: ("ok", ""), "returncode": 0},
    )()
    with (
        patch("vectorcode.src.vc_security.subprocess_sandbox.os.name", "nt"),
        patch(
            "vectorcode.src.vc_security.subprocess_sandbox.subprocess.CREATE_NEW_PROCESS_GROUP",
            sentinel,
            create=True,
        ),
        patch(
            "vectorcode.src.vc_security.subprocess_sandbox.subprocess.Popen",
            return_value=process,
        ) as popen,
    ):
        result = run_sandboxed("example --version")

    assert result.returncode == 0
    assert popen.call_args.kwargs["creationflags"] is sentinel
    assert "preexec_fn" not in popen.call_args.kwargs


def test_engine_loguru_calls_do_not_use_percent_placeholders() -> None:
    offenders: list[str] = []
    for path in sorted(ENGINE_SCOPE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            function = node.func
            if not (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "logger"
            ):
                continue
            message = node.args[0]
            if isinstance(message, ast.Constant) and isinstance(message.value, str):
                if any(marker in message.value for marker in ("%s", "%d", "%r")):
                    offenders.append(f"{path}:{node.lineno}")
    assert offenders == []


if __name__ == "__main__":
    test_vc_security_uses_loguru_without_stdlib_logging()
    test_vc_security_loguru_calls_do_not_use_stdlib_exception_keyword()
    test_subprocess_sandbox_uses_windows_process_group_flag()
    test_engine_loguru_calls_do_not_use_percent_placeholders()
    print("test_vectorcode_vc_security_logging.py OK")
