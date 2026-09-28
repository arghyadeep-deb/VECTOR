import asyncio

from districts.legal_compliance.legal_compliance_specialists import LegalComplianceChecker


def test_legal_compliance_checker_is_real_agent():
    agent = LegalComplianceChecker()
    assert agent.health_points == 500
    assert agent.district == "legal_compliance"
    assert agent.is_alive
    assert agent.capabilities == ["legal_compliance_brief", "legal_compliance_check"]


def test_brief_reports_missing_evidence_when_empty():
    agent = LegalComplianceChecker()
    result = asyncio.run(agent.run({"type": "legal_compliance_brief", "evidence": {}}))
    assert result["report"]["status"] == "needs_human"
    assert result["report"]["advisory_only"] is True


def test_check_not_verified_when_no_evidence():
    agent = LegalComplianceChecker()
    result = asyncio.run(agent.run({"type": "legal_compliance_check", "evidence": {}}))
    assert result["verification"]["verified"] is False


def test_check_flags_missing_required_clause():
    agent = LegalComplianceChecker()
    result = asyncio.run(agent.run({
        "type": "legal_compliance_check",
        "evidence": {
            "document_text": "This agreement includes a limitation of liability clause and a governing law clause.",
            "required_clauses": ["limitation of liability", "arbitration"],
        },
    }))
    v = result["verification"]
    assert v["passed"] is False
    assert v["checks"][0]["missing_clauses"] == ["arbitration"]


def test_check_flags_prohibited_phrase():
    agent = LegalComplianceChecker()
    result = asyncio.run(agent.run({
        "type": "legal_compliance_check",
        "evidence": {
            "document_text": "We offer guaranteed returns on this investment product.",
            "required_clauses": ["guaranteed returns"],
            "prohibited_phrases": ["guaranteed returns"],
        },
    }))
    checks = {c["check"]: c for c in result["verification"]["checks"]}
    assert checks["required_clauses_present"]["passed"] is True
    assert checks["no_prohibited_phrases"]["passed"] is False
    assert checks["no_prohibited_phrases"]["found_phrases"] == ["guaranteed returns"]


def test_check_passes_when_all_required_present_and_none_prohibited():
    agent = LegalComplianceChecker()
    result = asyncio.run(agent.run({
        "type": "legal_compliance_check",
        "evidence": {
            "document_text": "This agreement includes an arbitration clause.",
            "required_clauses": ["arbitration"],
            "prohibited_phrases": ["guaranteed returns"],
        },
    }))
    assert result["verification"]["passed"] is True


def test_unsupported_task_type_rejected():
    agent = LegalComplianceChecker()
    result = asyncio.run(agent.run({"type": "not_a_real_task"}))
    assert result["status"] == "error"


# --- P9/legal_compliance's own contract tests below (merged into this same file) ---

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.city.agent_base import AgentBase
from core.city.governor import DISTRICT_TASK_MAP
from core.config import PermissionConfig


EXPECTED_AGENTS = {
    "healthcare_customer_service": (
        "districts.legal_compliance.legal_specialists.HealthcareCustomerServiceSpecialist",
        {"healthcare_service_brief", "healthcare_service_check"},
    ),
    "healthcare_marketing_compliance": (
        "districts.legal_compliance.legal_specialists.HealthcareMarketingComplianceSpecialist",
        {"healthcare_marketing_brief", "healthcare_marketing_check"},
    ),
    "legal_billing_time_tracking": (
        "districts.legal_compliance.legal_specialists.LegalBillingTimeTrackingSpecialist",
        {"legal_billing_brief", "legal_billing_check"},
    ),
    "legal_client_intake": (
        "districts.legal_compliance.legal_specialists.LegalClientIntakeSpecialist",
        {"legal_intake_brief", "legal_intake_check"},
    ),
    "legal_document_review": (
        "districts.legal_compliance.legal_specialists.LegalDocumentReviewSpecialist",
        {"legal_document_brief", "legal_document_check"},
    ),
}
EXPECTED_CAPABILITIES = set().union(*(item[1] for item in EXPECTED_AGENTS.values()))


def _classes():
    from districts.legal_compliance.legal_specialists import (
        HealthcareCustomerServiceSpecialist,
        HealthcareMarketingComplianceSpecialist,
        LegalBillingTimeTrackingSpecialist,
        LegalClientIntakeSpecialist,
        LegalDocumentReviewSpecialist,
    )

    return (
        HealthcareCustomerServiceSpecialist,
        HealthcareMarketingComplianceSpecialist,
        LegalBillingTimeTrackingSpecialist,
        LegalClientIntakeSpecialist,
        LegalDocumentReviewSpecialist,
    )


