"""Evidence-checked ops specialists (SELF_DEV_P8_MEMORY_FINANCE_OPS).

Selected personas from `.claude/agents/` (not found in this worktree; scope inferred from persona
name + the ops domain, same disclosed limitation as SELF_DEV_P5_MARKETING) that had no existing
real match anywhere in VECTOR and have an honest deterministic check:

* ``hr-onboarding`` -> ``HROnboardingSpecialist`` -- required-checklist-item completion.
* ``project-management-jira-workflow-steward`` -> ``JiraWorkflowSteward`` -- validates a supplied
  issue's transition history against a supplied allowed-transition graph.
* ``project-management-project-shepherd`` -> ``ProjectShepherd`` -- flags overdue/at-risk
  milestones from supplied due dates and completion state.
* ``support-support-responder`` -> ``SupportResponder`` -- required-section completeness of a
  drafted support reply.
* ``data-consolidation-agent`` -> ``DataConsolidationAgent`` -- merges 2+ supplied record sets by
  a caller-named key field, flagging field-level conflicts. Distinct from ConsolidationBot
  (districts/memory_curator/consolidation_bot.py), which compresses VECTOR's own episodic memory,
  not caller-supplied external datasets.
* ``report-distribution-agent`` -> ``ReportDistributionAgent`` -- recipient/report metadata
  validation only; never sends or distributes anything.
* ``corporate-training-designer`` -> ``CorporateTrainingDesigner`` -- curriculum structure check
  (modules non-empty, unique, each has an assessment).

Every ``<x>_check`` recomputes something from the supplied evidence; none asks a model whether the
work is good, and none calls an LLM at all (so RULE 1 does not apply to any agent in this file).
Personas disclosed as NOT built here (see SELF_DEV_P8_MEMORY_FINANCE_OPS.md for the reasoning):
project-management-experiment-tracker, project-management-studio-operations,
project-management-studio-producer, support-analytics-reporter,
support-executive-summary-generator, support-finance-tracker, support-infrastructure-maintainer,
support-legal-compliance-checker (built instead under the new ``legal_compliance`` district),
accounts-payable-agent (already covered by finance-bookkeeper-controller in ``finance``),
language-translator.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from loguru import logger

from core.city.agent_base import AgentBase


@dataclass(frozen=True)
class SpecialistProfile:
    name: str
    agent_id: str
    primary_action: str
    audit_action: str
    evidence_fields: tuple[str, ...]
    deliverable: str
    analyzer: str = ""


def _rows(evidence: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = evidence.get(key)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _check_onboarding_checklist(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    items = _rows(evidence, "checklist_items")
    if not items:
        return []
    required = [i for i in items if i.get("required", True)]
    incomplete = [str(i.get("name", "")) for i in required if not i.get("done")]
    return [{
        "check": "required_checklist_items_complete", "passed": not incomplete,
        "total_required": len(required), "incomplete_items": incomplete,
    }]


def _check_jira_transitions(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = evidence.get("allowed_transitions")
    history = evidence.get("transition_history")
    if not isinstance(allowed, dict) or not isinstance(history, list) or not history:
        return []
    invalid = []
    for i in range(1, len(history)):
        frm, to = str(history[i - 1]), str(history[i])
        if to not in allowed.get(frm, []):
            invalid.append({"from": frm, "to": to, "step": i})
    return [{
        "check": "transition_history_valid", "passed": not invalid,
        "invalid_transitions": invalid, "steps_checked": len(history) - 1,
    }]


def _check_milestones_at_risk(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    milestones = _rows(evidence, "milestones")
    if not milestones:
        return []
    today = evidence.get("as_of_date")
    try:
        today_d = datetime.date.fromisoformat(str(today)) if today else datetime.date.today()
    except ValueError:
        today_d = datetime.date.today()
    at_risk = []
    for m in milestones:
        if m.get("complete"):
            continue
        due = m.get("due_date")
        try:
            due_d = datetime.date.fromisoformat(str(due))
        except (TypeError, ValueError):
            continue
        if due_d < today_d:
            at_risk.append({"name": str(m.get("name", "")), "due_date": str(due), "days_overdue": (today_d - due_d).days})
    return [{
        "check": "no_overdue_incomplete_milestones", "passed": not at_risk,
        "at_risk_milestones": at_risk, "milestones_considered": len(milestones),
    }]


def _check_support_response(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    draft = evidence.get("draft_reply")
    required_sections = evidence.get("required_sections")
    if not isinstance(draft, str) or not draft.strip() or not isinstance(required_sections, list) or not required_sections:
        return []
    text = draft.lower()
    missing = [str(s) for s in required_sections if str(s).lower() not in text]
    return [{
        "check": "required_sections_present", "passed": not missing,
        "missing_sections": missing, "required_sections": list(required_sections),
    }]


def _check_data_consolidation(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    sources = evidence.get("record_sets")
    key_field = evidence.get("key_field")
    if not isinstance(sources, list) or len(sources) < 2 or not key_field:
        return []
    by_key: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        for row in _rows({"rows": source}, "rows") if isinstance(source, list) else []:
            k = str(row.get(key_field, "")).strip()
            if k:
                by_key.setdefault(k, []).append(row)
    conflicts = []
    merged = 0
    for k, rows in by_key.items():
        if len(rows) < 2:
            continue
        merged += 1
        field_conflicts = {}
        all_fields = {f for r in rows for f in r if f != key_field}
        for f in all_fields:
            values = {str(r.get(f)) for r in rows if f in r}
            if len(values) > 1:
                field_conflicts[f] = sorted(values)
        if field_conflicts:
            conflicts.append({"key": k, "conflicting_fields": field_conflicts})
    return [{
        "check": "consolidated_records_no_conflicts", "passed": not conflicts,
        "keys_merged": merged, "conflicts": conflicts,
    }]


def _check_report_distribution(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    recipients = evidence.get("recipients")
    report_meta = evidence.get("report_meta")
    allowed_formats = evidence.get("allowed_formats") or ["pdf", "csv", "html"]
    if not isinstance(recipients, list) or not recipients or not isinstance(report_meta, dict):
        return []
    invalid_emails = [str(r) for r in recipients if "@" not in str(r) or "." not in str(r).split("@")[-1]]
    fmt = str(report_meta.get("format", "")).lower()
    return [
        {"check": "recipient_addresses_look_valid", "passed": not invalid_emails, "invalid": invalid_emails},
        {"check": "report_format_allowed", "passed": fmt in allowed_formats, "format": fmt, "allowed_formats": allowed_formats},
    ]


def _check_training_outline(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    modules = evidence.get("modules")
    if not isinstance(modules, list) or not modules:
        return []
    names = [str(m.get("name", "")).strip() if isinstance(m, dict) else str(m).strip() for m in modules]
    non_empty = all(names)
    unique = len(set(names)) == len(names)
    without_assessment = [
        n for m, n in zip(modules, names)
        if isinstance(m, dict) and not m.get("assessment")
    ]
    return [
        {"check": "modules_non_empty", "passed": non_empty, "count": len(modules)},
        {"check": "modules_unique", "passed": unique, "duplicates": len(modules) - len(set(names))},
        {"check": "modules_have_assessment", "passed": not without_assessment, "missing": without_assessment},
    ]


ANALYZERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "onboarding_checklist": _check_onboarding_checklist,
    "jira_transitions": _check_jira_transitions,
    "milestones_at_risk": _check_milestones_at_risk,
    "support_response": _check_support_response,
    "data_consolidation": _check_data_consolidation,
    "report_distribution": _check_report_distribution,
    "training_outline": _check_training_outline,
}


class OpsSpecialist(AgentBase):
    """Base class: evidence-completeness brief + deterministic recomputation check.

    No agent in this file calls an LLM, so RULE 1 session hydration does not
    apply here (unlike districts/marketing/marketing_specialists.py, which
    offers an optional free-text suggestion path this file deliberately
    omits to keep every action here pure, no-network, no-model recompute).
    """

    profile: SpecialistProfile

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="ops",
            generation=generation,
        )
        self.capabilities = [self.profile.primary_action, self.profile.audit_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][ops_specialists] initialized {}", self.name)

    def build_evidence_report(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [f for f in self.profile.evidence_fields if supplied.get(f)]
        missing = [f for f in self.profile.evidence_fields if not supplied.get(f)]
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
        checks = ANALYZERS[self.profile.analyzer](supplied) if self.profile.analyzer else []
        return {
            "verified": bool(checks),
            "verified_by": "deterministic_recomputation" if checks else "none",
            "passed": all(c["passed"] for c in checks) if checks else None,
            "checks": checks,
            "note": "" if checks else "No checkable evidence supplied for this persona's check.",
        }

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.primary_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
            }
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        evidence = task.get("evidence") or params.get("evidence")
        try:
            report = self.build_evidence_report(evidence)
            response: dict[str, Any] = {"status": "ok", "report": report}
            if task_type == self.profile.audit_action:
                response["verification"] = self.run_checks(evidence)
            verification = response.get("verification")
            if verification is None:
                earned = report["status"] == "ready"
            else:
                # A failed check is not completed work: HP only for a verified, non-failing check.
                earned = bool(verification.get("verified")) and verification.get("passed") is not False
            if earned:
                self.award_points(20, f"{task_type}_completed")
            return response
        except Exception as exc:
            logger.error("[VECTOR][ops_specialists] {} failed: {}", self.name, exc)
            self.deduct_points(30, "ops_specialist_task_failed")
            return {"status": "error", "error": str(exc)}


def _p(name: str, slug: str, primary: str, audit: str, evidence: tuple[str, ...], deliverable: str, analyzer: str) -> SpecialistProfile:
    return SpecialistProfile(name, f"{slug}_001", primary, audit, evidence, deliverable, analyzer)


class HROnboardingSpecialist(OpsSpecialist):
    profile = _p("HROnboardingSpecialist", "hr_onboarding_specialist", "hr_onboarding_brief", "hr_onboarding_check",
                 ("new_hire", "checklist_items"), "HR onboarding checklist brief", "onboarding_checklist")


class JiraWorkflowSteward(OpsSpecialist):
    profile = _p("JiraWorkflowSteward", "jira_workflow_steward", "jira_workflow_brief", "jira_workflow_check",
                 ("board_config", "allowed_transitions"), "Jira workflow-steward brief", "jira_transitions")


class ProjectShepherd(OpsSpecialist):
    profile = _p("ProjectShepherd", "project_shepherd", "project_shepherd_brief", "project_shepherd_check",
                 ("project_name", "milestones"), "project-shepherd risk brief", "milestones_at_risk")


class SupportResponder(OpsSpecialist):
    profile = _p("SupportResponder", "support_responder", "support_response_brief", "support_response_check",
                 ("ticket_summary", "draft_reply", "required_sections"), "support-response completeness brief",
                 "support_response")


class DataConsolidationAgent(OpsSpecialist):
    profile = _p("DataConsolidationAgent", "data_consolidation_agent", "data_consolidation_brief", "data_consolidation_check",
                 ("record_sets", "key_field"), "data-consolidation merge brief", "data_consolidation")


class ReportDistributionAgent(OpsSpecialist):
    profile = _p("ReportDistributionAgent", "report_distribution_agent", "report_distribution_brief", "report_distribution_validate",
                 ("recipients", "report_meta"), "report-distribution validation brief (never sends anything)",
                 "report_distribution")


class CorporateTrainingDesigner(OpsSpecialist):
    profile = _p("CorporateTrainingDesigner", "corporate_training_designer", "training_design_brief", "training_outline_check",
                 ("audience", "learning_objectives", "modules"), "corporate-training curriculum brief", "training_outline")


SPECIALIST_CLASSES: tuple[type[OpsSpecialist], ...] = (
    HROnboardingSpecialist, JiraWorkflowSteward, ProjectShepherd, SupportResponder,
    DataConsolidationAgent, ReportDistributionAgent, CorporateTrainingDesigner,
)


if __name__ == "__main__":
    import asyncio
    import sys as _sys

    async def _smoke() -> None:
        _sys.stdout.reconfigure(encoding="utf-8")

        for cls in SPECIALIST_CLASSES:
            agent = cls()
            assert agent.health_points == 500
            assert agent.district == "ops"
            brief = await agent.run({"type": agent.profile.primary_action, "evidence": {}})
            assert brief["status"] == "ok" and brief["report"]["missing_evidence"]
            check = await agent.run({"type": agent.profile.audit_action, "evidence": {}})
            assert check["verification"]["verified"] is False

        hr = HROnboardingSpecialist()
        r = await hr.run({"type": "hr_onboarding_check", "evidence": {
            "new_hire": "J. Doe",
            "checklist_items": [
                {"name": "laptop_provisioned", "done": True},
                {"name": "signed_nda", "done": False},
            ],
        }})
        assert r["verification"]["checks"][0]["incomplete_items"] == ["signed_nda"]

        hp_before = hr.health_points
        await hr.run({"type": "hr_onboarding_check", "evidence": {
            "new_hire": "J. Doe",
            "checklist_items": [{"name": "signed_nda", "done": False}],
        }})
        assert hr.health_points == hp_before  # failed check earns nothing

        ps = ProjectShepherd()
        r = await ps.run({"type": "project_shepherd_check", "evidence": {
            "project_name": "Alpha",
            "as_of_date": "2026-09-29",
            "milestones": [{"name": "M1", "due_date": "2026-09-01", "complete": False}],
        }})
        assert r["verification"]["checks"][0]["at_risk_milestones"][0]["name"] == "M1"

        logger.info("[VECTOR][ops_specialists] smoke check passed")
        print("ops_specialists.py OK")

    asyncio.run(_smoke())
