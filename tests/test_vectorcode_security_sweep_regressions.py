"""Focused regressions for the Phase 3 vc_security/vc_mcp sweep."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from vectorcode.src.vc_security import SecurityInitializationError, setup_security
from vectorcode.src.vc_security.capabilities import CapabilityPolicy
from vectorcode.src.vc_security import audit as audit_module
from vectorcode.src.vc_core.types import ToolResult
from vectorcode.src.vc_mcp.protocol import MCPRequest
from vectorcode.src.vc_mcp.server import MCPServer
from vectorcode.src.vc_tools._abc import BaseTool, ToolSpec


def _security_config(**overrides):
    values = {
        "enabled": True,
        "secret_scanner": True,
        "pii_scanner": True,
        "mode": "redact",
        "scan_input": True,
        "scan_output": True,
        "audit_log_path": ":memory:",
        "capabilities": SimpleNamespace(enabled=False, policy_path=""),
    }
    values.update(overrides)
    return SimpleNamespace(security=SimpleNamespace(**values))


def test_vcsec1_enabled_scanner_initialization_fails_closed(monkeypatch):
    def broken_scanner():
        raise RuntimeError("scanner unavailable")

    monkeypatch.setattr("vectorcode.src.vc_security.SecretScanner", broken_scanner)

    with pytest.raises(SecurityInitializationError, match="scanner controls"):
        setup_security(_security_config(), object())


def test_vcsec1_enabled_capability_initialization_fails_closed(monkeypatch):
    class BrokenPolicy:
        def __init__(self, **_kwargs):
            raise RuntimeError("policy unavailable")

    monkeypatch.setattr(
        "vectorcode.src.vc_security.capabilities.CapabilityPolicy", BrokenPolicy
    )
    config = _security_config(
        secret_scanner=False,
        pii_scanner=False,
        capabilities=SimpleNamespace(enabled=True, policy_path="policy.json"),
    )

    with pytest.raises(SecurityInitializationError, match="capability policy"):
        setup_security(config, object())


def test_vcsec1_enabled_audit_initialization_fails_closed(monkeypatch):
    def broken_audit(**_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr("vectorcode.src.vc_security.AuditLogger", broken_audit)
    config = _security_config(secret_scanner=False, pii_scanner=False)

    with pytest.raises(SecurityInitializationError, match="audit control"):
        setup_security(config, object())


def test_vcsec3_capability_policy_denies_unknown_agents_by_default():
    policy = CapabilityPolicy()

    assert policy.check("unknown-agent", "code:execute") is False


@pytest.mark.parametrize("content", [None, "not-json", "{}", '{"agents": [{}]}'])
def test_vcsec3_configured_policy_must_exist_and_be_well_formed(tmp_path, content):
    path = tmp_path / "capabilities.json"
    if content is not None:
        path.write_text(content)

    expected = FileNotFoundError if content is None else ValueError
    with pytest.raises(expected):
        CapabilityPolicy(policy_path=str(path))


class _ConsequentialTool(BaseTool):
    called = False

    @property
    def spec(self):
        return ToolSpec(
            name="regression_write",
            description="Regression-only consequential tool",
            required_capabilities=["file:write"],
        )

    def execute(self, **_params):
        self.called = True
        return ToolResult(tool_name=self.spec.name, content="executed", success=True)


def test_vcmcp1_ungated_consequential_tool_call_is_refused():
    tool = _ConsequentialTool()
    server = MCPServer(tools=[tool])

    response = server.handle(
        MCPRequest(
            method="tools/call",
            params={"name": tool.spec.name, "arguments": {}},
            id=1,
        )
    )

    assert response.error is not None
    assert "authorization unavailable" in response.error["message"]
    assert tool.called is False


def test_vcsec4_audit_store_refuses_plaintext_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(audit_module, "_USE_SQLCIPHER", False)
    monkeypatch.setattr(audit_module, "sqlcipher", None)

    with pytest.raises(RuntimeError, match="plaintext fallback is forbidden"):
        audit_module.AuditLogger(tmp_path / "audit.db")

    assert not (tmp_path / "audit.db").exists()
