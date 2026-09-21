"""Core controller for the VECTOR development orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

from approval import ApprovalPolicy
from difficulty_inference import infer_difficulty
from models import (
    DevTask,
    Provider,
    ProviderQuota,
    QuotaBand,
    QuotaState,
    TaskCategory,
    TaskSpec,
    TaskStage,
    TaskStatus,
)
from router import Difficulty, ModelRouter
from state_store import StateStore


class DevOrchestrator:
    """Coordinate task ownership, routing, approvals and persistent state."""

    def __init__(
        self,
        repo_root: Path,
        state_root: Path | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()

        if state_root is None:
            state_root = (
                self.repo_root
                / "tools"
                / "vector_dev_orchestrator"
                / ".state"
            )

        self.state_root = Path(state_root).resolve()
        self.state_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.scheduler_state_path = (
            self.state_root
            / "scheduler.json"
        )

        self.state = StateStore(self.state_root)
        self.router = ModelRouter()
        self.approval_policy = ApprovalPolicy()

    def _load_last_owner(self) -> Provider | None:
        """Load the last scheduled implementation owner.

        Corrupt scheduler state fails closed rather than silently
        breaking the 50/50 ownership invariant.
        """

        if not self.scheduler_state_path.exists():
            return None

        try:
            payload = json.loads(
                self.scheduler_state_path.read_text(
                    encoding="utf-8"
                )
            )

            value = payload.get("last_owner")

            if value is None:
                return None

            return Provider(value)

        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
            AttributeError,
        ) as exc:
            raise RuntimeError(
                "Persistent owner scheduler state is invalid"
            ) from exc

    def _save_last_owner(
        self,
        owner: Provider,
    ) -> None:
        """Atomically persist the most recently assigned owner."""

        temporary_path = (
            self.scheduler_state_path.with_suffix(
                ".json.tmp"
            )
        )

        payload = {
            "last_owner": owner.value,
        }

        temporary_path.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        temporary_path.replace(
            self.scheduler_state_path
        )

    def prepare_task(
        self,
        *,
        description: str,
        difficulty: Difficulty,
        previous_owner: Provider | None = None,
        task_category: TaskCategory | None = None,
        quota_state: QuotaState | None = None,
        quota_levels: dict[Provider, ProviderQuota] | None = None,
        spec: TaskSpec | None = None,
        baseline_commit: str = "",
    ) -> DevTask:
        """Create, route, classify and persist a development task.

        `task_category` is auto-classified from `description` when
        omitted (see router.classify_task_category). `quota_state` is
        controller-provided (never scraped); omitting it -- or leaving
        either provider's percentage as None -- routes exactly as
        before (NORMAL/UNKNOWN band, no conservation).
        """

        if not description.strip():
            raise ValueError("Task description must not be empty")

        task = DevTask(description=description.strip())

        task.stage = TaskStage.CLASSIFYING
        task.status = TaskStatus.RUNNING
        self.state.save(task)

        effective_previous_owner = (
            previous_owner
            if previous_owner is not None
            else self._load_last_owner()
        )

        # Automatic difficulty classification: the requested difficulty may
        # raise the level but never lowers a demonstrated safety floor.
        inference = infer_difficulty(
            task.description,
            requested=difficulty,
            spec=spec,
        )

        decision = self.router.route(
            description=task.description,
            base_difficulty=inference.effective,
            task_category=task_category,
            previous_owner=effective_previous_owner,
            quota_state=quota_state,
            quota_levels=quota_levels,
        )

        task.requested_difficulty = inference.requested
        task.inferred_difficulty = inference.inferred.value
        task.difficulty_reason = inference.reason_text
        task.baseline_commit = baseline_commit

        if spec is not None:
            task.objective = spec.objective
            task.allowed_paths = list(spec.allowed_paths)
            task.forbidden_scope = list(spec.forbidden_scope)
            task.acceptance_criteria = list(spec.acceptance_criteria)
            task.stop_conditions = list(spec.stop_conditions)
            task.program_id = spec.program_id
            task.package_id = spec.package_id

        task.owner = decision.owner
        task.reviewer = decision.reviewer
        task.implementer_model = decision.implementer_model
        task.reviewer_model = decision.reviewer_model
        task.difficulty = decision.difficulty
        task.task_category = decision.task_category
        task.quota_band_at_routing = decision.quota_band

        task.notes.append(
            f"Difficulty classified as {decision.difficulty.value} "
            f"(requested {difficulty.value}; inferred "
            f"{inference.inferred.value}; floor {inference.floor.value}; "
            f"category={decision.task_category.value}; "
            f"reason: {inference.reason_text})."
        )
        task.notes.append(
            f"Implementation owner: {decision.owner.value} "
            f"({decision.implementer_model.model})."
        )
        task.notes.append(
            f"Cross-provider reviewer: {decision.reviewer.value} "
            f"({decision.reviewer_model.model})."
        )

        if decision.quota_band not in (
            QuotaBand.NORMAL,
            QuotaBand.UNKNOWN,
        ):
            task.notes.append(
                "Implementer selection quota-conserved: "
                f"band={decision.quota_band.value}."
            )

        self._save_last_owner(decision.owner)

        approval = self.approval_policy.apply_to_task(task)

        if approval.requires_human:
            task.stage = TaskStage.WAITING_APPROVAL
            task.status = TaskStatus.NEEDS_HUMAN
            task.notes.append(
                "Human approval required before model execution."
            )

            for reason in approval.reasons:
                task.notes.append(
                    f"Approval required: {reason}."
                )

            self.state.save(task)
            return task

        task.stage = TaskStage.QUEUED
        task.status = TaskStatus.PENDING
        self.state.save(task)

        return task

    def load_task(self, task_id: str) -> DevTask:
        return self.state.load(task_id)

    def approve_task(
        self,
        task: DevTask,
        reason: str,
    ) -> None:
        self.approval_policy.approve_requirement(
            task,
            reason,
        )

        if self.approval_policy.all_requirements_approved(task):
            task.status = TaskStatus.PENDING
            task.stage = TaskStage.QUEUED
            task.notes.append(
                "All required human approvals granted."
            )

        self.state.save(task)

    def mark_running(
        self,
        task: DevTask,
        stage: TaskStage,
    ) -> None:
        if task.is_terminal():
            raise RuntimeError(
                f"Cannot restart terminal task {task.task_id}"
            )

        if (
            task.approvals
            and not self.approval_policy.all_requirements_approved(task)
        ):
            raise RuntimeError(
                "Task cannot run before all approval requirements are approved"
            )

        if (
            task.owner is None
            or task.reviewer is None
            or task.implementer_model is None
            or task.reviewer_model is None
        ):
            raise RuntimeError(
                "Task routing is incomplete; refusing execution"
            )

        task.stage = stage
        task.status = TaskStatus.RUNNING
        self.state.save(task)

    def mark_pass(
        self,
        task: DevTask,
        note: str,
    ) -> None:
        task.stage = TaskStage.COMPLETE
        task.status = TaskStatus.PASS
        task.notes.append(note)
        self.state.save(task)

    def mark_blocked(
        self,
        task: DevTask,
        note: str,
    ) -> None:
        task.stage = TaskStage.COMPLETE
        task.status = TaskStatus.BLOCKED
        task.notes.append(note)
        self.state.save(task)

    def mark_needs_human(
        self,
        task: DevTask,
        note: str,
    ) -> None:
        task.stage = TaskStage.WAITING_APPROVAL
        task.status = TaskStatus.NEEDS_HUMAN
        task.notes.append(note)
        self.state.save(task)


def _self_test() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    test_state = (
        repo_root
        / "tools"
        / "vector_dev_orchestrator"
        / ".orchestrator_test_state"
    )

    orchestrator = DevOrchestrator(
        repo_root=repo_root,
        state_root=test_state,
    )

    first = orchestrator.prepare_task(
        description="Fix deterministic parser bug and add regression tests.",
        difficulty=Difficulty.SERIOUS,
        previous_owner=None,
    )

    assert first.owner is Provider.CODEX
    assert first.reviewer is Provider.CLAUDE
    assert first.implementer_model is not None
    assert first.implementer_model.model == "gpt-5.6-sol"
    assert first.reviewer_model is not None
    assert first.reviewer_model.model == "sonnet"
    assert first.status is TaskStatus.PENDING
    assert first.stage is TaskStage.QUEUED

    risky = orchestrator.prepare_task(
        description="Change authentication security and deploy to production.",
        difficulty=Difficulty.CRITICAL,
        previous_owner=first.owner,
    )

    assert risky.status is TaskStatus.NEEDS_HUMAN
    assert risky.stage is TaskStage.WAITING_APPROVAL

    assert risky.owner is Provider.CLAUDE
    assert risky.reviewer is Provider.CODEX
    assert risky.implementer_model is not None
    assert risky.reviewer_model is not None

    try:
        orchestrator.mark_running(
            risky,
            TaskStage.IMPLEMENTING,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "Unapproved risky task must not start"
        )

    for requirement in tuple(risky.approvals):
        orchestrator.approve_task(
            risky,
            requirement.reason,
        )

    reloaded_risky = orchestrator.load_task(
        risky.task_id
    )

    assert reloaded_risky.status is TaskStatus.PENDING
    assert reloaded_risky.stage is TaskStage.QUEUED
    assert reloaded_risky.owner is Provider.CLAUDE
    assert reloaded_risky.implementer_model is not None

    orchestrator.mark_running(
        reloaded_risky,
        TaskStage.IMPLEMENTING,
    )

    reloaded_risky = orchestrator.load_task(
        risky.task_id
    )

    assert reloaded_risky.status is TaskStatus.RUNNING
    assert reloaded_risky.stage is TaskStage.IMPLEMENTING

    orchestrator.mark_running(
        first,
        TaskStage.IMPLEMENTING,
    )

    reloaded = orchestrator.load_task(first.task_id)

    assert reloaded.status is TaskStatus.RUNNING
    assert reloaded.stage is TaskStage.IMPLEMENTING

    orchestrator.mark_pass(
        first,
        "Controller self-test completed.",
    )

    reloaded = orchestrator.load_task(first.task_id)

    assert reloaded.status is TaskStatus.PASS
    assert reloaded.stage is TaskStage.COMPLETE

    # Restart the controller and prove ownership continues
    # from persisted scheduler state rather than resetting.
    restarted = DevOrchestrator(
        repo_root=repo_root,
        state_root=test_state,
    )

    after_restart = restarted.prepare_task(
        description="Make another harmless parser cleanup.",
        difficulty=Difficulty.ROUTINE,
    )

    # The previous persisted assignment was CLAUDE.
    assert after_restart.owner is Provider.CODEX
    assert after_restart.reviewer is Provider.CLAUDE

    another = restarted.prepare_task(
        description="Add another deterministic regression test.",
        difficulty=Difficulty.ROUTINE,
    )

    assert another.owner is Provider.CLAUDE
    assert another.reviewer is Provider.CODEX

    # A second restart must continue from CLAUDE -> CODEX.
    restarted_again = DevOrchestrator(
        repo_root=repo_root,
        state_root=test_state,
    )

    final_task = restarted_again.prepare_task(
        description="Verify persistent scheduler alternation.",
        difficulty=Difficulty.ROUTINE,
    )

    assert final_task.owner is Provider.CODEX
    assert final_task.reviewer is Provider.CLAUDE

    # --- Task-aware routing integration -------------------------------

    # task_category auto-classifies and persists on the task.
    debug_task = restarted_again.prepare_task(
        description="Debug the failure and find the root cause.",
        difficulty=Difficulty.SERIOUS,
        previous_owner=Provider.CODEX,
    )
    assert debug_task.task_category is TaskCategory.DEBUGGING
    assert debug_task.difficulty is Difficulty.SERIOUS
    assert debug_task.quota_band_at_routing is QuotaBand.UNKNOWN

    # An explicit task_category overrides auto-classification.
    explicit_category_task = restarted_again.prepare_task(
        description="Implement the ordinary feature as described.",
        difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CLAUDE,
        task_category=TaskCategory.ARCHITECTURE,
    )
    assert explicit_category_task.task_category is TaskCategory.ARCHITECTURE
    # ARCHITECTURE's floor (SERIOUS) lifts the requested SCOUT.
    assert explicit_category_task.difficulty is Difficulty.SERIOUS

    # quota_state is persisted and actually changes routing (implementer
    # conserved; reviewer independent of conservation).
    quota_task = restarted_again.prepare_task(
        description="Implement the ordinary feature as described.",
        difficulty=Difficulty.SERIOUS,
        previous_owner=Provider.CODEX,
        quota_state=QuotaState(claude_remaining_percent=10.0),
    )
    assert quota_task.owner is Provider.CLAUDE
    assert quota_task.quota_band_at_routing is QuotaBand.EMERGENCY
    assert quota_task.implementer_model is not None
    assert quota_task.implementer_model.model == "haiku"
    assert quota_task.reviewer_model is not None
    assert quota_task.reviewer_model.model == "gpt-5.6-sol"
    assert any(
        "quota-conserved" in note
        for note in quota_task.notes
    )

    # Approval gate still overrides routing: a SECURITY_SENSITIVE task
    # requires human approval regardless of the difficulty/category
    # floor bump it also receives, and routing does not bypass that.
    security_task = restarted_again.prepare_task(
        description="Rotate a credential and fix an authentication bug.",
        difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CODEX,
    )
    assert security_task.task_category is TaskCategory.SECURITY_SENSITIVE
    assert security_task.difficulty is Difficulty.HARD
    assert security_task.status is TaskStatus.NEEDS_HUMAN
    assert security_task.stage is TaskStage.WAITING_APPROVAL
    assert security_task.requires_human()

    # Task-aware routing metadata round-trips through persistence.
    reloaded_debug_task = restarted_again.load_task(debug_task.task_id)
    assert reloaded_debug_task.task_category is TaskCategory.DEBUGGING
    assert reloaded_debug_task.difficulty is Difficulty.SERIOUS

    for task_id in orchestrator.state.list_task_ids():
        path = test_state / "tasks" / f"{task_id}.json"

        if path.exists():
            path.unlink()

    tasks_dir = test_state / "tasks"

    if tasks_dir.exists():
        tasks_dir.rmdir()

    scheduler_path = (
        test_state
        / "scheduler.json"
    )

    if scheduler_path.exists():
        scheduler_path.unlink()

    scheduler_tmp_path = (
        test_state
        / "scheduler.json.tmp"
    )

    if scheduler_tmp_path.exists():
        scheduler_tmp_path.unlink()

    if test_state.exists():
        test_state.rmdir()


if __name__ == "__main__":
    _self_test()
