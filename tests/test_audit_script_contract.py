"""Regression tests for repository audit-tool assumptions."""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_wiring_audit_uses_its_checked_out_repository_root():
    source = (ROOT / "scripts" / "audit_all_wiring.py").read_text(encoding="utf-8")

    assert "Path(__file__).resolve().parents[1]" in source
    assert "C:\\Users\\Arghyadeep\\Desktop\\V.E.C.T.O.R" not in source


def test_integration_audit_checks_real_voice_method_and_research_registration():
    source = (ROOT / "scripts" / "full_integration_audit.py").read_text(encoding="utf-8")

    assert "MistralTTSClient.speak" in source
    assert "MistralTTSClient.synthesize" not in source
    assert "core.mcp_tools.research" in source
    assert "add_research_tools" in source


def test_wiring_audit_counts_the_javascript_runtime_once():
    source = (ROOT / "scripts" / "audit_all_wiring.py").read_text(encoding="utf-8")

    assert 'check("core/video/runtime/vector_runtime.js"' not in source
    assert 'js_wired = "_RUNTIME_JS"' in source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
