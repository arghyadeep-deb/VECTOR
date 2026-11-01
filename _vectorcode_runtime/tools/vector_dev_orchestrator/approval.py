"""Human-approval policy for the VECTOR development orchestrator."""

from __future__ import annotations

from dataclasses import dataclass

from models import ApprovalRequirement, DevTask, RiskLevel
from text_signals import normalize, phrase_triggers, split_sentences


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Result of deterministic approval-policy evaluation."""

    risk: RiskLevel
    requires_human: bool
    reasons: tuple[str, ...]


class ApprovalPolicy:
    """Fail-closed policy for high-impact development operations."""

    _RULES: tuple[tuple[str, tuple[str, ...], RiskLevel], ...] = (
        (
            "Architecture change",
            (
                "architecture",
                "architectural",
                "adr",
                "system design",
                "redesign",
                "rewrite from scratch",
                "replace the memory",
                "replace the provider",
            ),
            RiskLevel.HIGH,
        ),
        (
            "Security-sensitive change",
            (
                "security",
                "authentication",
                "authorization",
                "permission gateway",
                "encryption",
                "sandbox",
                "secret",
                "credential",
                "api key",
                "token",
            ),
            RiskLevel.CRITICAL,
        ),
        (
            "Dependency or package change",
            (
                "install dependency",
                "add dependency",
                "add a dependency",
                "remove dependency",
                "upgrade dependency",
                "requirements.txt",
                "pyproject.toml",
                "package.json",
                "package-lock.json",
            ),
            RiskLevel.HIGH,
        ),
        (
            "Database or schema migration",
            (
                "database migration",
                "schema migration",
                "alter table",
                "drop table",
                "migration",
            ),
            RiskLevel.CRITICAL,
        ),
        (
            "Destructive operation",
            (
                "delete files",
                "delete directory",
                "remove files",
                "wipe",
                "purge",
                "reset --hard",
                "clean -fd",
                "drop database",
                "rm -rf",
                "delete backups",
                "delete the backups",
                "delete owner data",
                "delete vector_memory",
                "erase user data",
            ),
            RiskLevel.CRITICAL,
        ),
        (
            "Irreversible external action",
            (
                "send an email",
                "send email",
                "send a message to",
                "post to twitter",
                "post to instagram",
                "post on twitter",
                "tweet",
                "transfer funds",
                "wire transfer",
                "place an order",
                "submit the order",
            ),
            RiskLevel.CRITICAL,
        ),
        (
            "Major product-scope decision",
            (
                "product scope",
                "change the scope of v1",
                "redefine v1",
                "decide which workflow",
                "choose which workflow",
                "product decision",
            ),
            RiskLevel.HIGH,
        ),
        (
            "Unresolved high-impact security tradeoff",
            (
                "security tradeoff",
                "security trade-off",
                "weaken security",
                "weaken the permission",
                "disable the permission gateway",
                "bypass the permission",
                "disable authentication",
                "skip authentication",
            ),
            RiskLevel.CRITICAL,
        ),
        (
            "Production or deployment action",
            (
                "production",
                "deploy",
                "release to prod",
                "publish",
            ),
            RiskLevel.CRITICAL,
        ),
        (
            "Financial or spending action",
            (
                "purchase",
                "payment",
                "spend money",
                "billing",
                "financial transaction",
            ),
            RiskLevel.CRITICAL,
        ),
        (
            "Protected Git operation",
            (
                "merge to main",
                "merge into main",
                "merge to master",
                "merge into master",
                "push to main",
                "push to master",
                "force push",
                "git push",
                "push to origin",
                "push to the remote",
                "push to github",
                "create a pull request",
                "open a pull request",
            ),
            RiskLevel.CRITICAL,
        ),
    )

    # Deterministic negation handling (issue 7): a phrase that appears only
    # inside a clear negated prohibition -- "Do not change ... security
    # code ..." -- must not by itself trigger human approval. Delegated to
    # text_signals.py (shared with router.py's task-category classifier)
    # so both apply the exact same narrow, explicitly-scoped heuristic
    # rather than maintaining divergent copies. Anything outside that
    # narrow shape fails closed (still flags), by design.

    def evaluate_description(
        self,
        description: str,
    ) -> ApprovalDecision:
        """Evaluate task text before autonomous execution."""

        normalized = normalize(description)
        sentences = split_sentences(normalized)

        reasons: list[str] = []
        highest_risk = RiskLevel.LOW

        for reason, phrases, risk in self._RULES:
            if phrase_triggers(sentences, phrases):
                reasons.append(reason)
                highest_risk = self._max_risk(
                    highest_risk,
                    risk,
                )

        return ApprovalDecision(
            risk=highest_risk,
            requires_human=bool(reasons),
            reasons=tuple(reasons),
        )

    def apply_to_task(
        self,
        task: DevTask,
    ) -> ApprovalDecision:
        """Attach approval requirements and risk to a task."""

        decision = self.evaluate_description(task.description)

        task.risk = decision.risk

        existing = {
            requirement.reason
            for requirement in task.approvals
        }

        for reason in decision.reasons:
            if reason not in existing:
                task.approvals.append(
                    ApprovalRequirement(
                        reason=reason,
                        approved=False,
                    )
                )

        return decision

    @staticmethod
    def all_requirements_approved(
        task: DevTask,
    ) -> bool:
        return all(
            requirement.approved
            for requirement in task.approvals
        )

    @staticmethod
    def approve_requirement(
        task: DevTask,
        reason: str,
    ) -> None:
        """Mark one exact approval requirement approved."""

        for requirement in task.approvals:
            if requirement.reason == reason:
                requirement.approved = True
                return

        raise KeyError(
            f"Approval requirement not found: {reason}"
        )

    @staticmethod
    def _max_risk(
        left: RiskLevel,
        right: RiskLevel,
    ) -> RiskLevel:
        ranking = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }

        if ranking[right] > ranking[left]:
            return right

        return left


def _self_test() -> None:
    policy = ApprovalPolicy()

    safe = policy.evaluate_description(
        "Fix deterministic parsing bug and add regression tests."
    )

    assert safe.risk is RiskLevel.LOW
    assert not safe.requires_human
    assert safe.reasons == ()

    security = policy.evaluate_description(
        "Change authentication security and deploy to production."
    )

    assert security.requires_human
    assert security.risk is RiskLevel.CRITICAL
    assert "Security-sensitive change" in security.reasons
    assert "Production or deployment action" in security.reasons

    # Issue 7 regression: a clear negated prohibition listing risky
    # keywords must not itself trigger approval.
    negated = policy.evaluate_description(
        "Do not change dependencies, architecture, permissions, "
        "security code, database schema, or production configuration."
    )

    assert not negated.requires_human
    assert negated.risk is RiskLevel.LOW
    assert negated.reasons == ()

    # A negation lead-in earlier in the sentence must not suppress a
    # genuinely risky request appearing in a later, un-negated sentence.
    negated_then_real = policy.evaluate_description(
        "Do not skip the review. Deploy to production now."
    )

    assert negated_then_real.requires_human
    assert "Production or deployment action" in negated_then_real.reasons

    # A coordinating "but" reset inside the same sentence must still
    # flag the risky action that follows it -- fail closed rather than
    # silently trusting the negation to cover the whole sentence.
    negated_then_reset = policy.evaluate_description(
        "Do not deploy to production, but please push to master now."
    )

    assert negated_then_reset.requires_human
    assert "Protected Git operation" in negated_then_reset.reasons
    assert "Production or deployment action" not in negated_then_reset.reasons

    # Owner-approval boundary for autonomous supervision: each category the
    # owner reserved must stop autonomy, while ordinary engineering wording
    # (and the standard prohibition boilerplate) must not.
    boundary_cases = {
        "Destructive operation": "Run rm -rf on the data directory and delete backups.",
        "Irreversible external action": "Send an email to every customer when tests pass.",
        "Major product-scope decision": "Decide which workflow defines V1 and change the scope of V1.",
        "Unresolved high-impact security tradeoff": "Disable authentication for the admin route to simplify testing.",
        "Protected Git operation": "Run git push to origin and open a pull request.",
        "Architecture change": "Rewrite from scratch the whole memory layer.",
        "Financial or spending action": "Purchase a larger cloud plan for the run.",
        "Security-sensitive change": "Rotate the API key stored for the provider.",
    }

    for expected_reason, text in boundary_cases.items():
        decision = policy.evaluate_description(text)
        assert decision.requires_human, text
        assert expected_reason in decision.reasons, (expected_reason, decision.reasons)

    ordinary_cases = (
        "Fix the off-by-one in the pagination helper and add a regression test.",
        "Add a test asserting the config defaults. Do not modify dependencies, "
        "architecture, permissions, security code, database schema or production "
        "configuration. Do not commit, stage, push or merge.",
        "Refactor the queue helper for readability and keep public names unchanged.",
        "Do not git push anything; only edit the helper and its test.",
    )

    for text in ordinary_cases:
        assert not policy.evaluate_description(text).requires_human, text

    # Genuine risky requests must still be caught even when phrased with
    # unrelated negation elsewhere in the same description.
    real_request_with_unrelated_negation = policy.evaluate_description(
        "Do not touch the README. Upgrade dependency versions across "
        "the project."
    )

    assert real_request_with_unrelated_negation.requires_human
    assert (
        "Dependency or package change"
        in real_request_with_unrelated_negation.reasons
    )

    task = DevTask(
        description="Add a dependency and perform a schema migration."
    )

    decision = policy.apply_to_task(task)

    assert decision.requires_human
    assert task.risk is RiskLevel.CRITICAL
    assert len(task.approvals) == 2
    assert not policy.all_requirements_approved(task)

    for requirement in tuple(task.approvals):
        policy.approve_requirement(
            task,
            requirement.reason,
        )

    assert policy.all_requirements_approved(task)

    try:
        policy.approve_requirement(
            task,
            "Nonexistent approval",
        )
    except KeyError:
        pass
    else:
        raise AssertionError(
            "Unknown approval requirements must fail closed"
        )


if __name__ == "__main__":
    _self_test()

