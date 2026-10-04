"""Regression coverage for the plugin security/correctness audit."""

from __future__ import annotations

import ast
import importlib.util
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "vectorcode" / "src" / "plugins"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_qe_security_bridge_rejects_prefix_sibling(tmp_path: Path):
    module = _load(PLUGINS / "bridges" / "qe_security_bridge.py", "audit_qe_security")
    allowed = tmp_path / "safe"
    sibling = tmp_path / "safe-evil" / "payload.py"
    allowed.mkdir()
    sibling.parent.mkdir()

    bridge = module.QESecurityBridge([str(allowed)])

    assert bridge.validate_path(str(allowed / "child.py")) is True
    assert bridge.validate_path(str(sibling)) is False


def test_meet_node_token_validation_uses_constant_time_compare(monkeypatch):
    module = _load(PLUGINS / "google_meet" / "node" / "protocol.py", "audit_meet_protocol")
    calls: list[tuple[str, str]] = []
    compare_digest = secrets.compare_digest

    def checked(candidate: str, expected: str) -> bool:
        calls.append((candidate, expected))
        return compare_digest(candidate, expected)

    monkeypatch.setattr(module.secrets, "compare_digest", checked)
    request = module.make_request("ping", "shared-secret", {}, req_id="1")

    assert module.validate_request(request, "shared-secret") == (True, "")
    assert calls == [("shared-secret", "shared-secret")]


def test_plugin_loggers_are_loguru_and_have_no_percent_placeholders():
    for path in PLUGINS.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, path)
        assert "logging.getLogger" not in source, path
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
            assert not any(marker in node.args[0].value for marker in ("%s", "%d", "%r", "%f")), path


def test_forbidden_requests_dependency_removed_from_plugins():
    offenders = []
    for path in PLUGINS.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "requests" for alias in node.names):
                offenders.append(path)
            if isinstance(node, ast.ImportFrom) and node.module == "requests":
                offenders.append(path)
    assert offenders == []


def test_teams_client_state_comparison_is_constant_time():
    source = (PLUGINS / "teams_pipeline" / "subscriptions.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "secrets"
        and node.func.attr == "compare_digest"
    ]
    assert calls, "client-state ownership checks must use secrets.compare_digest"


def test_meet_cli_fallback_does_not_close_over_deleted_exception_name():
    source = (PLUGINS / "google_meet" / "cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fallback = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_node_unavailable"
    )
    assert fallback.args.defaults, "fallback must capture the exception before except cleanup"
    loaded_names = {
        node.id
        for statement in fallback.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    assert "e" not in loaded_names
