"""ARM B — Software Factory (per validated market issue).

research specs → build → reviewer↔fix loop → security audit → **beta candidate**.
Reuses ``districts/coding/*`` (architect_bot, rapid_prototyper, code_reviewer,
bug_hunter, security_reviewer) and ``districts/startups/*`` — the conductor here
just sequences them and runs the review loop.

The output is explicitly framed as an **owner-security-reviewed beta candidate**,
never a "secure product." Beta signups (Task 5) are gated to the same owner
approval as release, because this collects real users' PII.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

from core.config import CONFIG


class SoftwareArm:
    """Issue→software pipeline with a bounded reviewer↔fix loop."""

    def __init__(self) -> None:
        self.max_iterations = int(CONFIG["growth"].get("review_loop_max_iterations", 5))

    # ── orchestration ────────────────────────────────────────────────
    async def run_once(self, issue: dict | None = None) -> dict:
        """Build a beta candidate for one validated issue. Never raises."""
        try:
            specs = self._specs(issue)
            code = self._build(specs)
            if not code.get("code"):
                # Build fell back (rapid_prototyper unavailable): there is nothing
                # to review, so do not run review/audit over an empty artifact.
                logger.error("[VECTOR][growth][armB] build produced no code -- aborting")
                return {"status": "error", "approved": False, "escalated": False,
                        "release_ready": False, "reason": "build_failed"}
            review = await self._review_fix_loop(code)
            security = await self._security_audit(review["code"])
            return {
                "status": "beta_candidate",          # never "secure product"
                "approved": review["approved"],
                "escalated": review.get("escalated", False),
                "iterations": review["iterations"],
                "security": security,
                "release_ready": review["approved"] and security.get("passed", False),
            }
        except Exception as exc:
            logger.error("[VECTOR][growth][armB] run_once failed: {}", exc)
            return {"status": "error", "release_ready": False}

    async def _review_fix_loop(self, code) -> dict:
        """Loop code_reviewer+bug_hunter ↔ fix until sign-off, capped. Exits only
        on reviewer-approve; on cap, escalates to the owner (never ships unreviewed)."""
        for i in range(1, self.max_iterations + 1):
            approved = self._review(code)
            if approved:
                logger.info("[VECTOR][growth][armB] review approved on iteration {}", i)
                return {"approved": True, "iterations": i, "code": code, "escalated": False}
            code = self._fix(code, review=approved)
        logger.warning("[VECTOR][growth][armB] review cap hit ({}) — escalating to owner",
                       self.max_iterations)
        await self._escalate_to_owner(self.max_iterations)
        return {"approved": False, "escalated": True, "iterations": self.max_iterations, "code": code}

    async def _escalate_to_owner(self, iterations: int) -> None:
        """Actually notify the owner on escalation (it used to only set a flag and
        log, so nobody was ever told the beta candidate failed review)."""
        try:
            from core.notify import pushover
            await pushover(
                f"VECTOR growth ARM B: beta candidate NOT approved after {iterations} "
                f"review iterations -- needs owner attention.", priority=1)
        except Exception as exc:
            logger.error("[VECTOR][growth][armB] owner escalation notify failed: {}", exc)

    # ── stages (reuse existing agents; mocked in tests) ──────────────
    def _specs(self, issue: dict | None) -> dict:
        try:
            from districts.startups.idea_validator import IdeaValidator  # reuse  # noqa: F401
        except Exception as exc:
            logger.warning("[VECTOR][growth][armB] idea_validator unavailable: {}", exc)
        # "validated" must come from an actual validation verdict on the issue, not
        # from the import having succeeded.
        issue = issue or {}
        return {"issue": issue, "validated": issue.get("validated") is True}

    def _build(self, specs: dict):
        try:
            from districts.coding.rapid_prototyper import RapidPrototyper  # reuse
            return {"specs": specs, "code": "<scaffold>"}
        except Exception as exc:
            logger.warning("[VECTOR][growth][armB] build fell back: {}", exc)
            return {"specs": specs, "code": ""}

    def _review(self, code) -> bool:
        """code_reviewer + bug_hunter sign-off. Real impl ANDs their verdicts."""
        try:
            from districts.coding.code_reviewer import CodeReviewer  # reuse
            from districts.coding.bug_hunter import BugHunter         # reuse
            # Conservative default until wired to real verdicts: not approved.
            return False
        except Exception as exc:
            logger.warning("[VECTOR][growth][armB] reviewers unavailable -- not approved: {}", exc)
            return False

    def _fix(self, code, review):
        """Apply reviewer feedback (minimal_change_engineer in the real path)."""
        try:
            from districts.coding.minimal_change_engineer import MinimalChangeEngineer  # reuse
            return code
        except Exception:
            return code

    async def _security_audit(self, code) -> dict:
        """Run the real SecurityReviewer and report its observed result.

        `reviewed` is only True when a scan actually executed (even in
        degraded static-only mode); `passed` reflects the reviewer's
        findings instead of a hardcoded value. A human security review is
        still required before release regardless of this result.
        """
        try:
            from districts.coding.security_reviewer import SecurityReviewer  # reuse
        except Exception as exc:
            logger.warning("[VECTOR][growth][armB] security_reviewer unavailable: {}", exc)
            return {"passed": False, "reviewed": False}

        code_text = code.get("code", "") if isinstance(code, dict) else str(code or "")
        try:
            result = await SecurityReviewer().review(code_text, filename="armb_beta_candidate")
        except Exception as exc:
            logger.error("[VECTOR][growth][armB] security review raised: {}", exc)
            return {"passed": False, "reviewed": False, "error": str(exc)}

        issue_count = result.get("issue_count")
        return {
            "passed": issue_count == 0,
            "reviewed": True,
            "issue_count": issue_count,
            "critical_count": result.get("critical_count"),
            "degraded": result.get("degraded", False),
        }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("software_arm OK")
