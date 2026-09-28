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