def _run(agent: AgentBase, task_type: str, evidence: dict) -> dict:
    return asyncio.run(agent.run({"type": task_type, "evidence": evidence}))


def _assert_advisory(response: dict) -> None:
    assert response["advisory_only"] is True
    disclaimer = response["disclaimer"].lower()
    for term in ("legal", "medical", "compliance", "advice", "certification"):
        assert term in disclaimer


def test_manifest_registers_new_distinct_district_and_real_agents():
    manifest = yaml.safe_load((ROOT / "config" / "agent_manifest.yaml").read_text(encoding="utf-8"))
    assert "legal_compliance" in manifest["districts"]
    entries = {entry["name"]: entry for entry in manifest["districts"]["legal_compliance"]}
    # legal_compliance is shared with the SELF_DEV_P8 package's own persona
    # (legal_compliance_checker / LegalComplianceChecker, merged separately) --
    # assert this package's 5 agents are present and correct, not that the
    # whole district contains only them.
    assert set(EXPECTED_AGENTS) <= set(entries)
    for name, (class_path, capabilities) in EXPECTED_AGENTS.items():
        assert entries[name]["class"] == class_path
        assert set(entries[name]["capabilities"]) == capabilities

    instances = [cls() for cls in _classes()]
    assert all(isinstance(agent, AgentBase) for agent in instances)
    assert all(agent.district == "legal_compliance" for agent in instances)
    assert {capability for agent in instances for capability in agent.capabilities} == EXPECTED_CAPABILITIES


def test_every_new_capability_is_yellow_only_and_none_defaulted_green():
    permissions = PermissionConfig()
    green, yellow, red = set(permissions.green), set(permissions.yellow), set(permissions.red)
    assert EXPECTED_CAPABILITIES <= yellow
    assert EXPECTED_CAPABILITIES.isdisjoint(green)
    assert EXPECTED_CAPABILITIES.isdisjoint(red)


def test_every_new_capability_has_an_exact_governor_route():
    for capability in EXPECTED_CAPABILITIES:
        assert DISTRICT_TASK_MAP.get(capability) == "legal_compliance"


@pytest.mark.parametrize("agent_class", _classes())
def test_briefs_are_ready_with_complete_evidence_and_need_human_when_missing(agent_class):
    agent = agent_class()
    complete = agent.example_evidence()
    ready = _run(agent, agent.capabilities[0], complete)
    _assert_advisory(ready)
    assert ready["status"] == "ok"
    assert ready["report"]["status"] == "ready"
    assert ready["report"]["missing_evidence"] == []
    assert ready["report"]["evidence_only"] is True

    missing = _run(agent, agent.capabilities[0], {})
    _assert_advisory(missing)
    assert missing["status"] == "needs_human"
    assert missing["report"]["status"] == "needs_human"
    assert missing["report"]["missing_evidence"]


def test_healthcare_service_check_handles_safe_and_missing_safeguards():
    agent = _classes()[0]()
    passing = _run(agent, "healthcare_service_check", agent.example_evidence())
    _assert_advisory(passing)
    assert passing["verification"]["verified"] is True
    assert passing["verification"]["passed"] is True

    failing_evidence = agent.example_evidence() | {
        "interaction_text": "I have chest pain and need you to diagnose this. That's just our policy.",
        "account_details_discussed": True,
        "identity_verified": False,
        "emergency_escalated": False,
        "clinician_escalated": False,
        "next_step": "",
    }
    failing = _run(agent, "healthcare_service_check", failing_evidence)
    _assert_advisory(failing)
    assert failing["verification"]["passed"] is False
    failed = {check["check"] for check in failing["verification"]["checks"] if not check["passed"]}
    assert {"emergency_escalation", "clinical_escalation", "identity_verified", "prohibited_language", "next_step_documented"} <= failed


