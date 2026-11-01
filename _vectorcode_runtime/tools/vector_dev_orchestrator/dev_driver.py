"""Small autonomous single-task driver for the VECTOR dev orchestrator.

This is the owner-facing entry point required by Step 8: it wires
together the EXISTING components (DevOrchestrator's 50/50 scheduler and
approval gate, WorktreeSessionManager for isolation, ExecutionCycle for
implement -> test -> cross-provider review -> bounded fix/re-review) into
one bounded call. It does not add new orchestration logic of its own.

The owner submits:
  - a task description
  - one or more explicit deterministic pytest targets
  - a bounded retry count

and gets back PASS / BLOCKED / NEEDS_HUMAN with full persisted evidence.

Hard safety invariants (see PLAN.md and the Step 7/8 safety rules):
  - never commits, stages, pushes, merges, resets or cleans Git state
    (this module issues no Git write commands at all -- ExecutionCycle/
    GitGuard/WorktreeManager own that, and neither ever commits either)
  - never automatically deletes ANY task's worktree/branch, including a
    PASS result -- the worktree holds the only copy of uncommitted
    implementation output, and cleanup is always a separate, deliberate,
    human-reviewed action via WorktreeSessionManager.remove_for_task
  - never bypasses a human approval gate: if DevOrchestrator.prepare_task
    already routed the task to NEEDS_HUMAN, no worktree is created and
    no provider is invoked
  - never loops without bound: ExecutionCycle enforces the retry budget
    this driver sets on the task; this driver itself makes exactly one
    run_once() call per invocation
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from models import (
    DevTask,
    Provider,
    ProviderQuota,
    QuotaBand,
    QuotaState,
    TaskCategory,
    TaskSpec,
    TaskStatus,
)
from orchestrator import DevOrchestrator
from router import Difficulty
from runner import invalid_test_targets
from worktree_manager import WorktreeInfo
from worktree_session import WorktreeSessionManager


@dataclass(slots=True)
class DriverResult:
    """Outcome of one bounded autonomous task run."""

    task: DevTask
    worktree: WorktreeInfo | None


def run_task(
    repo_root: Path,
    *,
    description: str,
    test_targets: list[str],
    difficulty: Difficulty = Difficulty.ROUTINE,
    max_retries: int = 2,
    run_ci_gate: bool = False,
    base_ref: str = "HEAD",
    previous_owner: Provider | None = None,
    task_category: TaskCategory | None = None,
    quota_state: QuotaState | None = None,
    quota_levels: dict[Provider, ProviderQuota] | None = None,
    spec: TaskSpec | None = None,
    quota_bands: dict[Provider, QuotaBand] | None = None,
    orchestrator: DevOrchestrator | None = None,
    session_manager: WorktreeSessionManager | None = None,
) -> DriverResult:
    """Run exactly one bounded development task end to end.

    Uses the existing 50/50 scheduler (DevOrchestrator.prepare_task),
    isolated worktree creation (WorktreeSessionManager.create) and the
    bounded implement/test/review/fix cycle (ExecutionCycle.run_once).
    Never commits/stages/pushes/merges/resets/cleans, never bypasses an
    approval gate, and never auto-deletes a worktree for any outcome.

    `previous_owner` is an optional passthrough to
    `DevOrchestrator.prepare_task` (default None: use the persisted
    scheduler state exactly as prepare_task already does). It exists
    only so a caller with a genuine, deliberate need to pin a specific
    implementer provider for one task (e.g. a validation contract that
    requires a specific provider route) can do so explicitly, without
    touching or biasing the persisted 50/50 alternation state itself.

    `task_category` and `quota_state` are optional passthroughs to the
    task-aware routing upgrade (router.ModelRouter.route). Omitting
    `task_category` auto-classifies it from `description`; omitting
    `quota_state` (or leaving a provider's percentage as None) routes
    exactly as before -- NORMAL/UNKNOWN band, no conservation. VECTOR
    never scrapes quota automatically; a caller supplies it only when
    it has a real reading.
    """

    if not test_targets:
        raise ValueError(
            "At least one deterministic pytest target is required"
        )

    problems = invalid_test_targets(test_targets)

    if problems:
        raise ValueError("Invalid pytest target(s): " + "; ".join(problems))

    if max_retries < 0:
        raise ValueError("max_retries must not be negative")

    repo_root = repo_root.resolve()

    orch = (
        orchestrator
        if orchestrator is not None
        else DevOrchestrator(repo_root)
    )

    task = orch.prepare_task(
        description=description,
        difficulty=difficulty,
        previous_owner=previous_owner,
        task_category=task_category,
        quota_state=quota_state,
        quota_levels=quota_levels,
        spec=spec,
        quota_bands=quota_bands,
    )

    if task.status is TaskStatus.NEEDS_HUMAN:
        # A genuine human approval gate was reached before any worktree
        # was created or any provider was invoked. Stop here -- do not
        # bypass permissions.
        return DriverResult(task=task, worktree=None)

    task.max_retries = max_retries
    orch.state.save(task)

    sessions = (
        session_manager
        if session_manager is not None
        else WorktreeSessionManager(repo_root, orchestrator=orch)
    )

    context = sessions.create(
        task.task_id,
        base_ref=base_ref,
    )

    # No except/finally here that removes the worktree: a crash must
    # propagate (see execution_cycle.py's crash-handling self-test) and
    # leave the worktree/state exactly as it was for audit, never
    # silently cleaned up.
    result = context.cycle.run_once(
        task,
        test_targets=test_targets,
        run_ci_gate=run_ci_gate,
    )

    return DriverResult(
        task=result,
        worktree=context.info,
    )


def resume_review_task(
    repo_root: Path,
    *,
    task_id: str,
    test_targets: list[str],
    run_ci_gate: bool = False,
    orchestrator: DevOrchestrator | None = None,
    session_manager: WorktreeSessionManager | None = None,
) -> DriverResult:
    """Run the deferred independent review of a task that stopped at WAITING_REVIEW.

    Re-opens the task's EXISTING worktree (never creates one), fails closed if it
    no longer matches what was tested, re-runs the targeted tests, then reviews,
    fixes (bounded) and verifies exactly like a normal cycle. Never removes anything.
    """

    if not test_targets:
        raise ValueError("At least one deterministic pytest target is required")

    problems = invalid_test_targets(test_targets)

    if problems:
        raise ValueError("Invalid pytest target(s): " + "; ".join(problems))

    repo_root = repo_root.resolve()
    orch = orchestrator if orchestrator is not None else DevOrchestrator(repo_root)
    task = orch.load_task(task_id)

    if task.status is not TaskStatus.WAITING_REVIEW:
        raise RuntimeError(f"Task {task_id} is {task.status.value}, not WAITING_REVIEW")

    sessions = (
        session_manager
        if session_manager is not None
        else WorktreeSessionManager(repo_root, orchestrator=orch)
    )
    context = sessions.attach(task_id)
    result = context.cycle.resume_review(
        task,
        test_targets=test_targets,
        run_ci_gate=run_ci_gate,
    )

    return DriverResult(task=result, worktree=context.info)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dev_driver.py",
        description=(
            "Run one bounded VECTOR development task through the "
            "orchestrator: implement -> targeted tests -> independent "
            "cross-provider review -> bounded fix/re-review. Returns "
            "PASS / BLOCKED / NEEDS_HUMAN and preserves the isolated "
            "worktree as evidence for every outcome."
        ),
    )

    parser.add_argument(
        "--repo-root",
        default=".",
        help="VECTOR repository root (default: current directory).",
    )
    parser.add_argument(
        "--description",
        required=True,
        help="Task description for the implementer/reviewer prompts.",
    )
    parser.add_argument(
        "--test",
        action="append",
        dest="test_targets",
        required=True,
        help=(
            "Explicit deterministic pytest target. Repeat for multiple "
            "targets."
        ),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Bounded review/fix retry budget (default: 2).",
    )
    parser.add_argument(
        "--difficulty",
        choices=[value.value for value in Difficulty],
        default=Difficulty.ROUTINE.value,
        help="Task difficulty classification (default: routine).",
    )
    parser.add_argument(
        "--run-ci-gate",
        action="store_true",
        help="Also run tools/ci_gate.py after review passes.",
    )
    parser.add_argument(
        "--base-ref",
        default="HEAD",
        help="Git ref the isolated worktree branches from (default: HEAD).",
    )
    parser.add_argument(
        "--previous-owner",
        choices=["codex", "claude"],
        default=None,
        help=(
            "Optional: pin the implementer provider for this one task by "
            "passing the OPPOSITE provider as if it had just implemented "
            "(default: use the persisted 50/50 scheduler state as-is)."
        ),
    )
    parser.add_argument(
        "--task-category",
        choices=[value.value for value in TaskCategory],
        default=None,
        help=(
            "Optional: override task-category classification instead of "
            "auto-classifying it from --description."
        ),
    )
    parser.add_argument(
        "--codex-quota-percent",
        type=float,
        default=None,
        help=(
            "Optional: Codex's remaining quota percentage (0-100), if "
            "known. Never scraped automatically -- omit when unknown, "
            "which routes exactly as if quota were normal."
        ),
    )
    parser.add_argument(
        "--claude-quota-percent",
        type=float,
        default=None,
        help=(
            "Optional: Claude's remaining quota percentage (0-100), if "
            "known. Never scraped automatically -- omit when unknown, "
            "which routes exactly as if quota were normal."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the result as JSON instead of plain text.",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    driver_result = run_task(
        Path(args.repo_root),
        description=args.description,
        test_targets=args.test_targets,
        difficulty=Difficulty(args.difficulty),
        max_retries=args.max_retries,
        run_ci_gate=args.run_ci_gate,
        base_ref=args.base_ref,
        previous_owner=(
            Provider(args.previous_owner)
            if args.previous_owner is not None
            else None
        ),
        task_category=(
            TaskCategory(args.task_category)
            if args.task_category is not None
            else None
        ),
        quota_state=QuotaState(
            codex_remaining_percent=args.codex_quota_percent,
            claude_remaining_percent=args.claude_quota_percent,
        ),
    )

    task = driver_result.task

    if args.json:
        payload = {
            "task_id": task.task_id,
            "status": task.status.value,
            "stage": task.stage.value,
            "difficulty": task.difficulty.value,
            "task_category": task.task_category.value,
            "quota_band_at_routing": task.quota_band_at_routing.value,
            "retry_count": task.retry_count,
            "escalation_count": task.escalation_count,
            "changed_files": task.changed_files,
            "notes": task.notes,
            "worktree_path": (
                str(driver_result.worktree.path)
                if driver_result.worktree is not None
                else None
            ),
            "worktree_branch": (
                driver_result.worktree.branch_name
                if driver_result.worktree is not None
                else None
            ),
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"task_id={task.task_id}")
        print(f"status={task.status.value}")
        print(f"stage={task.stage.value}")
        print(f"difficulty={task.difficulty.value}")
        print(f"task_category={task.task_category.value}")
        print(f"quota_band_at_routing={task.quota_band_at_routing.value}")
        print(f"retry_count={task.retry_count}")
        print(f"escalation_count={task.escalation_count}")

        if driver_result.worktree is not None:
            print(f"worktree_path={driver_result.worktree.path}")
            print(
                "worktree_branch="
                f"{driver_result.worktree.branch_name}"
            )
        else:
            print("worktree_path=<none, stopped at approval gate>")

        for note in task.notes:
            print(f"note: {note}")

    return 0 if task.status is TaskStatus.PASS else 1


def _self_test() -> None:
    """Deterministic driver self-test using injected fakes only.

    Never invokes a real Codex/Claude CLI or creates a real Git
    worktree -- a fake session manager stands in for
    WorktreeSessionManager so this stays fully offline and safe to run
    at any time, including before Codex/paid-provider calls are
    permitted.
    """

    import shutil

    from execution_cycle import (
        ExecutionCycle,
        _FakeCodex,
        _FakeGitGuard,
        _FakeClaude,
        _FakeFailingRunner,
        _FakeRunner,
    )
    from models import Provider, QuotaBand, TaskStage
    from worktree_session import WorktreeExecutionContext

    class _FakeSessionManager:
        """Stand-in for WorktreeSessionManager using only local dirs."""

        def __init__(self, base_dir: Path, cycle_factory) -> None:
            self.base_dir = base_dir
            self.cycle_factory = cycle_factory
            self.created: list[WorktreeExecutionContext] = []
            self.removed: list[WorktreeExecutionContext] = []

        def create(
            self,
            task_id: str,
            *,
            base_ref: str = "HEAD",
        ) -> WorktreeExecutionContext:
            path = self.base_dir / task_id
            path.mkdir(parents=True, exist_ok=True)

            info = WorktreeInfo(
                task_id=task_id,
                branch_name=f"vector-dev/{task_id}",
                path=path,
                base_ref=base_ref,
            )

            context = WorktreeExecutionContext(
                info=info,
                cycle=self.cycle_factory(path),
            )

            self.created.append(context)

            return context

        def remove(
            self,
            context: WorktreeExecutionContext,
            *,
            delete_branch: bool = False,
        ) -> None:
            self.removed.append(context)

    repo_root = Path(__file__).resolve().parents[2]

    state_root = (
        repo_root
        / "tools"
        / "vector_dev_orchestrator"
        / ".dev_driver_test_state"
    )

    scratch_dir = (
        repo_root
        / "tools"
        / "vector_dev_orchestrator"
        / ".dev_driver_test_worktrees"
    )

    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)

    orchestrator = DevOrchestrator(
        repo_root=repo_root,
        state_root=state_root,
    )

    def _passing_cycle_factory(path: Path) -> ExecutionCycle:
        return ExecutionCycle(
            path,
            orchestrator=orchestrator,
            codex=_FakeCodex(),
            claude=_FakeClaude(),
            runner=_FakeRunner(),
            git_guard=_FakeGitGuard(),
        )

    passing_sessions = _FakeSessionManager(
        scratch_dir,
        _passing_cycle_factory,
    )

    # 1. Argument validation happens before any state/worktree is
    #    touched.
    try:
        run_task(
            repo_root,
            description="Missing test targets.",
            test_targets=[],
            orchestrator=orchestrator,
            session_manager=passing_sessions,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Empty test_targets must be rejected"
        )

    try:
        run_task(
            repo_root,
            description="Negative retries.",
            test_targets=["tests/test_example.py"],
            max_retries=-1,
            orchestrator=orchestrator,
            session_manager=passing_sessions,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Negative max_retries must be rejected"
        )

    assert passing_sessions.created == []

    # 2. PASS scenario: worktree is created and, critically, NEVER
    #    automatically removed -- the driver must always preserve the
    #    worktree for owner review, even on a clean PASS.
    pass_result = run_task(
        repo_root,
        description=(
            "Fix deterministic parser cleanup and add regression test."
        ),
        test_targets=["tests/test_example.py"],
        difficulty=Difficulty.SERIOUS,
        max_retries=1,
        run_ci_gate=True,
        orchestrator=orchestrator,
        session_manager=passing_sessions,
    )

    assert pass_result.task.status is TaskStatus.PASS
    assert pass_result.task.stage is TaskStage.COMPLETE
    assert pass_result.task.max_retries == 1
    assert pass_result.worktree is not None
    assert pass_result.worktree.path.exists()
    assert pass_result.worktree.branch_name.startswith(
        "vector-dev/"
    )
    assert passing_sessions.removed == []

    # 2b. Explicit previous_owner pin (needed to satisfy a live
    #     validation contract that requires a specific implementer
    #     provider) is forwarded to prepare_task's existing routing
    #     unchanged -- it does not alter the 50/50 mechanism itself.
    pinned_result = run_task(
        repo_root,
        description="Pin the implementer provider for one task.",
        test_targets=["tests/test_example.py"],
        difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CODEX,
        orchestrator=orchestrator,
        session_manager=passing_sessions,
    )

    assert pinned_result.task.owner is Provider.CLAUDE
    assert pinned_result.task.reviewer is Provider.CODEX
    assert pinned_result.task.implementer_model is not None
    assert pinned_result.task.implementer_model.model == "haiku"
    assert pinned_result.task.reviewer_model is not None
    assert pinned_result.task.reviewer_model.model == "gpt-5.6-luna"

    # 2c. task_category / quota_state passthrough (task-aware routing
    #     upgrade): an explicit category floor and controller-supplied
    #     quota state both reach ModelRouter.route via prepare_task.
    routing_result = run_task(
        repo_root,
        description="Implement the ordinary feature as described.",
        test_targets=["tests/test_example.py"],
        difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CODEX,
        task_category=TaskCategory.ARCHITECTURE,
        quota_state=QuotaState(claude_remaining_percent=45.0),
        orchestrator=orchestrator,
        session_manager=passing_sessions,
    )

    assert routing_result.task.task_category is TaskCategory.ARCHITECTURE
    # ARCHITECTURE's floor (SERIOUS) lifts the requested SCOUT.
    assert routing_result.task.difficulty is Difficulty.SERIOUS
    assert routing_result.task.quota_band_at_routing is QuotaBand.CONSERVE

    # 3. Approval gate: a risky description must stop BEFORE any
    #    worktree is created or provider invoked.
    gate_result = run_task(
        repo_root,
        description=(
            "Change authentication security and deploy to production."
        ),
        test_targets=["tests/test_example.py"],
        difficulty=Difficulty.CRITICAL,
        orchestrator=orchestrator,
        session_manager=passing_sessions,
    )

    assert gate_result.task.status is TaskStatus.NEEDS_HUMAN
    assert gate_result.worktree is None
    # Still just the three worktrees from the PASS, pinned-owner and
    # routing-passthrough scenarios above.
    assert len(passing_sessions.created) == 3

    # 4. BLOCKED scenario (failing targeted tests): worktree still
    #    created and still never auto-removed.
    def _failing_cycle_factory(path: Path) -> ExecutionCycle:
        return ExecutionCycle(
            path,
            orchestrator=orchestrator,
            codex=_FakeCodex(),
            claude=_FakeClaude(),
            runner=_FakeFailingRunner(),
            git_guard=_FakeGitGuard(),
        )

    failing_sessions = _FakeSessionManager(
        scratch_dir,
        _failing_cycle_factory,
    )

    blocked_result = run_task(
        repo_root,
        description="Attempt a harmless parser cleanup.",
        test_targets=["tests/test_example.py"],
        difficulty=Difficulty.ROUTINE,
        orchestrator=orchestrator,
        session_manager=failing_sessions,
    )

    assert blocked_result.task.status is TaskStatus.BLOCKED
    assert blocked_result.worktree is not None
    assert blocked_result.worktree.path.exists()
    assert failing_sessions.removed == []

    # 5. CLI argument parsing is exercised directly (no execution) so
    #    the owner-facing usage shape stays covered without invoking a
    #    real provider.
    parsed = _parse_args(
        [
            "--repo-root",
            str(repo_root),
            "--description",
            "Example task.",
            "--test",
            "tests/test_example.py",
            "--test",
            "tests/test_other.py",
            "--max-retries",
            "0",
            "--difficulty",
            "scout",
        ]
    )

    assert parsed.test_targets == [
        "tests/test_example.py",
        "tests/test_other.py",
    ]
    assert parsed.max_retries == 0
    assert parsed.difficulty == "scout"
    assert parsed.run_ci_gate is False
    assert parsed.task_category is None
    assert parsed.codex_quota_percent is None
    assert parsed.claude_quota_percent is None

    routing_parsed = _parse_args(
        [
            "--repo-root",
            str(repo_root),
            "--description",
            "Example task.",
            "--test",
            "tests/test_example.py",
            "--task-category",
            "architecture",
            "--codex-quota-percent",
            "20",
            "--claude-quota-percent",
            "80",
        ]
    )

    assert routing_parsed.task_category == "architecture"
    assert routing_parsed.codex_quota_percent == 20.0
    assert routing_parsed.claude_quota_percent == 80.0

    # Cleanup.
    for task_id in orchestrator.state.list_task_ids():
        path = state_root / "tasks" / f"{task_id}.json"
        if path.exists():
            path.unlink()

    tasks_dir = state_root / "tasks"
    if tasks_dir.exists():
        tasks_dir.rmdir()

    if state_root.exists():
        shutil.rmtree(state_root)

    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(main())
    _self_test()
