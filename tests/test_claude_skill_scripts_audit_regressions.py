"""Regression coverage for the owner-authored Claude skill scripts audit."""

from __future__ import annotations

import importlib.util
import subprocess
from email.message import EmailMessage
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(relative_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_email_attachment_filename_cannot_escape_output_directory(tmp_path):
    module = _load(
        ".claude/skills/analyzing-email-headers-for-phishing-investigation/scripts/agent.py",
        "email_skill_agent",
    )
    message = EmailMessage()
    message.set_content("body")
    message.add_attachment(b"evidence", maintype="application", subtype="octet-stream", filename="../escape.bin")

    attachments = module.extract_attachments(message, tmp_path / "attachments")

    saved = Path(attachments[0]["saved_to"]).resolve()
    output_root = (tmp_path / "attachments").resolve()
    assert saved.parent == output_root
    assert not (tmp_path / "escape.bin").exists()


def test_cloudtrail_collection_failure_is_not_a_clean_empty_result(monkeypatch):
    module = _load(
        ".claude/skills/analyzing-cloud-storage-access-patterns/scripts/agent.py",
        "cloud_storage_skill_agent",
    )
    failed = subprocess.CompletedProcess(["aws"], 2, stdout="", stderr="denied")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: failed)

    with pytest.raises(module.CollectionError, match="denied"):
        module.query_cloudtrail_s3_events("sensitive")


def test_current_cloudtrail_events_are_not_used_as_the_known_ip_baseline():
    module = _load(
        ".claude/skills/analyzing-cloud-storage-access-patterns/scripts/agent.py",
        "cloud_storage_baseline_skill_agent",
    )
    events = [{"source_ip": "203.0.113.9", "event_name": "GetObject", "user_arn": "u", "key": "k"}]

    assert module.known_ips_for_analysis(events, None) == set()
    assert len(module.detect_new_source_ips(events, module.known_ips_for_analysis(events, None))) == 1


def test_api_full_analysis_includes_unusual_method_detector():
    source = (ROOT / ".claude/skills/analyzing-api-gateway-access-logs/scripts/agent.py").read_text(
        encoding="utf-8"
    )
    assert '"unusual_methods"' in source
    assert '"unusual"' in source


def test_ipv4_enrichment_uses_virustotal_ip_endpoint(monkeypatch):
    module = _load(
        ".claude/skills/analyzing-indicators-of-compromise/scripts/agent.py",
        "ioc_skill_agent",
    )
    calls = []
    monkeypatch.setattr(module, "HAS_REQUESTS", True)
    monkeypatch.setattr(module, "query_abuseipdb", lambda *args: None)
    monkeypatch.setattr(module, "query_virustotal_ip", lambda value, key: calls.append((value, key)))

    module.enrich_ioc("203.0.113.9", vt_key="key", abuse_key="abuse")

    assert calls == [("203.0.113.9", "key")]


def test_network_skills_use_approved_http_and_secret_abstractions():
    apt_source = (ROOT / ".claude/skills/analyzing-apt-group-with-mitre-navigator/scripts/agent.py").read_text(
        encoding="utf-8"
    )
    ioc_source = (ROOT / ".claude/skills/analyzing-indicators-of-compromise/scripts/agent.py").read_text(
        encoding="utf-8"
    )
    assert "import requests" not in apt_source
    assert "import requests" not in ioc_source
    assert "os.environ" not in ioc_source
    assert "get_secret" in ioc_source


@pytest.mark.parametrize("runner_name", ["run_slither", "run_mythril"])
def test_contract_scanner_failure_cannot_become_pass(monkeypatch, runner_name):
    module = _load(
        ".claude/skills/analyzing-ethereum-smart-contract-vulnerabilities/scripts/agent.py",
        f"ethereum_skill_agent_{runner_name}",
    )
    failed = subprocess.CompletedProcess([runner_name], 1, stdout="", stderr="tool failed")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: failed)

    with pytest.raises(module.AnalysisToolError, match="tool failed"):
        getattr(module, runner_name)("contract.sol")


def test_kubernetes_parser_rejects_malformed_records(tmp_path):
    module = _load(
        ".claude/skills/analyzing-kubernetes-audit-logs/scripts/agent.py",
        "kubernetes_skill_agent",
    )
    audit_log = tmp_path / "audit.jsonl"
    audit_log.write_text('{"verb":"get"}\nnot-json\n', encoding="utf-8")

    with pytest.raises(module.AuditLogParseError, match="line 2"):
        module.parse_audit_log(audit_log)


def test_kubernetes_detectors_tolerate_empty_source_ip_lists():
    module = _load(
        ".claude/skills/analyzing-kubernetes-audit-logs/scripts/agent.py",
        "kubernetes_empty_source_skill_agent",
    )
    event = {
        "verb": "create",
        "objectRef": {"resource": "pods", "subresource": "exec"},
        "sourceIPs": [],
    }

    assert module.detect_pod_exec([event])[0]["source_ip"] == ""


def test_linux_audit_parser_fails_closed_for_missing_and_malformed_input(tmp_path):
    module = _load(
        ".claude/skills/analyzing-linux-audit-logs-for-intrusion/scripts/agent.py",
        "linux_audit_skill_agent",
    )
    with pytest.raises(FileNotFoundError):
        module.parse_audit_log(tmp_path / "missing.log")

    malformed = tmp_path / "audit.log"
    malformed.write_text("not an audit record\n", encoding="utf-8")
    with pytest.raises(module.AuditLogParseError, match="line 1"):
        module.parse_audit_log(malformed)

    valid = tmp_path / "large.log"
    valid.write_text(
        "type=SYSCALL msg=audit(1.0:1): uid=0\n"
        "type=SYSCALL msg=audit(2.0:2): uid=0\n",
        encoding="utf-8",
    )
    with pytest.raises(module.AuditLogParseError, match="exceeds max_lines"):
        module.parse_audit_log(valid, max_lines=1)


def test_health_snapshot_executes_smoke_gate(monkeypatch):
    module = _load(
        ".claude/skills/vector-diagnostics-and-tooling/scripts/health_snapshot.py",
        "health_snapshot_skill",
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="failed", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ok, detail = module.check_smoke_tests()

    assert not ok
    assert calls and calls[0][0] == module.sys.executable
    assert "failed" in detail


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