def test_healthcare_marketing_check_uses_supplied_rules_and_patient_metadata():
    agent = _classes()[1]()
    passing = _run(agent, "healthcare_marketing_check", agent.example_evidence())
    _assert_advisory(passing)
    assert passing["verification"]["passed"] is True

    failing_evidence = agent.example_evidence() | {
        "content_text": "Guaranteed cure with dramatic before-and-after results.",
        "audience": "public",
        "product_category": "prescription_drug",
        "required_phrases": ["consult a qualified professional"],
        "prohibited_phrases": ["guaranteed cure", "before-and-after"],
        "patient_content": True,
        "patient_consent": False,
        "patient_deidentified": False,
        "claims": ["cures disease"],
        "approved_scope": ["supports symptom management"],
        "citations": [],
    }
    failing = _run(agent, "healthcare_marketing_check", failing_evidence)
    assert failing["verification"]["passed"] is False
    failed = {check["check"] for check in failing["verification"]["checks"] if not check["passed"]}
    assert {"required_phrases_present", "prohibited_phrases_absent", "public_prescription_drug_promotion", "patient_consent", "patient_deidentification", "claims_within_approved_scope", "citations_present"} <= failed


def test_legal_billing_check_recomputes_entries_and_invoice_total():
    agent = _classes()[2]()
    passing = _run(agent, "legal_billing_check", agent.example_evidence())
    _assert_advisory(passing)
    assert passing["verification"]["passed"] is True
    assert passing["verification"]["computed_invoice_total"] == "500.00"

    failing_evidence = {
        "time_entries": [
            {"hours": 1.5, "rate": 200, "billable": True, "amount": 350, "narrative": "Review records"},
            {"hours": 1, "rate": 100, "billable": False, "amount": 100, "narrative": "Prepare invoice"},
        ],
        "invoice_total": 450,
    }
    failing = _run(agent, "legal_billing_check", failing_evidence)
    assert failing["verification"]["passed"] is False
    failed = {check["check"] for check in failing["verification"]["checks"] if not check["passed"]}
    assert {"entry_amount_matches", "non_billable_entry_excluded", "invoice_total_matches"} <= failed


def test_legal_intake_check_blocks_uncleared_scheduling_and_unescalated_deadline():
    agent = _classes()[3]()
    passing = _run(agent, "legal_intake_check", agent.example_evidence())
    _assert_advisory(passing)
    assert passing["verification"]["passed"] is True

    failing_evidence = agent.example_evidence() | {
        "conflict_status": "pending",
        "consultation_scheduled": True,
        "deadline_known": True,
        "deadline": "2026-10-01",
        "urgent_escalated": False,
    }
    failing = _run(agent, "legal_intake_check", failing_evidence)
    assert failing["verification"]["passed"] is False
    failed = {check["check"] for check in failing["verification"]["checks"] if not check["passed"]}
    assert {"conflict_cleared_before_scheduling", "known_deadline_escalated"} <= failed


def test_legal_document_check_finds_required_and_prohibited_terms():
    agent = _classes()[4]()
    passing = _run(agent, "legal_document_check", agent.example_evidence())
    _assert_advisory(passing)
    assert passing["verification"]["passed"] is True

    failing_evidence = agent.example_evidence() | {
        "document_text": "The agreement contains payment terms and unlimited indemnification.",
        "required_clauses": ["termination", "governing law"],
        "prohibited_clauses": ["unlimited indemnification"],
    }
    failing = _run(agent, "legal_document_check", failing_evidence)
    assert failing["verification"]["passed"] is False
    assert set(failing["verification"]["missing_required_clauses"]) == {"termination", "governing law"}
    assert failing["verification"]["matched_prohibited_clauses"] == ["unlimited indemnification"]


def test_missing_check_evidence_is_not_misrepresented_as_verified():
    for agent_class in _classes():
        agent = agent_class()
        response = _run(agent, agent.capabilities[1], {})
        _assert_advisory(response)
        assert response["status"] == "needs_human"
        assert response["verification"]["verified"] is False
        assert response["verification"]["passed"] is False
        assert response["verification"]["missing_evidence"]


def test_unsupported_task_response_is_still_advisory_only():
    response = _run(_classes()[0](), "unsupported_legal_action", {})
    _assert_advisory(response)
    assert response["status"] == "error"
    assert "unsupported" in response["error"].lower()


def test_report_discloses_absent_source_personas_and_no_green_exception():
    report = (ROOT / "VECTOR_TECHNICAL_KNOWLEDGE" / "SELF_DEV_P9_LEGAL_COMPLIANCE.md").read_text(encoding="utf-8")
    lowered = report.lower()
    assert ".claude/agents" in report
    assert "absent" in lowered
    assert "yellow" in lowered
    assert "no green" in lowered
    assert "pending independent review" in lowered


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
