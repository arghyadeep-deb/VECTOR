"""Deterministic, evidence-gated specialists for the Security district.

The patch roles in this module are deliberately proposal-only. They construct
or parse in-memory text and cannot read, write, execute, apply, commit, or merge
the proposed change. A human or the existing PermissionGateway must perform any
real action after reviewing the returned evidence.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from core.city.agent_base import AgentBase


@dataclass(frozen=True)
class SecuritySpecialistProfile:
    """The bounded contract for one deterministic Security specialist."""

    name: str
    agent_id: str
    brief_action: str
    check_action: str
    required_fields: tuple[str, ...]
    deliverable: str


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _safe_relative_path(value: Any) -> bool:
    text = str(value or "").strip().replace("\\", "/")
    if not text or ":" in text.split("/", 1)[0]:
        return False
    path = PurePosixPath(text)
    return not path.is_absolute() and ".." not in path.parts


def _check(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


class SecuritySpecialist(AgentBase):
    """Base class for read-only, deterministic Security analysis."""

    profile: SecuritySpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict[str, Any] | None = None) -> None:
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="security",
            generation=generation,
        )
        self.capabilities = [self.profile.brief_action, self.profile.check_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][security_specialists] initialized {}", self.name)

    def _evidence_state(self, evidence: Any) -> tuple[dict[str, Any], list[str], list[str]]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [field for field in self.profile.required_fields if _has_value(supplied.get(field))]
        missing = [field for field in self.profile.required_fields if field not in present]
        return supplied, present, missing

    def build_brief(self, evidence: Any) -> dict[str, Any]:
        _, present, missing = self._evidence_state(evidence)
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.required_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "deterministic": True,
            "read_only": True,
        }

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.brief_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
            }

        try:
            evidence, _, missing = self._evidence_state(task.get("evidence"))
            if task_type == self.profile.brief_action or missing:
                report = self.build_brief(evidence)
            else:
                report = self.evaluate(evidence)
                report.setdefault("persona", self.name)
                report.setdefault("deliverable", self.profile.deliverable)
                report.setdefault("missing_evidence", [])
                report.setdefault("deterministic", True)
                report.setdefault("read_only", True)
            if report.get("status") in {"ready", "passed"}:
                self.award_points(10, f"{task_type}_completed")
            return {"status": "ok", "report": report}
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("[VECTOR][security_specialists] {} rejected evidence: {}", self.name, exc)
            return {
                "status": "ok",
                "report": {
                    **self.build_brief(task.get("evidence")),
                    "status": "needs_human",
                    "validation_error": str(exc),
                },
            }
        except Exception as exc:
            logger.error("[VECTOR][security_specialists] {} failed: {}", self.name, exc)
            self.deduct_points(30, "security_specialist_task_failed")
            return {"status": "error", "error": str(exc)}


class PatchProposalGenerator(SecuritySpecialist):
    """Create an inert unified-diff proposal from explicit before/after text."""

    profile = SecuritySpecialistProfile(
        "PatchProposalGenerator",
        "patch_proposal_generator_001",
        "patch_proposal_brief",
        "patch_proposal_check",
        ("target_path", "before", "after", "finding_id", "rationale"),
        "structured patch proposal",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        target = str(evidence["target_path"])
        before = str(evidence["before"])
        after = str(evidence["after"])
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{target}",
                tofile=f"b/{target}",
            )
        )
        checks = [
            _check("target_is_safe_relative_path", _safe_relative_path(target), target),
            _check("content_changes", before != after, "before and after differ"),
            _check("diff_has_hunk", "@@" in diff, "unified diff contains a hunk"),
        ]
        proposal = {
            "proposal_id": str(evidence["finding_id"]),
            "target_path": target,
            "before": before,
            "after": after,
            "change_description": str(evidence["rationale"]),
            "unified_diff": diff,
            "validation_steps": list(evidence.get("validation_steps", [])),
            "applied": False,
            "executed": False,
            "requires_human_or_permission_gateway": True,
        }
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "proposal": proposal,
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }


class PatchProposalVerifier(SecuritySpecialist):
    """Parse patch evidence and reported checks without applying or running it."""

    profile = SecuritySpecialistProfile(
        "PatchProposalVerifier",
        "patch_proposal_verifier_001",
        "patch_verification_brief",
        "patch_verification_check",
        ("proposal", "verification_results"),
        "structured patch verification report",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        proposal = evidence["proposal"]
        results = evidence["verification_results"]
        if not isinstance(proposal, dict) or not isinstance(results, list):
            raise ValueError("proposal must be a mapping and verification_results must be a list")

        target = str(proposal.get("target_path", ""))
        diff = str(proposal.get("unified_diff", ""))
        result_shape = all(
            isinstance(item, dict)
            and _has_value(item.get("name"))
            and _has_value(item.get("status"))
            and _has_value(item.get("evidence"))
            for item in results
        )
        all_reported_passed = bool(results) and result_shape and all(
            str(item["status"]).lower() == "passed" for item in results
        )
        checks = [
            _check("target_is_safe_relative_path", _safe_relative_path(target), target),
            _check("diff_has_old_header", f"--- a/{target}" in diff, "old file header"),
            _check("diff_has_new_header", f"+++ b/{target}" in diff, "new file header"),
            _check("diff_has_hunk", "@@" in diff, "unified diff hunk"),
            _check("reported_results_have_evidence", result_shape, len(results)),
            _check("all_reported_results_passed", all_reported_passed, len(results)),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "reported_verification_results": results,
            "verification_results_executed_here": False,
            "applied": False,
            "executed": False,
            "requires_human_or_permission_gateway": True,
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }


class ScanInventoryAnalyst(SecuritySpecialist):
    """Build a content-free inventory with deterministic caller-data hashes."""

    profile = SecuritySpecialistProfile(
        "ScanInventoryAnalyst",
        "scan_inventory_analyst_001",
        "scan_inventory_brief",
        "scan_inventory_check",
        ("artifacts",),
        "scan artifact inventory",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        artifacts = evidence["artifacts"]
        if not isinstance(artifacts, list):
            raise ValueError("artifacts must be a list")
        inventory: list[dict[str, Any]] = []
        paths: list[str] = []
        valid_shape = True
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not _has_value(artifact.get("path")) or "content" not in artifact:
                valid_shape = False
                continue
            path = str(artifact["path"])
            content = str(artifact["content"])
            paths.append(path)
            inventory.append(
                {
                    "path": path,
                    "bytes": len(content.encode("utf-8")),
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "content_included": False,
                }
            )
        checks = [
            _check("artifacts_have_path_and_content", valid_shape and bool(inventory), len(inventory)),
            _check("paths_are_safe_and_relative", all(_safe_relative_path(path) for path in paths), paths),
            _check("paths_are_unique", len(paths) == len(set(paths)), len(paths)),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "inventory": inventory,
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }


class ScanLoaderAnalyst(SecuritySpecialist):
    """Parse and normalize JSON scan evidence without loading executable code."""

    profile = SecuritySpecialistProfile(
        "ScanLoaderAnalyst",
        "scan_loader_analyst_001",
        "scan_load_brief",
        "scan_load_check",
        ("scan_payload",),
        "normalized scan evidence",
    )
    _SEVERITIES = {"info", "low", "medium", "high", "critical"}

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        raw = evidence["scan_payload"]
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, dict):
            raise ValueError("scan_payload must decode to a mapping")
        findings = payload.get("findings")
        if not isinstance(findings, list):
            raise ValueError("scan_payload.findings must be a list")
        normalized: list[dict[str, Any]] = []
        valid_findings = True
        for finding in findings:
            required = ("severity", "message", "path", "line", "evidence")
            if not isinstance(finding, dict) or any(not _has_value(finding.get(key)) for key in required):
                valid_findings = False
                continue
            severity = str(finding["severity"]).lower()
            if severity not in self._SEVERITIES:
                valid_findings = False
                continue
            normalized.append(
                {
                    "severity": severity,
                    "message": str(finding["message"]),
                    "path": str(finding["path"]),
                    "line": int(finding["line"]),
                    "evidence": str(finding["evidence"]),
                }
            )
        scan_id = str(payload.get("scan_id", ""))
        checks = [
            _check("scan_id_present", bool(scan_id), scan_id),
            _check("findings_have_required_evidence", valid_findings, len(normalized)),
            _check(
                "finding_paths_are_safe_and_relative",
                all(_safe_relative_path(item["path"]) for item in normalized),
                [item["path"] for item in normalized],
            ),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "normalized_scan": {"scan_id": scan_id, "findings": normalized},
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }


class ScanResearcher(SecuritySpecialist):
    """Check provenance and corroboration in supplied security research."""

    profile = SecuritySpecialistProfile(
        "ScanResearcher",
        "scan_researcher_001",
        "scan_research_brief",
        "scan_research_check",
        ("sources",),
        "security research provenance report",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        sources = evidence["sources"]
        if not isinstance(sources, list):
            raise ValueError("sources must be a list")
        required = ("advisory_id", "title", "url", "summary")
        complete = bool(sources) and all(
            isinstance(source, dict) and all(_has_value(source.get(key)) for key in required)
            for source in sources
        )
        advisory_ids = {str(source.get("advisory_id")) for source in sources if isinstance(source, dict)}
        domains = {
            urlparse(str(source.get("url", ""))).netloc.lower()
            for source in sources
            if isinstance(source, dict)
        }
        domains.discard("")
        checks = [
            _check("sources_have_provenance", complete, len(sources)),
            _check("advisory_id_is_consistent", len(advisory_ids) == 1, sorted(advisory_ids)),
            _check("independent_domains_corroborate", len(domains) >= 2, sorted(domains)),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "source_count": len(sources),
            "independent_domains": sorted(domains),
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }


class ScanVerifier(SecuritySpecialist):
    """Compare supplied scan coverage with a supplied inventory."""

    profile = SecuritySpecialistProfile(
        "ScanVerifier",
        "scan_verifier_001",
        "scan_verification_brief",
        "scan_verification_check",
        ("inventory", "scan"),
        "scan coverage verification report",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        inventory = evidence["inventory"]
        scan = evidence["scan"]
        if not isinstance(inventory, list) or not isinstance(scan, dict):
            raise ValueError("inventory must be a list and scan must be a mapping")
        expected = {
            str(item.get("path")) for item in inventory if isinstance(item, dict) and _has_value(item.get("path"))
        }
        scanned_raw = scan.get("scanned_paths", [])
        scanned = {str(path) for path in scanned_raw} if isinstance(scanned_raw, list) else set()
        findings = scan.get("findings", [])
        finding_shape = isinstance(findings, list) and all(isinstance(item, dict) for item in findings)
        missing_paths = sorted(expected - scanned)
        unexpected_paths = sorted(scanned - expected)
        coverage = 1.0 if not expected else (len(expected & scanned) / len(expected))
        checks = [
            _check("inventory_has_paths", bool(expected), sorted(expected)),
            _check("all_inventory_paths_scanned", not missing_paths, missing_paths),
            _check("no_unexpected_paths", not unexpected_paths, unexpected_paths),
            _check("findings_are_structured", finding_shape, len(findings) if isinstance(findings, list) else 0),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "coverage": round(coverage, 4),
            "missing_paths": missing_paths,
            "unexpected_paths": unexpected_paths,
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }


class AgenticIdentityTrustAnalyst(SecuritySpecialist):
    """Fail closed on identity, scope, freshness, signature, and audit evidence."""

    profile = SecuritySpecialistProfile(
        "AgenticIdentityTrustAnalyst",
        "agentic_identity_trust_analyst_001",
        "identity_trust_brief",
        "identity_trust_check",
        (
            "claimed_agent_id",
            "registry_agent_id",
            "requested_action",
            "required_scope",
            "granted_scopes",
            "credential_expires_at",
            "signature_verification",
            "audit_chain_valid",
        ),
        "agent identity and authorization evidence report",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        expiry = datetime.fromisoformat(str(evidence["credential_expires_at"]).replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        signature = evidence["signature_verification"]
        if not isinstance(signature, dict):
            raise ValueError("signature_verification must be a mapping")
        signature_evidence = (
            signature.get("valid") is True
            and _has_value(signature.get("verifier"))
            and _has_value(signature.get("evidence_id"))
        )
        scopes = evidence["granted_scopes"]
        if not isinstance(scopes, list):
            raise ValueError("granted_scopes must be a list")
        checks = [
            _check(
                "registry_identity_matches_claim",
                str(evidence["claimed_agent_id"]) == str(evidence["registry_agent_id"]),
                str(evidence["registry_agent_id"]),
            ),
            _check(
                "required_scope_is_granted",
                str(evidence["required_scope"]) in {str(scope) for scope in scopes},
                scopes,
            ),
            _check("credential_is_current", expiry > datetime.now(UTC), expiry.isoformat()),
            _check("independent_signature_evidence_present", signature_evidence, signature.get("evidence_id")),
            _check("audit_chain_is_valid", evidence["audit_chain_valid"] is True, evidence["audit_chain_valid"]),
        ]
        authorized = all(item["passed"] for item in checks)
        return {
            "status": "passed" if authorized else "needs_human",
            "authorized": authorized,
            "checks": checks,
            "cryptographic_verification_performed_here": False,
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }


class AutomationGovernanceAnalyst(SecuritySpecialist):
    """Produce a deterministic governance verdict from explicit controls."""

    profile = SecuritySpecialistProfile(
        "AutomationGovernanceAnalyst",
        "automation_governance_analyst_001",
        "automation_governance_brief",
        "automation_governance_check",
        (
            "process_name",
            "time_saved_hours_month",
            "data_criticality",
            "external_dependencies",
            "idempotency",
            "retry_policy",
            "timeout_handling",
            "audit_logging",
            "fallback_owner",
            "human_checkpoint",
        ),
        "automation governance verdict",
    )

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        hours = float(evidence["time_saved_hours_month"])
        dependencies = int(evidence["external_dependencies"])
        criticality = str(evidence["data_criticality"]).lower()
        if criticality not in {"low", "medium", "high", "critical"}:
            raise ValueError("data_criticality must be low, medium, high, or critical")
        controls = {
            "idempotency": evidence["idempotency"] is True,
            "retry_policy": evidence["retry_policy"] is True,
            "timeout_handling": evidence["timeout_handling"] is True,
            "audit_logging": evidence["audit_logging"] is True,
            "fallback_owner": _has_value(evidence["fallback_owner"]),
            "human_checkpoint": evidence["human_checkpoint"] is True,
        }
        control_score = sum(controls.values())
        if criticality == "critical" and not controls["human_checkpoint"]:
            verdict = "REJECT"
        elif control_score < 4:
            verdict = "DEFER"
        elif criticality in {"high", "critical"} or dependencies > 3:
            verdict = "PARTIAL AUTOMATION ONLY"
        elif hours < 2:
            verdict = "DEFER"
        elif control_score == len(controls):
            verdict = "APPROVE"
        else:
            verdict = "APPROVE AS PILOT"
        checks = [
            _check("time_savings_are_non_negative", hours >= 0, hours),
            _check("dependency_count_is_non_negative", dependencies >= 0, dependencies),
            _check("reliability_controls_present", control_score >= 4, controls),
            _check("fallback_owner_present", controls["fallback_owner"], evidence["fallback_owner"]),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "verdict": verdict,
            "checks": checks,
            "control_score": control_score,
            "controls": controls,
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }


SPECIALIST_CLASSES: tuple[type[SecuritySpecialist], ...] = (
    PatchProposalGenerator,
    PatchProposalVerifier,
    ScanInventoryAnalyst,
    ScanLoaderAnalyst,
    ScanResearcher,
    ScanVerifier,
    AgenticIdentityTrustAnalyst,
    AutomationGovernanceAnalyst,
)


if __name__ == "__main__":
    async def _smoke() -> None:
        for specialist_class in SPECIALIST_CLASSES:
            specialist = specialist_class()
            result = await specialist.run(
                {"type": specialist.profile.check_action, "evidence": {}}
            )
            assert result["status"] == "ok"
            assert result["report"]["status"] == "needs_human"
        logger.info("[VECTOR][security_specialists] smoke check passed")

    asyncio.run(_smoke())
