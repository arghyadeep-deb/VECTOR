import asyncio

import pytest

from districts.ops.ops_specialists import (
    CorporateTrainingDesigner,
    DataConsolidationAgent,
    HROnboardingSpecialist,
    JiraWorkflowSteward,
    ProjectShepherd,
    ReportDistributionAgent,
    SPECIALIST_CLASSES,
    SupportResponder,
)


@pytest.mark.parametrize("cls", SPECIALIST_CLASSES)
def test_specialist_is_real_agent(cls):
    agent = cls()
    assert agent.health_points == 500
    assert agent.district == "ops"
    assert agent.is_alive
    assert agent.capabilities == [agent.profile.primary_action, agent.profile.audit_action]


@pytest.mark.parametrize("cls", SPECIALIST_CLASSES)
def test_brief_reports_missing_evidence_when_empty(cls):
    agent = cls()
    result = asyncio.run(agent.run({"type": agent.profile.primary_action, "evidence": {}}))
    assert result["status"] == "ok"
    assert result["report"]["status"] == "needs_human"
    assert result["report"]["missing_evidence"] == list(agent.profile.evidence_fields)


@pytest.mark.parametrize("cls", SPECIALIST_CLASSES)
def test_check_not_verified_when_no_evidence(cls):
    agent = cls()
    result = asyncio.run(agent.run({"type": agent.profile.audit_action, "evidence": {}}))
    assert result["verification"]["verified"] is False


def test_unsupported_task_type_rejected():
    agent = HROnboardingSpecialist()
    result = asyncio.run(agent.run({"type": "not_a_real_task"}))
    assert result["status"] == "error"


def test_hr_onboarding_flags_incomplete_required_item():
    agent = HROnboardingSpecialist()
    result = asyncio.run(agent.run({
        "type": "hr_onboarding_check",
        "evidence": {
            "new_hire": "J. Doe",
            "checklist_items": [
                {"name": "laptop_provisioned", "done": True},
                {"name": "signed_nda", "done": False},
            ],
        },
    }))
    check = result["verification"]["checks"][0]
    assert check["passed"] is False
    assert check["incomplete_items"] == ["signed_nda"]


def test_jira_workflow_steward_flags_invalid_transition():
    agent = JiraWorkflowSteward()
    result = asyncio.run(agent.run({
        "type": "jira_workflow_check",
        "evidence": {
            "board_config": {"name": "ENG"},
            "allowed_transitions": {"todo": ["in_progress"], "in_progress": ["done"]},
            "transition_history": ["todo", "in_progress", "todo"],
        },
    }))
    check = result["verification"]["checks"][0]
    assert check["passed"] is False
    assert check["invalid_transitions"] == [{"from": "in_progress", "to": "todo", "step": 2}]


def test_project_shepherd_flags_overdue_incomplete_milestone():
    agent = ProjectShepherd()
    result = asyncio.run(agent.run({
        "type": "project_shepherd_check",
        "evidence": {
            "project_name": "Alpha",
            "as_of_date": "2026-09-29",
            "milestones": [
                {"name": "M1", "due_date": "2026-09-01", "complete": False},
                {"name": "M2", "due_date": "2026-10-01", "complete": False},
            ],
        },
    }))
    check = result["verification"]["checks"][0]
    assert check["passed"] is False
    assert [m["name"] for m in check["at_risk_milestones"]] == ["M1"]


def test_support_responder_flags_missing_section():
    agent = SupportResponder()
    result = asyncio.run(agent.run({
        "type": "support_response_check",
        "evidence": {
            "ticket_summary": "Login broken",
            "draft_reply": "Hi there, thanks for reaching out.",
            "required_sections": ["thanks for reaching out", "resolution", "next steps"],
        },
    }))
    check = result["verification"]["checks"][0]
    assert check["passed"] is False
    assert check["missing_sections"] == ["resolution", "next steps"]


def test_failed_check_earns_no_hp_but_passing_check_does():
    agent = HROnboardingSpecialist()
    hp = agent.health_points
    asyncio.run(agent.run({"type": "hr_onboarding_check", "evidence": {
        "new_hire": "J. Doe", "checklist_items": [{"name": "signed_nda", "done": False}],
    }}))
    assert agent.health_points == hp
    asyncio.run(agent.run({"type": "hr_onboarding_check", "evidence": {
        "new_hire": "J. Doe", "checklist_items": [{"name": "signed_nda", "done": True}],
    }}))
    assert agent.health_points > hp


def test_governor_has_exact_routes_for_p8_capabilities():
    from core.city.governor import DISTRICT_TASK_MAP
    from districts.legal_compliance.legal_compliance_specialists import SPECIALIST_CLASSES as LEGAL
    from districts.memory_curator.memory_curator_specialists import SPECIALIST_CLASSES as MEMORY

    for classes, district in ((SPECIALIST_CLASSES, "ops"), (LEGAL, "legal_compliance"), (MEMORY, "memory_curator")):
        for cls in classes:
            for cap in (cls.profile.primary_action, cls.profile.audit_action):
                assert DISTRICT_TASK_MAP.get(cap) == district, cap


def test_accounts_payable_not_duplicated_in_ops():
    import districts.ops.ops_specialists as mod
    assert not hasattr(mod, "AccountsPayableAgent")


def test_data_consolidation_agent_flags_field_conflict():
    agent = DataConsolidationAgent()
    result = asyncio.run(agent.run({
        "type": "data_consolidation_check",
        "evidence": {
            "key_field": "id",
            "record_sets": [
                [{"id": "1", "name": "Acme"}],
                [{"id": "1", "name": "Acme Corp"}],
            ],
        },
    }))
    check = result["verification"]["checks"][0]
    assert check["passed"] is False
    assert check["conflicts"][0]["key"] == "1"
    assert "name" in check["conflicts"][0]["conflicting_fields"]


def test_report_distribution_agent_flags_bad_recipient_and_format():
    agent = ReportDistributionAgent()
    result = asyncio.run(agent.run({
        "type": "report_distribution_validate",
        "evidence": {
            "recipients": ["not-an-email"],
            "report_meta": {"format": "docx"},
        },
    }))
    checks = {c["check"]: c["passed"] for c in result["verification"]["checks"]}
    assert checks["recipient_addresses_look_valid"] is False
    assert checks["report_format_allowed"] is False


def test_corporate_training_designer_flags_missing_assessment():
    agent = CorporateTrainingDesigner()
    result = asyncio.run(agent.run({
        "type": "training_outline_check",
        "evidence": {
            "audience": "new engineers",
            "learning_objectives": ["ship safely"],
            "modules": [
                {"name": "Intro", "assessment": True},
                {"name": "Advanced"},
            ],
        },
    }))
    checks = {c["check"]: c for c in result["verification"]["checks"]}
    assert checks["modules_have_assessment"]["passed"] is False
    assert checks["modules_have_assessment"]["missing"] == ["Advanced"]
