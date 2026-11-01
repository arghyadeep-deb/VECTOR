"""Deterministic, advisory-only legal and healthcare compliance specialists.

The agents in this module inspect caller-supplied evidence. They never render a
legal, medical, or compliance verdict, never execute a recommendation, and never
use an LLM as a verifier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase


ADVISORY_DISCLAIMER = (
    "This output is advisory only and does not constitute legal, medical, or "
    "compliance advice or certification. A qualified professional must review it."
)
_MONEY = Decimal("0.01")
_EMERGENCY_TERMS = (
    "chest pain",
    "difficulty breathing",
    "shortness of breath",
    "stroke",
    "severe bleeding",
    "loss of consciousness",
    "suicidal",
    "self-harm",
)
_CLINICAL_TERMS = (
    "diagnose",
    "diagnosis",
    "medication",
    "prescription",
    "test result",
    "symptom",
    "treatment",
)
_MINIMIZING_PHRASES = ("that's not a big deal", "that is not a big deal", "that's just our policy", "that is just our policy")


@dataclass(frozen=True)
class SpecialistProfile:
    """Bounded contract for one regulated-adjacent specialist."""

    agent_id: str
    name: str
    brief_action: str
    check_action: str
    evidence_fields: tuple[str, ...]
    deliverable: str


def _response(**payload: Any) -> dict[str, Any]:
    return {"advisory_only": True, "disclaimer": ADVISORY_DISCLAIMER, **payload}


def _is_present(evidence: dict[str, Any], field: str) -> bool:
    if field not in evidence or evidence[field] is None:
        return False
    value = evidence[field]
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _norm(value: Any) -> str:
    """Lower-case, curly-quote and whitespace-normalised text so a phrase split by a
    newline / double space / typographic apostrophe is still matched."""
    text = str(value).replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _flag(value: Any) -> bool:
    """Fail-safe boolean trigger: only a literal ``False`` means 'not applicable'.

    A malformed flag ("yes", "false", 1) must trigger the safeguard checks, not skip them.
    """
    return value is not False


def _strict_list(value: Any) -> tuple[list[str], bool]:
    """Return (items, well_formed). Non-list or blank/non-str entries are malformed."""
    if not isinstance(value, list):
        return [], False
    ok = all(isinstance(item, str) and item.strip() for item in value)
    return [item.strip() for item in value if isinstance(item, str) and item.strip()], ok


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


class LegalComplianceSpecialist(AgentBase):
    """Shared read-only dispatch and evidence reporting for this district."""

    profile: SpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict[str, Any] | None = None) -> None:
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="legal_compliance",
            generation=generation,
        )
        self.capabilities = [self.profile.brief_action, self.profile.check_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][legal_compliance] initialized {}", self.name)

    def build_evidence_report(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [field for field in self.profile.evidence_fields if _is_present(supplied, field)]
        missing = [field for field in self.profile.evidence_fields if field not in present]
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.evidence_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "evidence_only": True,
        }

    def run_checks(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        report = self.build_evidence_report(supplied)
        checks, details = self._check_evidence(supplied)
        verified = not report["missing_evidence"] and bool(checks)
        result: dict[str, Any] = {
            "verified": verified,
            "verified_by": "deterministic_recomputation" if verified else "none",
            "passed": verified and all(check["passed"] for check in checks),
            "checks": checks,
            "missing_evidence": report["missing_evidence"],
        }
        result.update(details)
        return result

    def _check_evidence(self, evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        raise NotImplementedError

    def example_evidence(self) -> dict[str, Any]:
        raise NotImplementedError

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.brief_action))
        if task_type not in self.capabilities:
            return _response(
                status="error",
                error=f"Unsupported task type '{task_type}' for {self.name}",
                supported_tasks=list(self.capabilities),
            )
        evidence = task.get("evidence")
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        if evidence is None:
            evidence = params.get("evidence")
        try:
            report = self.build_evidence_report(evidence)
            status = "ok" if report["status"] == "ready" else "needs_human"
            payload: dict[str, Any] = {"status": status, "report": report}
            if task_type == self.profile.check_action:
                verification = self.run_checks(evidence)
                payload["verification"] = verification
                status = "ok" if verification["verified"] else "needs_human"
                payload["status"] = status
            if status == "ok":
                self.award_points(20, f"{task_type}_completed")
            return _response(**payload)
        except Exception as exc:
            logger.error("[VECTOR][legal_compliance] {} failed: {}", self.name, exc)
            self.deduct_points(30, "legal_compliance_task_failed")
            return _response(status="error", error=str(exc))


class HealthcareCustomerServiceSpecialist(LegalComplianceSpecialist):
    profile = SpecialistProfile(
        agent_id="legal-healthcare-customer-service",
        name="HealthcareCustomerServiceSpecialist",
        brief_action="healthcare_service_brief",
        check_action="healthcare_service_check",
        evidence_fields=(
            "interaction_text",
            "inquiry_type",
            "identity_verified",
            "account_details_discussed",
            "emergency_escalated",
            "clinician_escalated",
            "escalation_target",
            "next_step",
        ),
        deliverable="Patient-support safeguard brief for qualified staff review",
    )

    def _check_evidence(self, evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        text = _norm(evidence.get("interaction_text", ""))
        emergency_terms = [term for term in _EMERGENCY_TERMS if term in text]
        clinical_terms = [term for term in _CLINICAL_TERMS if term in text]
        prohibited = [term for term in _MINIMIZING_PHRASES if term in text]
        account_discussed = _flag(evidence.get("account_details_discussed"))
        checks = [
            {"check": "emergency_escalation", "passed": not emergency_terms or evidence.get("emergency_escalated") is True, "matched_terms": emergency_terms},
            {"check": "clinical_escalation", "passed": not clinical_terms or evidence.get("clinician_escalated") is True, "matched_terms": clinical_terms},
            {"check": "identity_verified", "passed": not account_discussed or evidence.get("identity_verified") is True},
            {"check": "prohibited_language", "passed": not prohibited, "matched_phrases": prohibited},
            {"check": "next_step_documented", "passed": bool(str(evidence.get("next_step", "")).strip())},
        ]
        return checks, {"requires_qualified_staff_review": True}

    def example_evidence(self) -> dict[str, Any]:
        return {
            "interaction_text": "The patient requested an appointment change and received a scheduling handoff.",
            "inquiry_type": "appointment",
            "identity_verified": True,
            "account_details_discussed": False,
            "emergency_escalated": False,
            "clinician_escalated": False,
            "escalation_target": "scheduling team",
            "next_step": "Scheduling team will call by 17:00 tomorrow.",
        }


class HealthcareMarketingComplianceSpecialist(LegalComplianceSpecialist):
    profile = SpecialistProfile(
        agent_id="legal-healthcare-marketing-compliance",
        name="HealthcareMarketingComplianceSpecialist",
        brief_action="healthcare_marketing_brief",
        check_action="healthcare_marketing_check",
        evidence_fields=(
            "content_text",
            "audience",
            "product_category",
            "required_phrases",
            "prohibited_phrases",
            "claims",
            "approved_scope",
            "patient_content",
            "patient_consent",
            "patient_deidentified",
            "citations",
        ),
        deliverable="Marketing-content rule check for qualified local compliance review",
    )

    def _check_evidence(self, evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        text = _norm(evidence.get("content_text", ""))
        required, required_ok = _strict_list(evidence.get("required_phrases"))
        prohibited, prohibited_ok = _strict_list(evidence.get("prohibited_phrases"))
        claims, claims_ok = _strict_list(evidence.get("claims"))
        approved_items, approved_ok = _strict_list(evidence.get("approved_scope"))
        approved = {_norm(item) for item in approved_items}
        missing_required = [phrase for phrase in required if _norm(phrase) not in text]
        matched_prohibited = [phrase for phrase in prohibited if _norm(phrase) in text]
        outside_scope = [claim for claim in claims if _norm(claim) not in approved]
        patient_content = _flag(evidence.get("patient_content"))
        is_public_rx = (
            str(evidence.get("product_category", "")).casefold() == "prescription_drug"
            and str(evidence.get("audience", "")).casefold() == "public"
            and bool(text.strip())
        )
        checks = [
            {
                "check": "rule_lists_well_formed",
                "passed": required_ok and prohibited_ok and claims_ok and approved_ok,
            },
            {"check": "required_phrases_present", "passed": not missing_required, "missing": missing_required},
            {"check": "prohibited_phrases_absent", "passed": not matched_prohibited, "matched": matched_prohibited},
            {"check": "public_prescription_drug_promotion", "passed": not is_public_rx},
            {"check": "patient_consent", "passed": not patient_content or evidence.get("patient_consent") is True},
            {"check": "patient_deidentification", "passed": not patient_content or evidence.get("patient_deidentified") is True},
            {"check": "claims_within_approved_scope", "passed": not outside_scope, "outside_scope": outside_scope},
            {"check": "citations_present", "passed": bool(_text_list(evidence.get("citations")))},
        ]
        return checks, {"current_law_not_verified": True, "jurisdiction_specific_review_required": True}

    def example_evidence(self) -> dict[str, Any]:
        return {
            "content_text": "This educational material supports symptom management. Consult a qualified professional.",
            "audience": "professional",
            "product_category": "general_health_education",
            "required_phrases": ["consult a qualified professional"],
            "prohibited_phrases": ["guaranteed cure", "before-and-after"],
            "claims": ["supports symptom management"],
            "approved_scope": ["supports symptom management"],
            "patient_content": False,
            "patient_consent": False,
            "patient_deidentified": False,
            "citations": ["caller-supplied-study-identifier"],
        }


class LegalBillingTimeTrackingSpecialist(LegalComplianceSpecialist):
    profile = SpecialistProfile(
        agent_id="legal-billing-time-tracking",
        name="LegalBillingTimeTrackingSpecialist",
        brief_action="legal_billing_brief",
        check_action="legal_billing_check",
        evidence_fields=("time_entries", "invoice_total"),
        deliverable="Time-entry and invoice arithmetic check for responsible professional review",
    )

    def _check_evidence(self, evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = evidence.get("time_entries") if isinstance(evidence.get("time_entries"), list) else []
        checks: list[dict[str, Any]] = [
            {"check": "time_entries_is_list", "passed": isinstance(evidence.get("time_entries"), list)}
        ]
        subtotal = Decimal("0")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                checks.append({"check": "entry_is_mapping", "entry": index, "passed": False})
                continue
            hours, rate, amount = _decimal(row.get("hours")), _decimal(row.get("rate")), _decimal(row.get("amount"))
            numeric_valid = hours is not None and rate is not None and amount is not None and hours >= 0 and rate >= 0 and amount >= 0
            checks.append({"check": "entry_values_valid", "entry": index, "passed": numeric_valid})
            if not numeric_valid:
                continue
            expected = (hours * rate).quantize(_MONEY, rounding=ROUND_HALF_UP)
            billable = row.get("billable") is True
            if billable:
                subtotal += expected
                checks.append({
                    "check": "entry_amount_matches",
                    "entry": index,
                    "passed": abs(amount - expected) <= _MONEY,
                    "computed": str(expected),
                    "supplied": str(amount.quantize(_MONEY, rounding=ROUND_HALF_UP)),
                })
            else:
                checks.append({"check": "non_billable_entry_excluded", "entry": index, "passed": amount == 0, "supplied": str(amount)})
            checks.append({"check": "narrative_present", "entry": index, "passed": bool(str(row.get("narrative", "")).strip())})
        invoice_total = _decimal(evidence.get("invoice_total"))
        subtotal = subtotal.quantize(_MONEY, rounding=ROUND_HALF_UP)
        checks.append({
            "check": "invoice_total_matches",
            "passed": invoice_total is not None and abs(invoice_total - subtotal) <= _MONEY,
            "computed": str(subtotal),
            "supplied": None if invoice_total is None else str(invoice_total.quantize(_MONEY, rounding=ROUND_HALF_UP)),
        })
        return checks, {"computed_invoice_total": str(subtotal)}

    def example_evidence(self) -> dict[str, Any]:
        return {
            "time_entries": [
                {"hours": 2, "rate": 200, "billable": True, "amount": 400, "narrative": "Review supplied agreement"},
                {"hours": 1, "rate": 100, "billable": True, "amount": 100, "narrative": "Prepare factual chronology"},
            ],
            "invoice_total": 500,
        }


class LegalClientIntakeSpecialist(LegalComplianceSpecialist):
    profile = SpecialistProfile(
        agent_id="legal-client-intake",
        name="LegalClientIntakeSpecialist",
        brief_action="legal_intake_brief",
        check_action="legal_intake_check",
        evidence_fields=(
            "prospect_name",
            "contact",
            "matter_type",
            "opposing_parties",
            "key_facts",
            "conflict_status",
            "consultation_scheduled",
            "deadline_known",
            "urgent_escalated",
            "next_step",
        ),
        deliverable="Attorney-ready intake completeness and routing check",
    )

    def _check_evidence(self, evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        required_text = ("prospect_name", "contact", "matter_type", "key_facts", "next_step")
        missing_text = [field for field in required_text if not str(evidence.get(field, "")).strip()]
        opposing = _text_list(evidence.get("opposing_parties"))
        scheduled = _flag(evidence.get("consultation_scheduled"))
        cleared = str(evidence.get("conflict_status", "")).casefold() == "cleared"
        deadline_known = _flag(evidence.get("deadline_known"))
        deadline = str(evidence.get("deadline", "")).strip()
        checks = [
            {"check": "required_intake_fields", "passed": not missing_text, "missing": missing_text},
            {"check": "opposing_parties_supplied", "passed": bool(opposing)},
            {"check": "conflict_cleared_before_scheduling", "passed": not scheduled or cleared},
            {"check": "known_deadline_recorded", "passed": not deadline_known or bool(deadline)},
            {"check": "known_deadline_escalated", "passed": not deadline_known or evidence.get("urgent_escalated") is True},
        ]
        return checks, {"attorney_review_required": True}

    def example_evidence(self) -> dict[str, Any]:
        return {
            "prospect_name": "Prospect A",
            "contact": "caller-supplied contact channel",
            "matter_type": "contract dispute",
            "opposing_parties": ["Counterparty B"],
            "key_facts": "Caller supplied a short factual chronology.",
            "conflict_status": "cleared",
            "consultation_scheduled": True,
            "deadline_known": False,
            "urgent_escalated": False,
            "next_step": "Consultation scheduled for attorney review.",
        }


class LegalDocumentReviewSpecialist(LegalComplianceSpecialist):
    profile = SpecialistProfile(
        agent_id="legal-document-review",
        name="LegalDocumentReviewSpecialist",
        brief_action="legal_document_brief",
        check_action="legal_document_check",
        evidence_fields=(
            "document_text",
            "document_type",
            "parties",
            "represented_party",
            "jurisdiction",
            "required_clauses",
            "prohibited_clauses",
        ),
        deliverable="Clause-presence report flagged for licensed-attorney review",
    )

    def _check_evidence(self, evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        text = _norm(evidence.get("document_text", ""))
        required, required_ok = _strict_list(evidence.get("required_clauses"))
        prohibited, prohibited_ok = _strict_list(evidence.get("prohibited_clauses"))
        missing = [clause for clause in required if _norm(clause) not in text]
        matched = [clause for clause in prohibited if _norm(clause) in text]
        checks = [
            {"check": "clause_lists_well_formed", "passed": required_ok and prohibited_ok},
            {"check": "required_clauses_present", "passed": not missing, "missing": missing},
            {"check": "prohibited_clauses_absent", "passed": not matched, "matched": matched},
        ]
        return checks, {
            "missing_required_clauses": missing,
            "matched_prohibited_clauses": matched,
            "attorney_review_required": True,
        }

    def example_evidence(self) -> dict[str, Any]:
        return {
            "document_text": "This agreement includes payment terms, termination rights, confidentiality, and governing law.",
            "document_type": "services agreement",
            "parties": ["Party A", "Party B"],
            "represented_party": "Party A",
            "jurisdiction": "caller-supplied jurisdiction",
            "required_clauses": ["payment terms", "termination", "confidentiality", "governing law"],
            "prohibited_clauses": ["unlimited indemnification"],
        }


def _smoke_check() -> bool:
    agents = [cls() for cls in (
        HealthcareCustomerServiceSpecialist,
        HealthcareMarketingComplianceSpecialist,
        LegalBillingTimeTrackingSpecialist,
        LegalClientIntakeSpecialist,
        LegalDocumentReviewSpecialist,
    )]
    return all(
        agent.build_evidence_report(agent.example_evidence())["status"] == "ready"
        and agent.run_checks(agent.example_evidence())["verified"]
        for agent in agents
    )


if __name__ == "__main__":
    assert _smoke_check(), "legal_compliance specialist smoke check failed"
    logger.info("[VECTOR][legal_compliance] specialist smoke check passed")
