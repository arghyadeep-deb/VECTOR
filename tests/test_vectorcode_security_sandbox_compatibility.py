"""Regressions for the VectorCode security and sandbox compatibility sweep."""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

from loguru import logger


REPO_ROOT = Path(__file__).resolve().parents[1]


def _assert_no_wildcard_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    wildcard_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == "*" for alias in node.names)
    ]
    assert wildcard_imports == []


def test_sec1_unsafe_safe_executor_and_legacy_importers_are_removed() -> None:
    unsafe_module = REPO_ROOT / "vectorcode/src/security/safe_executor.py"
    assert not unsafe_module.exists()

    importers: list[str] = []
    for root in (REPO_ROOT / "vectorcode", REPO_ROOT / "tests"):
        for path in root.rglob("*.py"):
            if path == Path(__file__).resolve():
                continue
            text = path.read_text(encoding="utf-8")
            if "security.safe_executor" in text or "SafeExecutor" in text:
                importers.append(path.relative_to(REPO_ROOT).as_posix())
    assert importers == []


def test_sec2_validation_log_contains_metadata_but_no_raw_values() -> None:
    from vectorcode.src.security.validator import InputValidator

    secret_content = "top-secret-content-9f3c"
    sensitive_path = "private/credentials.txt"
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="DEBUG", format="{message}")
    try:
        result = InputValidator().validate_tool_call(
            "write_file", {"path": sensitive_path, "content": secret_content}
        )
    finally:
        logger.remove(sink_id)

    assert result == {"path": sensitive_path, "content": secret_content}
    log_output = "".join(messages)
    assert "tool=write_file" in log_output
    assert "fields=content,path" in log_output
    assert f"lengths=content:{len(secret_content)},path:{len(sensitive_path)}" in log_output
    assert re.search(r"correlation_id=[0-9a-f]{32}\b", log_output)
    assert secret_content not in log_output
    assert sensitive_path not in log_output


def test_sec3_security_shims_are_explicit_and_point_to_canonical_namespace() -> None:
    expected_exports = {
        "credential_stripper.py": {"CredentialStripper", "wrap_tool_output"},
        "file_utils.py": {"secure_create", "secure_mkdir"},
        "injection_scanner.py": {"InjectionScanner", "InjectionScanResult"},
    }
    security_dir = REPO_ROOT / "vectorcode/src/security"

    for filename, exports in expected_exports.items():
        path = security_dir / filename
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        assert "vc_security" in (ast.get_docstring(tree) or "")
        _assert_no_wildcard_imports(path)

        module = importlib.import_module(f"vectorcode.src.security.{path.stem}")
        canonical = importlib.import_module(f"vectorcode.src.vc_security.{path.stem}")
        assert set(module.__all__) == exports
        for name in exports:
            assert getattr(module, name) is getattr(canonical, name)


def test_sandbox1_shims_are_explicit_compatibility_only_delegates() -> None:
    expected_exports = {
        "runner.py": {"ContainerRunner", "logger"},
        "mount_security.py": {
            "AllowedRoot",
            "DEFAULT_BLOCKED_PATTERNS",
            "MountAllowlist",
            "load_mount_allowlist",
            "validate_mount",
            "validate_mounts",
        },
        "wasm_runner.py": {"WasmResult", "WasmRunner", "create_sandbox_runner"},
    }
    sandbox_dir = REPO_ROOT / "vectorcode/src/sandbox"

    for filename, exports in expected_exports.items():
        path = sandbox_dir / filename
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        docstring = (ast.get_docstring(tree) or "").lower()
        assert "compatibility-only" in docstring
        assert "no independent" in docstring
        assert "core.sandbox" in docstring
        _assert_no_wildcard_imports(path)

        module = importlib.import_module(f"vectorcode.src.sandbox.{path.stem}")
        canonical = importlib.import_module(f"core.sandbox.{path.stem}")
        assert set(module.__all__) == exports
        for name in exports:
            assert getattr(module, name) is getattr(canonical, name)


if __name__ == "__main__":
    test_sec1_unsafe_safe_executor_and_legacy_importers_are_removed()
    test_sec2_validation_log_contains_metadata_but_no_raw_values()
    test_sec3_security_shims_are_explicit_and_point_to_canonical_namespace()
    test_sandbox1_shims_are_explicit_compatibility_only_delegates()
    logger.info("[VECTOR][test] security/sandbox compatibility regressions OK")
