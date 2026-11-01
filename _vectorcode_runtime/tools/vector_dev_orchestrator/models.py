"""Core task and state models for the VECTOR development orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class Provider(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStage(StrEnum):
    QUEUED = "queued"
    CLASSIFYING = "classifying"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    REVIEWING = "reviewing"
    FIXING = "fixing"
    CI_GATE = "ci_gate"
    VERIFYING = "verifying"
    WAITING_APPROVAL = "waiting_approval"
    # Implemented and tested; the independent cross-provider review has not
    # happened yet (the reviewer provider is in a quota EMERGENCY). Not PASS.
    WAITING_REVIEW = "waiting_review"
    COMPLETE = "complete"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PASS = "pass"
    BLOCKED = "blocked"
    NEEDS_HUMAN = "needs_human"
    FAILED = "failed"
    # Non-terminal and NOT a pass: waiting for an independent review that is
    # deferred until the reviewer provider's quota allows it (POLICY.md sec. 10).
    WAITING_REVIEW = "waiting_review"


class ReviewSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class Difficulty(StrEnum):
    """Task complexity/effort tier used to select a model family.

    Defined here (not in router.py) so DevTask can persist it without a
    models.py <-> router.py circular import; router.py imports and
    re-exports this exact enum, so `from router import Difficulty`
    continues to work unchanged everywhere it is already used.
    """

    SCOUT = "scout"
    ROUTINE = "routine"
    SERIOUS = "serious"
    HARD = "hard"
    CRITICAL = "critical"


class TaskCategory(StrEnum):
    """Task-role classification, orthogonal to Difficulty.

    Distinguishes what KIND of work a task is, independent of how hard
    it is. Two categories (SECURITY_SENSITIVE, ARCHITECTURE) carry a
    deterministic minimum-difficulty floor in router.py; the rest exist
    for observability/testing and future routing refinement without
    forcing every category to carry a floor today.
    """

    EXPLORATION = "exploration"
    DOCUMENTATION = "documentation"
    TRIVIAL_EDIT = "trivial_edit"
    IMPLEMENTATION = "implementation"
    DEBUGGING = "debugging"
    TEST_REPAIR = "test_repair"
    INTEGRATION = "integration"
    ARCHITECTURE = "architecture"
    SECURITY_SENSITIVE = "security_sensitive"


class QuotaBand(StrEnum):
    """Controller-provided remaining-quota band for one provider.

    UNKNOWN means the caller did not supply a quota reading; routing
    then behaves exactly as NORMAL (never silently restricts capability
    just because quota state is unavailable).
    """

    NORMAL = "normal"
    CONSERVE = "conserve"
    RESERVE = "reserve"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


class ProviderQuota(StrEnum):
    """Honest per-provider availability level.

    UNKNOWN is a first-class value: when no real telemetry exists the
    system says so instead of pretending NORMAL. Routing stays safe under
    UNKNOWN (no capability is reduced because of it).
    """

    UNKNOWN = "unknown"
    NORMAL = "normal"
    CONSTRAINED = "constrained"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True, slots=True)
class QuotaState:
    """Controller-supplied remaining-quota snapshot, per provider.

    Percentages are 0-100 or None (unknown). VECTOR never scrapes these
    from an external source automatically -- a caller (dev_driver.py,
    or a future controller) supplies them explicitly when known.
    """

    codex_remaining_percent: float | None = None
    claude_remaining_percent: float | None = None


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Optional structured scope for a task (a planner work package).

    Everything is optional: an ad-hoc task passes no spec and routing uses
    only what the description says. When a spec is present the controller
    can infer difficulty from scope, enforce allowed_paths after the
    implementer runs, and give the reviewer the acceptance criteria.
    """

    objective: str = ""
    allowed_paths: tuple[str, ...] = ()
    forbidden_scope: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    test_targets: tuple[str, ...] = ()
    review_only: bool = False
    acceptance_critical: bool = False
    program_id: str | None = None
    package_id: str | None = None

    @property
    def scope_known(self) -> bool:
        return bool(self.allowed_paths or self.test_targets)


@dataclass(slots=True)
class ModelChoice:
    provider: Provider
    model: str
    effort: str | None = None
    reason: str = ""


@dataclass(slots=True)
class TestResult:
    command: str
    exit_code: int
    passed: bool
    stdout: str = ""
    stderr: str = ""


@dataclass(slots=True)
class ReviewFinding:
    severity: ReviewSeverity
    summary: str
    file: str | None = None
    line: int | None = None
    resolved: bool = False


@dataclass(slots=True)
class ApprovalRequirement:
    reason: str
    approved: bool = False


