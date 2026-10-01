"""Phase 3 audit regressions for districts/legal_compliance (no false PASS)."""
import asyncio

from districts.legal_compliance.legal_compliance_specialists import LegalComplianceChecker
from districts.legal_compliance.legal_specialists import (
    HealthcareCustomerServiceSpecialist as CS,
    HealthcareMarketingComplianceSpecialist as MK,
    LegalBillingTimeTrackingSpecialist as BL,
    LegalClientIntakeSpecialist as IN,
    LegalDocumentReviewSpecialist as DR,
)


def _checks(result):
    return {c["check"]: c for c in result["checks"]}


# ---- LegalComplianceChecker ----------------------------------------------
def test_checker_blank_required_clause_not_vacuous_pass():
    r = LegalComplianceChecker().run_checks({"document_text": "anything", "required_clauses": [""]})
    assert r["verified"] is False and r.get("passed") is not True


def test_checker_malformed_prohibited_list_not_silently_skipped():
    r = LegalComplianceChecker().run_checks({
        "document_text": "we promise guaranteed returns", "required_clauses": ["promise"],
        "prohibited_phrases": "guaranteed returns"})
    assert r["verified"] is False and r.get("passed") is not True


def test_checker_phrase_split_by_newline_still_found():
    r = LegalComplianceChecker().run_checks({
        "document_text": "we offer guaranteed\nreturns today", "required_clauses": ["offer"],
        "prohibited_phrases": ["guaranteed returns"]})
    assert r["passed"] is False


def test_checker_unverified_check_status_needs_human():
    res = asyncio.run(LegalComplianceChecker().run({"type": "legal_compliance_check", "evidence": {}}))
    assert res["status"] == "needs_human"


# ---- legal_specialists ----------------------------------------------------
def test_customer_service_string_flag_does_not_skip_identity_check():
    ev = CS().example_evidence()
    ev.update(account_details_discussed="yes", identity_verified=False)
    r = CS().run_checks(ev)
    assert _checks(r)["identity_verified"]["passed"] is False and r["passed"] is False


def test_customer_service_prohibited_phrase_curly_apostrophe_and_newline():
    ev = CS().example_evidence()
    ev["interaction_text"] = "That’s not a\nbig deal."
    r = CS().run_checks(ev)
    assert _checks(r)["prohibited_language"]["passed"] is False


def test_marketing_string_patient_flag_does_not_skip_consent():
    ev = MK().example_evidence()
    ev.update(patient_content="true", patient_consent=False, patient_deidentified=False)
    r = MK().run_checks(ev)
    assert r["passed"] is False


def test_marketing_prohibited_phrase_split_by_newline_detected():
    ev = MK().example_evidence()
    ev["content_text"] += " This is a guaranteed\ncure."
    assert _checks(MK().run_checks(ev))["prohibited_phrases_absent"]["passed"] is False


def test_marketing_string_rule_lists_not_vacuous():
    # Start from valid example evidence and change ONE field to a bare string:
    # the old code treated it as "present" yet produced zero checks -> passed=True.
    for field in ("prohibited_phrases", "required_phrases", "claims", "approved_scope"):
        ev = MK().example_evidence()
        ev[field] = "some banned phrase"
        r = MK().run_checks(ev)
        assert _checks(r)["rule_lists_well_formed"]["passed"] is False, field
        assert r["passed"] is False, field


def test_billing_non_list_time_entries_not_a_pass():
    r = BL().run_checks({"time_entries": "lots of hours", "invoice_total": 0})
    assert r["passed"] is False


def test_intake_string_flags_do_not_skip_conflict_and_deadline():
    ev = IN().example_evidence()
    ev.update(consultation_scheduled="yes", conflict_status="pending",
              deadline_known="yes", urgent_escalated=False)
    r = IN().run_checks(ev)
    c = _checks(r)
    assert c["conflict_cleared_before_scheduling"]["passed"] is False
    assert c["known_deadline_recorded"]["passed"] is False
    assert r["passed"] is False


def test_document_review_blank_clause_lists_not_vacuous():
    for field, bad in (("required_clauses", "payment terms"), ("prohibited_clauses", "some banned clause"),
                       ("required_clauses", ["payment terms", " "]), ("prohibited_clauses", [""])):
        ev = DR().example_evidence()
        ev[field] = bad
        r = DR().run_checks(ev)
        assert _checks(r)["clause_lists_well_formed"]["passed"] is False, (field, bad)
        assert r["passed"] is False, (field, bad)


def test_document_review_prohibited_clause_with_double_space_detected():
    ev = DR().example_evidence()
    ev["prohibited_clauses"] = ["unlimited  indemnification"]
    ev["document_text"] += " It contains unlimited indemnification."
    r = DR().run_checks(ev)
    assert r["passed"] is False and r["matched_prohibited_clauses"]


def test_valid_examples_still_pass():
    for cls in (CS, MK, BL, IN, DR):
        a = cls()
        assert a.run_checks(a.example_evidence())["passed"] is True
