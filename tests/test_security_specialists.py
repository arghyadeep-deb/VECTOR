"""Focused tests for the self-development Security specialists."""
# ruff: noqa: E402

from __future__ import annotations

import ast
import difflib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.city.agent_base import AgentBase
from core.city.declarative_manifest import ManifestLoader
from core.city.governor import DISTRICT_TASK_MAP
from core.config import CONFIG
from districts.security.security_specialists import (
    SPECIALIST_CLASSES,
    AgenticIdentityTrustAnalyst,
    AutomationGovernanceAnalyst,
    PatchProposalGenerator,
    PatchProposalVerifier,
    ScanInventoryAnalyst,
    ScanLoaderAnalyst,
    ScanResearcher,
    ScanVerifier,
    SlackArchaeologist,
)


def _patch_evidence() -> dict:
    before = "enabled = False\n"
    after = "enabled = True\n"
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="a/core/example.py",
            tofile="b/core/example.py",
        )
    )
    return {
        "target_path": "core/example.py",
        "before": before,
        "after": after,
        "finding_id": "SEC-001",
        "rationale": "Use the approved safe default.",
        "unified_diff": diff,
    }


COMPLETE_EVIDENCE = {
    PatchProposalGenerator: {
        "target_path": "core/example.py",
        "before": "enabled = False\n",
        "after": "enabled = True\n",
        "finding_id": "SEC-001",
        "rationale": "Use the approved safe default.",
    },
    PatchProposalVerifier: {
        "proposal": _patch_evidence(),
        "verification_results": [
            {"name": "focused tests", "status": "passed", "evidence": "1 passed"}
        ],
    },
    ScanInventoryAnalyst: {
        "artifacts": [
            {"path": "districts/security/example.py", "content": "value = 1\n"},
            {"path": "config/example.yaml", "content": "enabled: true\n"},
        ]
    },
    ScanLoaderAnalyst: {
        "scan_payload": (
            '{"scan_id":"scan-1","findings":[{"severity":"high",'
            '"message":"unsafe default","path":"core/example.py",'
            '"line":1,"evidence":"enabled = False"}]}'
        )
    },
    ScanResearcher: {
        "sources": [
            {
                "advisory_id": "CVE-2099-0001",
                "title": "Primary advisory",
                "url": "https://vendor.example/advisory",
                "summary": "Affected versions use an unsafe default.",
            },
            {
                "advisory_id": "CVE-2099-0001",
                "title": "Registry advisory",
                "url": "https://registry.example/CVE-2099-0001",
                "summary": "The same affected range is independently listed.",
            },
        ]
    },
    ScanVerifier: {
        "inventory": [{"path": "core/example.py"}, {"path": "config/example.yaml"}],
        "scan": {
            "scan_id": "scan-1",
            "scanned_paths": ["core/example.py", "config/example.yaml"],
            "findings": [],
        },
    },
    AgenticIdentityTrustAnalyst: {
        "claimed_agent_id": "security-agent-1",
        "registry_agent_id": "security-agent-1",
        "requested_action": "scan_verification_check",
        "required_scope": "security.scan.verify",
        "granted_scopes": ["security.scan.verify"],
        "credential_expires_at": "2099-01-01T00:00:00+00:00",
        "signature_verification": {
            "valid": True,
            "verifier": "local-keyring",
            "evidence_id": "sig-check-1",
        },
        "audit_chain_valid": True,
    },
    AutomationGovernanceAnalyst: {
        "process_name": "security scan intake",
        "time_saved_hours_month": 12,
        "data_criticality": "low",
        "external_dependencies": 1,
        "idempotency": True,
        "retry_policy": True,
        "timeout_handling": True,
        "audit_logging": True,
        "fallback_owner": "security owner",
        "human_checkpoint": True,
    },
    SlackArchaeologist: {
        "channel_or_thread_ref": "C0123ABCDEF",
        "messages": [
            {"id": "m1", "author": "alice", "timestamp": "2026-09-29T10:00:00Z", "text": "incident started"},
            {"id": "m2", "author": "bob", "timestamp": "2026-09-29T09:59:00Z", "text": "earlier reply", "thread_id": "m1"},
        ],
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_class", SPECIALIST_CLASSES)
async def test_specialist_check_handles_complete_and_missing_evidence(agent_class):
    agent = agent_class()
    assert isinstance(agent, AgentBase)

    brief_missing = await agent.run({"type": agent.profile.brief_action, "evidence": {}})
    assert brief_missing["report"]["status"] == "needs_human"

    brief_complete = await agent.run(
        {
            "type": agent.profile.brief_action,
            "evidence": COMPLETE_EVIDENCE[agent_class],
        }
    )
    assert brief_complete["report"]["status"] == "ready"

    missing = await agent.run({"type": agent.profile.check_action, "evidence": {}})
    assert missing["status"] == "ok"
    assert missing["report"]["status"] == "needs_human"
    assert missing["report"]["missing_evidence"]

    complete = await agent.run(
        {
            "type": agent.profile.check_action,
            "evidence": COMPLETE_EVIDENCE[agent_class],
        }
    )
    assert complete["status"] == "ok"
    assert complete["report"]["status"] in {"ready", "passed"}
    assert complete["report"]["deterministic"] is True


def test_manifest_tiers_and_routes_are_exact():
    expected = {
        "patch_proposal_generator": PatchProposalGenerator,
        "patch_proposal_verifier": PatchProposalVerifier,
        "scan_inventory_analyst": ScanInventoryAnalyst,
        "scan_loader_analyst": ScanLoaderAnalyst,
        "scan_researcher": ScanResearcher,
        "scan_verifier": ScanVerifier,
        "agentic_identity_trust_analyst": AgenticIdentityTrustAnalyst,
        "automation_governance_analyst": AutomationGovernanceAnalyst,
        "slack_archaeologist": SlackArchaeologist,
    }
    definitions = ManifestLoader().load()
    security = {entry["name"]: entry for entry in definitions if entry["district"] == "security"}
    selected_definitions = [security[name] for name in expected]
    instances = ManifestLoader().instantiate_all(selected_definitions)
    assert {type(instance) for instance in instances} == set(expected.values())

    for name, agent_class in expected.items():
        entry = security[name]
        assert entry["class"].endswith(f".{agent_class.__name__}")
        instance = agent_class()
        assert entry["capabilities"] == instance.capabilities
        for action in instance.capabilities:
            assert DISTRICT_TASK_MAP[action] == "security"
            assert action in CONFIG["permission"]["green"]
            assert action not in CONFIG["permission"]["yellow"]
            assert action not in CONFIG["permission"]["red"]


@pytest.mark.asyncio
async def test_slack_archaeologist_catches_every_real_defect_and_orders_the_timeline():
    agent = SlackArchaeologist()
    messages = [
        {"id": "m1", "author": "alice", "timestamp": "2026-09-29T10:00:00Z", "text": "incident started"},
        {"id": "m2", "author": "bob", "timestamp": "2026-09-29T09:59:00Z", "text": "earlier reply", "thread_id": "m1"},
        {"id": "m3", "author": "", "timestamp": "2026-09-29T10:01:00Z", "text": "no author"},
        {"id": "m1", "author": "dup", "timestamp": "2026-09-29T10:02:00Z", "text": "dup id"},
        {"id": "m4", "author": "carol", "timestamp": "bad-ts", "text": "bad ts"},
        {"id": "m5", "author": "dave", "timestamp": "2026-09-29T10:03:00Z", "text": "dangling", "thread_id": "ghost"},
    ]
    result = await agent.run(
        {"type": "slack_archaeology_check", "evidence": {"channel_or_thread_ref": "C123", "messages": messages}}
    )
    report = result["report"]
    assert report["status"] == "needs_human"
    failed = {c["name"] for c in report["checks"] if not c["passed"]}
    assert failed == {
        "no_duplicate_message_ids",
        "every_message_has_author_and_timestamp",
        "every_timestamp_parses",
        "no_dangling_thread_references",
    }
    assert report["duplicate_ids"] == ["m1"]
    assert report["dangling_thread_references"] == ["m5"]

    clean = await agent.run(
        {
            "type": "slack_archaeology_check",
            "evidence": {
                "channel_or_thread_ref": "C123",
                "messages": [
                    {"id": "a", "author": "alice", "timestamp": "2026-09-29T10:00:00Z", "text": "second"},
                    {"id": "b", "author": "bob", "timestamp": "2026-09-29T09:59:00Z", "text": "first", "thread_id": "a"},
                ],
            },
        }
    )
    assert clean["report"]["status"] == "passed"
    assert [t["id"] for t in clean["report"]["timeline"]] == ["b", "a"]


@pytest.mark.asyncio
async def test_patch_roles_cannot_apply_or_execute_payloads(tmp_path):
    target = tmp_path / "vector_target.py"
    target.write_text("safe = True\n", encoding="utf-8")
    marker = tmp_path / "executed.txt"
    payload = f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')\n"

    generator = PatchProposalGenerator()
    generated = await generator.run(
        {
            "type": generator.profile.check_action,
            "evidence": {
                "target_path": str(target),
                "before": target.read_text(encoding="utf-8"),
                "after": payload,
                "finding_id": "SEC-PAYLOAD",
                "rationale": "Prove proposal text stays inert.",
            },
        }
    )
    proposal = generated["report"]["proposal"]

    verifier = PatchProposalVerifier()
    verified = await verifier.run(
        {
            "type": verifier.profile.check_action,
            "evidence": {
                "proposal": proposal,
                "verification_results": [
                    {
                        "name": "malicious command",
                        "status": "passed",
                        "evidence": payload,
                        "command": payload,
                    }
                ],
            },
        }
    )

    assert target.read_text(encoding="utf-8") == "safe = True\n"
    assert not marker.exists()
    assert proposal["applied"] is False
    assert proposal["executed"] is False
    assert proposal["requires_human_or_permission_gateway"] is True
    assert verified["report"]["applied"] is False
    assert verified["report"]["executed"] is False

    module_path = Path(__file__).parents[1] / "districts" / "security" / "security_specialists.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not ({"subprocess", "runpy"} & imported_roots)

    banned_calls = {"eval", "exec", "compile", "system", "popen", "write_text", "write_bytes"}
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    assert not (banned_calls & called)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
