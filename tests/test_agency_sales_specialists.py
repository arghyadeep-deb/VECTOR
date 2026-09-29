"""Focused tests for the self-development Agency sales specialists."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.city.agent_base import AgentBase
from core.city.declarative_manifest import ManifestLoader
from core.city.governor import DISTRICT_TASK_MAP
from core.config import CONFIG
from districts.agency.agency_specialists import (
    SPECIALIST_CLASSES,
    AccountStrategist,
    DealStrategist,
    OutboundSequenceStrategist,
    PipelineVelocityAnalyst,
    ProposalCoverageStrategist,
    SalesCoach,
    SalesDataExtractionAgent,
    SalesEngineer,
)


COMPLETE_EVIDENCE = {
    AccountStrategist: {
        "engagement_history": [{"date": "2026-09-20T00:00:00+00:00", "type": "meeting"}],
        "contract_value": 50000,
        "renewal_date": "2026-12-31T00:00:00+00:00",
        "expansion_signals": [{"direction": "positive", "signal": "new team asking for demo"}],
        "stakeholder_map": [{"name": "Asha", "role": "economic_buyer"}],
        "as_of": "2026-09-29T00:00:00+00:00",
    },
    DealStrategist: {
        "metrics": {"hours_saved": 40, "payback_months": 4},
        "economic_buyer": {"name": "Asha", "role": "VP Ops"},
        "decision_criteria": ["security", "integration"],
        "decision_process": ["technical review", "commercial approval"],
        "identified_pain": "Manual reporting is delaying executive decisions every week.",
        "champion": {"name": "Ravi", "validated": True},
        "competition": ["internal build"],
    },
    SalesEngineer: {
        "technical_requirements": ["sso", "audit logging", "slack integration"],
        "solution_design": {
            "addressed_capabilities": ["sso", "audit logging"],
            "integrations": ["slack integration"],
        },
    },
    OutboundSequenceStrategist: {
        "touches": [
            {"day": 0, "channel": "email"},
            {"day": 3, "channel": "linkedin"},
            {"day": 8, "channel": "email"},
        ]
    },
    PipelineVelocityAnalyst: {
        "stage_transitions": [
            {"deal_id": "d1", "from_stage": "qualified", "to_stage": "proposal", "days_in_stage": 5},
            {"deal_id": "d2", "from_stage": "qualified", "to_stage": "closed_lost", "days_in_stage": 9},
        ]
    },
    ProposalCoverageStrategist: {
        "required_capabilities": ["sso", "audit logging", "slack integration"],
        "addressed_capabilities": ["sso", "audit logging", "slack integration"],
    },
    SalesCoach: {
        "call_transcript": (
            "We discussed the budget of 50k and the timeline for Q2 rollout. "
            "The champion is the VP of Sales, and the main pain point is manual reporting."
        ),
        "rubric_items": ["budget", "timeline", "champion", "pain point"],
    },
    SalesDataExtractionAgent: {
        "records": [
            {"date": "2026-09-05", "amount": "1000", "rep": "Alice"},
            {"date": "2026-09-20", "amount": "2000", "rep": "Bob"},
        ],
        "as_of_date": "2026-09-25",
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_class", SPECIALIST_CLASSES)
async def test_brief_and_check_handle_complete_and_missing_evidence(agent_class):
    agent = agent_class()
    assert isinstance(agent, AgentBase)

    start_hp = agent.health_points
    missing_brief = await agent.run({"type": agent.profile.brief_action, "evidence": {}})
    assert missing_brief["report"]["status"] == "needs_human"
    assert agent.health_points == start_hp

    ready_brief = await agent.run(
        {"type": agent.profile.brief_action, "evidence": COMPLETE_EVIDENCE[agent_class]}
    )
    assert ready_brief["report"]["status"] == "ready"
    assert agent.health_points > start_hp

    hp_after_ready = agent.health_points
    missing_check = await agent.run({"type": agent.profile.check_action, "evidence": {}})
    assert missing_check["report"]["status"] == "needs_human"
    assert missing_check["report"]["missing_evidence"]
    assert agent.health_points == hp_after_ready

    passed_check = await agent.run(
        {"type": agent.profile.check_action, "evidence": COMPLETE_EVIDENCE[agent_class]}
    )
    assert passed_check["status"] == "ok"
    assert passed_check["report"]["status"] == "passed"
    assert passed_check["report"]["deterministic"] is True
    assert agent.health_points > hp_after_ready


def test_manifest_tiers_and_routes_are_exact():
    expected = {
        "account_strategist": AccountStrategist,
        "deal_strategist": DealStrategist,
        "sales_engineer": SalesEngineer,
        "outbound_sequence_strategist": OutboundSequenceStrategist,
        "pipeline_velocity_analyst": PipelineVelocityAnalyst,
        "proposal_coverage_strategist": ProposalCoverageStrategist,
        "sales_coach": SalesCoach,
        "sales_data_extraction_agent": SalesDataExtractionAgent,
    }
    definitions = ManifestLoader().load()
    agency = {entry["name"]: entry for entry in definitions if entry["district"] == "agency"}
    selected_definitions = [agency[name] for name in expected]
    instances = ManifestLoader().instantiate_all(selected_definitions)
    assert {type(instance) for instance in instances} == set(expected.values())

    for name, agent_class in expected.items():
        entry = agency[name]
        instance = agent_class()
        assert entry["class"].endswith(f".{agent_class.__name__}")
        assert entry["capabilities"] == instance.capabilities
        for action in instance.capabilities:
            assert DISTRICT_TASK_MAP[action] == "agency"
            assert action in CONFIG["permission"]["green"]
            assert action not in CONFIG["permission"]["yellow"]
            assert action not in CONFIG["permission"]["red"]


@pytest.mark.asyncio
async def test_account_strategist_catches_missing_decision_maker():
    evidence = dict(COMPLETE_EVIDENCE[AccountStrategist])
    evidence["stakeholder_map"] = [{"name": "Noor", "role": "user"}]
    result = await AccountStrategist().run({"type": "acct_health_check", "evidence": evidence})
    assert result["report"]["status"] == "needs_human"
    assert "decision_stakeholder_mapped" in {c["name"] for c in result["report"]["checks"] if not c["passed"]}


@pytest.mark.asyncio
async def test_deal_strategist_catches_weak_champion():
    evidence = dict(COMPLETE_EVIDENCE[DealStrategist])
    evidence["champion"] = {"name": "Ravi", "validated": False}
    result = await DealStrategist().run({"type": "deal_meddpicc_check", "evidence": evidence})
    assert result["report"]["status"] == "needs_human"
    assert result["report"]["weak_fields"] == ["champion"]


@pytest.mark.asyncio
async def test_sales_engineer_catches_missing_required_capability():
    evidence = dict(COMPLETE_EVIDENCE[SalesEngineer])
    evidence["solution_design"] = {"addressed_capabilities": ["sso"], "integrations": ["slack integration"]}
    result = await SalesEngineer().run({"type": "tech_fit_check", "evidence": evidence})
    assert result["report"]["status"] == "needs_human"
    assert result["report"]["missing_capabilities"] == ["audit logging"]


@pytest.mark.asyncio
async def test_outbound_sequence_catches_duplicate_day_and_channel_monoculture():
    evidence = {"touches": [{"day": 0, "channel": "email"}, {"day": 0, "channel": "email"}]}
    result = await OutboundSequenceStrategist().run({"type": "out_seq_check", "evidence": evidence})
    assert result["report"]["status"] == "needs_human"
    failed = {c["name"] for c in result["report"]["checks"] if not c["passed"]}
    assert {"no_duplicate_touch_day", "at_least_two_channels"} <= failed


@pytest.mark.asyncio
async def test_pipeline_velocity_catches_bad_transition_shape():
    evidence = {"stage_transitions": [{"deal_id": "d1", "from_stage": "qualified", "days_in_stage": -1}]}
    result = await PipelineVelocityAnalyst().run({"type": "pipe_velocity_check", "evidence": evidence})
    assert result["report"]["status"] == "needs_human"
    assert "transitions_have_required_shape" in {c["name"] for c in result["report"]["checks"] if not c["passed"]}


@pytest.mark.asyncio
async def test_proposal_coverage_catches_missing_required_capability():
    evidence = {
        "required_capabilities": ["sso", "audit logging", "slack integration"],
        "addressed_capabilities": ["sso", "slack integration"],
    }
    result = await ProposalCoverageStrategist().run({"type": "prop_coverage_check", "evidence": evidence})
    assert result["report"]["status"] == "needs_human"
    assert result["report"]["missing_capabilities"] == ["audit logging"]


def test_outbound_and_outreach_are_one_real_sequence_validator():
    agent = OutboundSequenceStrategist()
    assert agent.profile.deliverable.startswith("outbound/outreach")
    assert agent.capabilities == ["out_seq_brief", "out_seq_check"]


@pytest.mark.asyncio
async def test_sales_coach_catches_missing_rubric_items():
    evidence = {
        "call_transcript": "We just chatted about the weather and had lunch.",
        "rubric_items": ["budget", "timeline", "champion"],
    }
    result = await SalesCoach().run({"type": "sales_coaching_check", "evidence": evidence})
    assert result["report"]["status"] == "needs_human"
    assert result["report"]["missing_items"] == ["budget", "champion", "timeline"]
    assert result["report"]["coverage"] == 0.0


def test_sales_coach_serves_both_general_and_discovery_rubrics_as_one_agent():
    # sales-coach and sales-discovery-coach are the same underlying capability
    # (rubric-vs-transcript coverage) under two names; the caller's rubric
    # choice is what distinguishes a discovery-call review from general
    # coaching, not the agent. Same reasoning as OutboundSequenceStrategist.
    agent = SalesCoach()
    assert agent.capabilities == ["sales_coaching_brief", "sales_coaching_check"]
    assert "general coaching or discovery-call rubric" in agent.profile.deliverable


@pytest.mark.asyncio
async def test_sales_data_extraction_computes_real_mtd_ytd_and_flags_malformed_rows():
    evidence = {
        "records": [
            {"date": "2026-09-05", "amount": "1000", "rep": "Alice"},
            {"date": "2026-09-20", "amount": "2000", "rep": "Bob"},
            {"date": "2026-08-15", "amount": "500", "rep": "Alice"},
            {"date": "2025-01-01", "amount": "999", "rep": "Alice"},  # excluded: prior year
            {"date": "not-a-date", "amount": "100", "rep": "Bob"},  # malformed
            {"amount": "50"},  # malformed: no date
        ],
        "as_of_date": "2026-09-25",
    }
    result = await SalesDataExtractionAgent().run(
        {"type": "sales_data_extraction_check", "evidence": evidence}
    )
    report = result["report"]
    assert report["status"] == "needs_human"  # malformed rows present -> flagged for review
    assert report["mtd_total"] == 3000.0
    assert report["ytd_total"] == 3500.0
    assert report["by_rep_ytd"] == {"Alice": 1500.0, "Bob": 2000.0}
    assert report["malformed_row_count"] == 2
    assert report["valid_row_count"] == 4


@pytest.mark.asyncio
async def test_sales_data_extraction_passes_clean_when_all_rows_valid():
    result = await SalesDataExtractionAgent().run(
        {
            "type": "sales_data_extraction_check",
            "evidence": COMPLETE_EVIDENCE[SalesDataExtractionAgent],
        }
    )
    report = result["report"]
    assert report["status"] == "passed"
    assert report["malformed_row_count"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
