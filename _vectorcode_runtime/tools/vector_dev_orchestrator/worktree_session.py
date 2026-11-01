"""Task worktree execution context for the VECTOR dev orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from claude_adapter import ClaudeAdapter
from codex_adapter import CodexAdapter
from execution_cycle import ExecutionCycle
from git_guard import GitGuard
from models import DevTask, TaskStatus
from orchestrator import DevOrchestrator
from runner import CommandRunner
from worktree_manager import WorktreeInfo, WorktreeManager


@dataclass(slots=True)
class WorktreeExecutionContext:
    info: WorktreeInfo
    cycle: ExecutionCycle


class WorktreeSessionManager:
    """Create an isolated execution cycle for one development task."""

    # Evidence-bearing terminal states (issue 5). A task ending in any of
    # these must not be auto-cleaned: its worktree/branch is the audit
    # trail for what happened and why. Only TaskStatus.PASS is safe for
    # a caller to remove without an explicit, deliberate override.
    _PRESERVE_STATUSES = frozenset(
        {
            TaskStatus.BLOCKED,
            TaskStatus.NEEDS_HUMAN,
            TaskStatus.FAILED,
            TaskStatus.RUNNING,
            TaskStatus.PENDING,
            TaskStatus.WAITING_REVIEW,
        }
    )

    @classmethod
    def requires_preservation(cls, task: DevTask) -> bool:
        """Whether a task's worktree/branch must not be auto-deleted.

        Any non-PASS status is treated as evidence-bearing, including a
        crash/exception that left the task RUNNING (never resolved to a
        terminal status) -- there is no safe status under which an
        automated caller should destroy the working tree.
        """

        return task.status in cls._PRESERVE_STATUSES

    def __init__(
        self,
        repo_root: Path,
        *,
        orchestrator: DevOrchestrator | None = None,
        worktree_root: Path | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()

        self.orchestrator = (
            orchestrator
            if orchestrator is not None
            else DevOrchestrator(self.repo_root)
        )

        self.worktrees = WorktreeManager(
            self.repo_root,
            worktree_root,
        )

    def create(
        self,
        task_id: str,
        *,
        base_ref: str = "HEAD",
    ) -> WorktreeExecutionContext:
        info = self.worktrees.create(
            task_id,
            base_ref=base_ref,
        )

        try:
            cycle = ExecutionCycle(
                info.path,
                orchestrator=self.orchestrator,
                codex=CodexAdapter(info.path),
                claude=ClaudeAdapter(info.path),
                runner=CommandRunner(info.path),
                git_guard=GitGuard(info.path),
            )
        except Exception:
            self.worktrees.remove(
                info,
                delete_branch=True,
            )
            raise

        return WorktreeExecutionContext(
            info=info,
            cycle=cycle,
        )

    def attach(self, task_id: str) -> WorktreeExecutionContext:
        """An execution cycle bound to an EXISTING task worktree (resume a review)."""

        info = self.worktrees.attach(task_id)

        return WorktreeExecutionContext(
            info=info,
            cycle=ExecutionCycle(
                info.path,
                orchestrator=self.orchestrator,
                codex=CodexAdapter(info.path),
                claude=ClaudeAdapter(info.path),
                runner=CommandRunner(info.path),
                git_guard=GitGuard(info.path),
            ),
        )

    def remove(
        self,
        context: WorktreeExecutionContext,
        *,
        delete_branch: bool = False,
    ) -> None:
        self.worktrees.remove(
            context.info,
            delete_branch=delete_branch,
        )

    def remove_for_task(
        self,
        context: WorktreeExecutionContext,
        task: DevTask,
        *,
        delete_branch: bool = False,
        force: bool = False,
    ) -> None:
        """Remove a task's worktree, refusing to destroy audit evidence.

        This is the safe API callers (including the autonomous driver)
        should use instead of `remove()` directly: it refuses to delete
        an evidence-bearing task's worktree/branch (failed, blocked,
        NEEDS_HUMAN, provider-failed, parser-failed, crashed/RUNNING,
        or HEAD-movement) unless `force=True` is passed for an explicit,
        deliberate human cleanup decision.
        """

        if not force and self.requires_preservation(task):
            raise RuntimeError(
                "Refusing to remove worktree/branch for evidence-"
                f"bearing task {task.task_id} "
                f"(status={task.status.value}); failed, blocked, "
                "NEEDS_HUMAN, FAILED and RUNNING/crashed task state "
                "must be preserved for audit. Pass force=True only for "
                "an explicit, reviewed human cleanup decision."
            )

        self.remove(
            context,
            delete_branch=delete_branch,
        )


def _self_test() -> None:
    import shutil
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        git = shutil.which("git")
        if git is None:
            raise RuntimeError("Git executable not found.")

        def run(*args: str) -> None:
            result = subprocess.run(
                [git, "-C", str(root), *args],
                capture_output=True,
                text=True,
                shell=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr)

        run("init")
        run("config", "user.email", "vector-test@example.invalid")
        run("config", "user.name", "VECTOR Test")

        (root / "tracked.txt").write_text(
            "baseline\n",
            encoding="utf-8",
        )

        run("add", "tracked.txt")
        run("commit", "-m", "baseline")

        manager = WorktreeManager(
            root,
            Path(temp_dir) / "worktrees",
            git_executable=git,
        )

        info = manager.create("session-test")

        assert info.path.exists()
        assert info.path != root

        manager.remove(
            info,
            delete_branch=True,
        )

        assert not info.path.exists()

        # Issue 5: evidence-bearing task worktrees must not be
        # auto-deleted through the session-manager API.
        session_manager = WorktreeSessionManager(
            root,
            worktree_root=Path(temp_dir) / "session-worktrees",
        )

        blocked_task = DevTask(
            description="Preservation guard self-test."
        )
        blocked_task.status = TaskStatus.BLOCKED

        assert WorktreeSessionManager.requires_preservation(
            blocked_task
        )

        blocked_context = session_manager.create(
            "preserve-test"
        )

        try:
            session_manager.remove_for_task(
                blocked_context,
                blocked_task,
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError(
                "Evidence-bearing (BLOCKED) task worktree must not be "
                "auto-removed"
            )

        assert blocked_context.info.path.exists()

        # An explicit, deliberate force=True override remains possible
        # for a human-reviewed cleanup decision.
        session_manager.remove_for_task(
            blocked_context,
            blocked_task,
            delete_branch=True,
            force=True,
        )

        assert not blocked_context.info.path.exists()

        # A PASS task's worktree may be removed without force.
        passed_task = DevTask(
            description="Preservation guard self-test."
        )
        passed_task.status = TaskStatus.PASS

        assert not WorktreeSessionManager.requires_preservation(
            passed_task
        )

        passed_context = session_manager.create(
            "preserve-test-pass"
        )

        session_manager.remove_for_task(
            passed_context,
            passed_task,
            delete_branch=True,
        )

        assert not passed_context.info.path.exists()


if __name__ == "__main__":
    _self_test()