@dataclass(slots=True)
class DevTask:
    description: str

    task_id: str = field(default_factory=lambda: uuid4().hex)

    status: TaskStatus = TaskStatus.PENDING
    stage: TaskStage = TaskStage.QUEUED
    risk: RiskLevel = RiskLevel.LOW

    owner: Provider | None = None
    reviewer: Provider | None = None

    implementer_model: ModelChoice | None = None
    reviewer_model: ModelChoice | None = None

    # Task-aware routing metadata (persisted for audit/observability and
    # so bounded escalation has something to bump).
    difficulty: Difficulty = Difficulty.ROUTINE
    task_category: TaskCategory = TaskCategory.IMPLEMENTATION
    quota_band_at_routing: QuotaBand = QuotaBand.UNKNOWN

    retry_count: int = 0
    max_retries: int = 2

    # Bounded escalation (section 6): at most `max_escalations` times,
    # the controller may bump `difficulty` one tier and re-route the
    # implementer model for a fix attempt when a review surfaces a
    # genuine BLOCKER-severity defect. Never triggered by malformed
    # output, tooling bugs, sandbox issues, HEAD movement, or approval
    # requirements -- those are handled by their own subsystems.
    escalation_count: int = 0
    max_escalations: int = 1

    # Difficulty provenance (automatic classification): the caller's
    # request, the controller's inference, and what routing actually used.
    requested_difficulty: str = ""
    inferred_difficulty: str = ""
    difficulty_reason: str = ""

    # Work-package specification (all optional; empty for ad-hoc tasks).
    objective: str = ""
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_scope: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    program_id: str | None = None
    package_id: str | None = None
    baseline_commit: str = ""
    # Provider invocations that actually happened (implementer, reviewer, fix);
    # incremented by the execution cycle right before each real call.
    provider_calls: int = 0
    # Set at routing when the independent reviewer's provider is in a quota
    # EMERGENCY: the cycle stops after passing tests with WAITING_REVIEW.
    review_deferred: bool = False
    # Why ownership deviated from the 50/50 scheduler (e.g. Claude-first while
    # Codex is in EMERGENCY). Empty when the scheduler's choice stood.
    ownership_note: str = ""

    changed_files: list[str] = field(default_factory=list)
    commands_executed: list[str] = field(default_factory=list)
    tests: list[TestResult] = field(default_factory=list)
    review_findings: list[ReviewFinding] = field(default_factory=list)
    reviewer_evidence: list[str] = field(default_factory=list)
    approvals: list[ApprovalRequirement] = field(default_factory=list)

    notes: list[str] = field(default_factory=list)

    def is_terminal(self) -> bool:
        return self.status in {
            TaskStatus.PASS,
            TaskStatus.BLOCKED,
            TaskStatus.NEEDS_HUMAN,
            TaskStatus.FAILED,
        }

    def requires_human(self) -> bool:
        return any(not approval.approved for approval in self.approvals)

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def can_escalate(self) -> bool:
        return self.escalation_count < self.max_escalations

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _self_test() -> None:
    task = DevTask(description="Verify VECTOR orchestrator task model")

    assert task.status is TaskStatus.PENDING
    assert task.stage is TaskStage.QUEUED
    assert task.can_retry()
    assert not task.is_terminal()
    assert not task.requires_human()

    task.approvals.append(
        ApprovalRequirement(reason="Architecture change")
    )
    assert task.requires_human()

    assert task.reviewer_evidence == []
    task.reviewer_evidence.append("Bounded reviewer evidence self-test.")
    assert task.reviewer_evidence == ["Bounded reviewer evidence self-test."]

    # Task-aware routing metadata defaults and bounded escalation.
    assert task.difficulty is Difficulty.ROUTINE
    assert task.task_category is TaskCategory.IMPLEMENTATION
    assert task.quota_band_at_routing is QuotaBand.UNKNOWN
    assert task.escalation_count == 0
    assert task.max_escalations == 1
    assert task.can_escalate()
    assert not TaskSpec().scope_known
    assert TaskSpec(allowed_paths=("a.py",)).scope_known
    assert task.requested_difficulty == "" and task.allowed_paths == []
    assert task.program_id is None and task.baseline_commit == ""
    assert ProviderQuota.UNKNOWN.value == "unknown"
    assert {q.value for q in ProviderQuota} == {
        "unknown", "normal", "constrained", "exhausted",
    }

    task.escalation_count = 1
    assert not task.can_escalate()

    quota = QuotaState(
        codex_remaining_percent=42.0,
        claude_remaining_percent=None,
    )
    assert quota.codex_remaining_percent == 42.0
    assert quota.claude_remaining_percent is None

    task.status = TaskStatus.PASS
    assert task.is_terminal()

    serialized = task.to_dict()
    assert serialized["description"] == "Verify VECTOR orchestrator task model"
    assert serialized["difficulty"] == Difficulty.ROUTINE
    assert serialized["task_category"] == TaskCategory.IMPLEMENTATION
    assert serialized["escalation_count"] == 1


if __name__ == "__main__":
    _self_test()
