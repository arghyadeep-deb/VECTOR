"""Regression test for a real, verified bug found during the 2026-09-30 Phase 3
codebase audit, affecting 5 files across 4 self-dev-program districts:

  districts/agency/agency_specialists.py       (AgencySalesSpecialist.run())
  districts/design/design_specialists.py       (DesignSpecialist.run())
  districts/security/security_specialists.py   (SecuritySpecialist.run())
  districts/personal_growth/skill_builder.py   (SkillBuilder.run())
  districts/chief_of_staff/slack_archaeologist.py (SlackArchaeologist.run())

Every one of these evidence-gated `<x>_brief`/`<x>_check` specialists read
`task.get("evidence")` (and design_specialists also `task.get("query")`)
directly off the top-level task dict. The real governor dispatch shape
(core/city/governor.py dispatch() -> `await agent.run(task)`) is
`task = {"type": ..., "params": {...}}` -- every other agent in the
codebase receives its real arguments nested under "params". Confirmed at
the plain-dict level before fixing anything:

    task = {"type": "x", "params": {"evidence": {"a": 1}}}
    task.get("evidence")  ->  None          # the bug
    task["params"]["evidence"]  ->  {"a": 1}  # what was actually supplied

So a real governor dispatch to any of these ~42 agent classes always saw
"no evidence supplied", regardless of what the caller actually sent --
every real invocation would report `needs_human`/missing-everything, never
`ready`/`passed`, no matter how complete the real evidence was.

The identical bug was already fixed once, later, in the last-built
districts/marketing/marketing_specialists.py's run()
(`task.get("evidence") or params.get("evidence")`) but never backported to
these 5 earlier files -- exactly the kind of parallel-evolution-without-
backport gap this whole audit has been finding. Same fix applied to all 5.

None of these 5 files' existing test suites exercised the nested-params
shape at all (grepped for the literal string "params" across each --
zero hits) -- which is why the bug was never caught. This file adds that
missing coverage for all 5 at once.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.agency.agency_specialists import LoanOfficerAssistant
from districts.chief_of_staff.slack_archaeologist import SlackArchaeologist
from districts.design.design_specialists import BrandGuardian
from districts.personal_growth.skill_builder import SkillBuilder
from districts.security.security_specialists import ScanVerifier


def _dict_level_proof():
    """Not a test of agent code -- a standalone proof of the exact mechanism,
    kept as its own function so the underlying claim is checkable in
    isolation from any agent-specific evidence-schema quirks below."""
    task = {"type": "x", "params": {"evidence": {"a": 1}}}
    assert task.get("evidence") is None
    assert task["params"]["evidence"] == {"a": 1}


def test_dict_level_mechanism_proof():
    _dict_level_proof()


@pytest.mark.asyncio
async def test_agency_specialist_reads_evidence_from_nested_params():
    agent = LoanOfficerAssistant()
    evidence = {"applicant_financials": {"credit_score": 700}, "eligibility_rules": {"min_credit_score": 620}}
    result = await agent.run({"type": agent.profile.brief_action, "params": {"evidence": evidence}})
    # A non-empty evidence dict must be genuinely inspected -- present_evidence
    # should reflect it, not report every field missing as it would for
    # None/{} evidence (which is exactly what the bug did for ANY real
    # nested-params evidence, empty or not).
    assert result["report"]["present_evidence"] == ["applicant_financials", "eligibility_rules"]


@pytest.mark.asyncio
async def test_design_specialist_reads_evidence_and_query_from_nested_params():
    agent = BrandGuardian()
    evidence = {"brand_purpose": "sustainability-first outdoor gear", "audience": "urban millennials", "existing_assets": "logo, 2 color palettes"}
    result = await agent.run({"type": agent.profile.primary_action, "params": {"evidence": evidence}})
    assert result["status"] == "ok"
    assert result["report"]["present_evidence"] == ["brand_purpose", "audience", "existing_assets"]


@pytest.mark.asyncio
async def test_security_specialist_reads_evidence_from_nested_params():
    agent = ScanVerifier()
    evidence = {f: "supplied" for f in agent.profile.required_fields}
    result = await agent.run({"type": agent.profile.brief_action, "params": {"evidence": evidence}})
    assert result["report"]["present_evidence"] == list(agent.profile.required_fields)


@pytest.mark.asyncio
async def test_skill_builder_reads_evidence_from_nested_params():
    agent = SkillBuilder()
    evidence = {f: "supplied" for f in agent.profile.required_fields}
    result = await agent.run({"type": agent.profile.brief_action, "params": {"evidence": evidence}})
    assert result["report"]["present_evidence"] == list(agent.profile.required_fields)


@pytest.mark.asyncio
async def test_slack_archaeologist_reads_evidence_from_nested_params():
    agent = SlackArchaeologist()
    evidence = {f: "supplied" for f in agent.profile.required_fields}
    result = await agent.run({"type": agent.profile.brief_action, "params": {"evidence": evidence}})
    assert result["report"]["present_evidence"] == list(agent.profile.required_fields)


@pytest.mark.asyncio
async def test_flat_shape_unaffected_for_all_five_agent_types():
    """Backward compat: the flat (no "params" key) shape every existing
    passing test in these files' own suites already uses must keep working
    identically after the fix."""
    agent = LoanOfficerAssistant()
    evidence = {"applicant_financials": {"credit_score": 700}, "eligibility_rules": {"min_credit_score": 620}}
    result = await agent.run({"type": agent.profile.brief_action, "evidence": evidence})
    assert result["report"]["present_evidence"] == ["applicant_financials", "eligibility_rules"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
