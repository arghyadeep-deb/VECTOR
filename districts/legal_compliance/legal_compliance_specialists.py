"""Evidence-checked legal_compliance specialist (SELF_DEV_P8_MEMORY_FINANCE_OPS).

``support-legal-compliance-checker`` (`.claude/agents/`, not found in this worktree; scope
inferred from persona name, same disclosed limitation as SELF_DEV_P5_MARKETING) is placed in the
new ``legal_compliance`` district rather than ``ops`` or ``finance``: SELF_DEV_AGENT_SPEC.md names
``legal_compliance/`` as a district "kept separate on purpose... because regulated advice needs
its own tier discipline", and this persona's job (checking regulated documents for required/
prohibited language) is exactly that discipline, not an operations or finance task.

``LegalComplianceChecker`` never renders a compliant/non-compliant verdict from a model (that
would be "ask the LLM if it's good and trust the answer" -- the exact pattern
SELF_DEV_AGENT_SPEC.md's guardrail #7 forbids for verification personas). Its one real check is a
literal, caller-supplied clause search: does the supplied document text contain every required
clause/phrase, and does it avoid every prohibited phrase. This is advisory-only, gated (GREEN,
read/recompute only) and gives no legal advice of its own -- it flags a real string-presence gap
for the owner's own human/legal review, per the spec's cross-district link note ("legal_compliance
<-> anyone touching regulated claims -- advisory-only, gated, never a direct executor").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


class LegalComplianceChecker(AgentBase):
    """Required/prohibited-clause presence brief + check over supplied document text."""

    profile = SpecialistProfile(
        "LegalComplianceChecker", "legal_compliance_checker_001",
        "legal_compliance_brief", "legal_compliance_check",
        ("document_text", "required_clauses"),
        "regulated-document clause-presence brief",
    )

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="legal_compliance",
            generation=generation,
        )
        self.capabilities = [self.profile.primary_action, self.profile.audit_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][legal_compliance_specialists] initialized {}", self.name)

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
            "advisory_only": True,
        }

    def run_checks(self, evidence: dict[str, Any] | None) -> dict[str, Any]:
        supplied = evidence if isinstance(evidence, dict) else {}
        text = supplied.get("document_text")
        required = supplied.get("required_clauses")
        if not isinstance(text, str) or not text.strip() or not isinstance(required, list) or not required:
            return {"verified": False, "verified_by": "none", "checks": [],
                    "note": "document_text (str) and required_clauses (non-empty list) both required"}

        lowered = text.lower()
        missing = [str(c) for c in required if str(c).lower() not in lowered]
        checks = [{"check": "required_clauses_present", "passed": not missing, "missing_clauses": missing,
                   "required_clauses": list(required)}]

        prohibited = supplied.get("prohibited_phrases")
        if isinstance(prohibited, list) and prohibited:
            found = [str(p) for p in prohibited if str(p).lower() in lowered]
            checks.append({"check": "no_prohibited_phrases", "passed": not found, "found_phrases": found})

        return {
            "verified": True,
            "verified_by": "deterministic_string_search",
            "passed": all(c["passed"] for c in checks),
            "checks": checks,
            "advisory_only": True,
            "note": "String-presence check only; does not constitute legal advice or a compliance certification.",
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
            logger.error("[VECTOR][legal_compliance_specialists] {} failed: {}", self.name, exc)
            self.deduct_points(30, "legal_compliance_specialist_task_failed")
            return {"status": "error", "error": str(exc)}


SPECIALIST_CLASSES: tuple[type[LegalComplianceChecker], ...] = (LegalComplianceChecker,)


if __name__ == "__main__":
    import asyncio
    import sys as _sys

    async def _smoke() -> None:
        _sys.stdout.reconfigure(encoding="utf-8")

        agent = LegalComplianceChecker()
        assert agent.health_points == 500
        assert agent.district == "legal_compliance"

        brief = await agent.run({"type": "legal_compliance_brief", "evidence": {}})
        assert brief["status"] == "ok" and brief["report"]["missing_evidence"]

        empty_check = await agent.run({"type": "legal_compliance_check", "evidence": {}})
        assert empty_check["verification"]["verified"] is False

        result = await agent.run({
            "type": "legal_compliance_check",
            "evidence": {
                "document_text": "This agreement includes a limitation of liability clause and a governing law clause.",
                "required_clauses": ["limitation of liability", "arbitration"],
                "prohibited_phrases": ["guaranteed returns"],
            },
        })
        v = result["verification"]
        assert v["checks"][0]["missing_clauses"] == ["arbitration"]
        assert v["passed"] is False

        logger.info("[VECTOR][legal_compliance_specialists] smoke check passed")
        print("legal_compliance_specialists.py OK")

    asyncio.run(_smoke())
