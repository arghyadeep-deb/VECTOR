"""Autonomous worker: drains the backlog through the Claude<->Codex bridge.

Each run pulls pending backlog specs and runs each one through
dev_driver.run_task() (routing -> isolated worktree -> implement -> tests
-> independent cross-provider review -> bounded fix/re-review). On PASS the
worker commits the task's changed files to that task's own
`vector-dev/<task_id>` branch so a human can review and merge in one batch.

Hard safety rules (enforced in code, covered by the self-test):
  - never commits anywhere except a branch named vector-dev/*; never main
  - never pushes, merges, resets, cleans, or deletes a worktree/branch
  - commits ONLY the files the task reported as changed, and only if the
    worktree contains exactly those files (anything unexpected -> no commit)
  - never bypasses hooks, signing, permissions or the approval gate
  - stops the whole run on a crash, after N consecutive failures, when the
    daily cap is reached, or when a STOP file exists
  - a lock file prevents two workers running at once
  - an item interrupted mid-run is never replayed automatically

CLI:
  python autonomous_worker.py add --description "..." --test tests/x.py
  python autonomous_worker.py run [--max-tasks N]
  python autonomous_worker.py status
  python autonomous_worker.py stop | resume
  python autonomous_worker.py requeue ITEM_ID
  python autonomous_worker.py close-manual ITEM_ID --commit SHA --note "..." --owner-approved yes

close-manual is OWNER-RUN TOOLING (POLICY.md sec 14/15: "No model may self-authorize a
human-gated action"). It records a needs_human/blocked item as completed via directly-
supervised manual work done OUTSIDE the bridge's own automated pipeline (built, verified,
and merged by a human + their assistant with the human's explicit real-time sign-off) --
it does not and cannot grant that sign-off itself. Neither Claude nor Codex may invoke it
on their own initiative; it exists so the owner has one clean command instead of a raw
JSON edit for bookkeeping work that was already independently approved in chat.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import backlog as bl
from backlog import BacklogItem, BacklogStore
from dev_driver import DriverResult, resume_review_task, run_task
from git_guard import GitGuard
from integration import IntegrationStage
from orchestrator import DevOrchestrator
from models import (
    Difficulty,
    Provider,
    ProviderQuota,
    QuotaBand,
    QuotaState,
    TaskCategory,
    TaskSpec,
    TaskStatus,
)
from quota import BAND_LEVEL, QuotaBoard
from router import difficulty_rank, quota_band_for_percent
from runner import CommandRunner

BRANCH_PREFIX = "vector-dev/"


# --- guarded commit ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class CommitResult:
    committed: bool
    sha: str | None = None
    branch: str | None = None
    reason: str = ""


def _git(
    worktree: Path,
    *args: str,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("git")

    if executable is None:
        raise RuntimeError("git executable was not found")

    return subprocess.run(
        [executable, "-C", str(worktree), *args],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )


def _norm(paths: list[str] | set[str]) -> set[str]:
    return {p.replace("\\", "/").strip() for p in paths if p.strip()}


def commit_task_changes(
    worktree: Path,
    changed_files: list[str],
    message: str,
) -> CommitResult:
    """Commit exactly `changed_files` on a vector-dev/* branch, or refuse."""

    expected = _norm(changed_files)

    if not expected:
        return CommitResult(False, reason="Task reported no changed files.")

    branch_proc = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch_proc.stdout.strip()

    if branch_proc.returncode != 0 or not branch.startswith(BRANCH_PREFIX):
        return CommitResult(
            False,
            branch=branch or None,
            reason=(
                f"Refusing to commit: branch {branch!r} is not a "
                f"{BRANCH_PREFIX}* task branch."
            ),
        )

    actual = _norm(set(GitGuard(worktree).snapshot().files))

    if actual != expected:
        return CommitResult(
            False,
            branch=branch,
            reason=(
                "Refusing to commit: worktree files differ from the "
                f"task's reported changes. unexpected="
                f"{sorted(actual - expected)} "
                f"missing={sorted(expected - actual)}"
            ),
        )

    add = _git(worktree, "add", "--", *sorted(expected))

    if add.returncode != 0:
        return CommitResult(
            False, branch=branch, reason=f"git add failed: {add.stderr.strip()[-300:]}"
        )

    staged = _norm(
        set(_git(worktree, "diff", "--cached", "--name-only").stdout.split("\n"))
    )

    if staged != expected:
        return CommitResult(
            False,
            branch=branch,
            reason=f"Staged set {sorted(staged)} != expected {sorted(expected)}.",
        )

    commit = _git(worktree, "commit", "-F", "-", input_text=message)

    if commit.returncode != 0:
        return CommitResult(
            False,
            branch=branch,
            reason=(
                "git commit failed (hooks/signing/identity are never "
                f"bypassed): {(commit.stderr or commit.stdout).strip()[-300:]}"
            ),
        )

    sha = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    committed = _norm(
        set(
            _git(
                worktree, "show", "--name-only", "--format=", "HEAD"
            ).stdout.split("\n")
        )
    )

    if committed != expected:
        return CommitResult(
            False,
            sha=sha,
            branch=branch,
            reason=f"Commit contents {sorted(committed)} != expected.",
        )

    return CommitResult(True, sha=sha, branch=branch)


def build_commit_message(item: BacklogItem, task: Any) -> str:
    first_line = item.title or " ".join(item.description.split())[:72]
    owner = getattr(task.implementer_model, "model", "?")
    reviewer = getattr(task.reviewer_model, "model", "?")

    return (
        f"dev-orchestrator: {first_line}\n\n"
        f"Backlog item: {item.item_id}\n"
        f"Task: {task.task_id}\n"
        f"Implementer: {task.owner.value if task.owner else '?'} ({owner})\n"
        f"Reviewer: {task.reviewer.value if task.reviewer else '?'} ({reviewer})\n"
        f"Targeted tests: {', '.join(item.test_targets)} (passed)\n"
        "Independent cross-provider review: PASS\n\n"
        "Committed automatically to a task branch. NOT merged: review "
        "before merging into main.\n"
    )


# --- failure evidence -------------------------------------------------

_MISSING_TARGET_RE = re.compile(r"file or directory not found:\s*(.+)")
_EVIDENCE_TAIL_CHARS = 1200


def _bounded(text: str, limit: int) -> str:
    from execution_cycle import ExecutionCycle

    redacted = ExecutionCycle._redact_secrets(text or "")

    if len(redacted) <= limit:
        return redacted

    # Keep BOTH ends: a usage error is often printed first, the verdict last.
    head = limit // 4

    return redacted[:head] + "\n...[truncated]...\n" + redacted[-(limit - head):]


def build_failure_evidence(item: BacklogItem, task: Any) -> dict[str, Any]:
    """Bounded, secret-redacted diagnosis of why a task did not pass.

    `kind` separates what a correction can fix from what it cannot:
      implementation - the change is wrong/incomplete (retry with feedback helps)
      test_spec      - the test specification itself is wrong (bad target/usage
                       error); re-running the same package cannot fix it, the
                       PLAN must change
      infrastructure - the machinery failed (timeout, internal error)
    """

    from runner import invalid_test_target_reason
    from text_signals import norm_repo_path

    notes = [n for n in getattr(task, "notes", []) if isinstance(n, str)]
    evidence: dict[str, Any] = {
        "category": "unknown",
        "kind": "implementation",
        "command": "",
        "exit_code": None,
        "tail": "",
        "findings": [],
        "note": _bounded(notes[-1] if notes else "", 300),
    }
    tests = list(getattr(task, "tests", []) or [])
    last = tests[-1] if tests else None
    findings = [
        _bounded(f"{getattr(f.severity, 'value', f.severity)}: {f.summary}", 200)
        for f in getattr(task, "review_findings", [])
        if not getattr(f, "resolved", False)
    ][:3]
    evidence["findings"] = findings

    if last is not None and not last.passed:
        text = (last.stdout or "") + "\n" + (last.stderr or "")
        code = last.exit_code
        evidence["command"] = _bounded(last.command, 300)[-300:]
        evidence["exit_code"] = code
        evidence["tail"] = _bounded(text, _EVIDENCE_TAIL_CHARS)

        if code == 4:
            match = _MISSING_TARGET_RE.search(text)
            missing = match.group(1).strip() if match else ""
            wanted = norm_repo_path(missing).split("::", 1)[0]
            deliverable = (
                bool(missing)
                and invalid_test_target_reason(missing) is None
                and any(norm_repo_path(a) == wanted for a in item.allowed_paths)
            )
            evidence["category"], evidence["kind"] = (
                ("test_file_missing", "implementation")
                if deliverable
                else ("test_spec", "test_spec")
            )
        elif code == 5:
            evidence["category"] = "no_tests_collected"
        elif code == 2:
            evidence["category"] = "collection_error"
        elif code == 3 or code is None or code < 0:
            evidence["category"], evidence["kind"] = "infrastructure", "infrastructure"
        else:
            evidence["category"] = "test_failure"

        return evidence

    if any(n.startswith("SCOPE VIOLATION") for n in notes):
        evidence["category"] = "scope_violation"
    elif any("changed no files" in n for n in notes):
        evidence["category"] = "no_change"
    elif any("HEAD" in n and "moved" in n.lower() for n in notes):
        evidence["category"], evidence["kind"] = "infrastructure", "infrastructure"
    elif findings:
        evidence["category"] = "review_rejected"

    return evidence


# --- worker -----------------------------------------------------------


@dataclass(slots=True)
class WorkerConfig:
    max_tasks_per_run: int = 3
    daily_cap: int = 5
    max_consecutive_failures: int = 2
    lock_stale_seconds: int = 4 * 3600
    quota_state: QuotaState | None = None
    # Read real Codex telemetry into the quota board at the start of a run.
    # Off by default so tests never touch ~/.codex; the CLI turns it on.
    refresh_quota_telemetry: bool = False


@dataclass(slots=True)
class RunSummary:
    processed: list[tuple[str, str]] = field(default_factory=list)
    # deferred independent reviews that became affordable and were run
    resumed: list[tuple[str, str]] = field(default_factory=list)
    stopped_because: str = "backlog empty"


class AutonomousWorker:
    def __init__(
        self,
        repo_root: Path,
        state_dir: Path,
        *,
        config: WorkerConfig | None = None,
        run_task_fn: Callable[..., DriverResult] | None = None,
        review_fn: Callable[..., DriverResult] | None = None,
        orchestrator: DevOrchestrator | None = None,
        commit_fn: Callable[[Path, list[str], str], CommitResult] | None = None,
        today_fn: Callable[[], str] | None = None,
        echo: bool = True,
        quota_board: QuotaBoard | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or WorkerConfig()
        # ONE orchestrator, used for both the implement path and the resume-review path.
        # Each provider function (run_task/resume_review_task) can build its own default
        # DevOrchestrator(repo_root) if left unset, but that default only happens to match
        # this worker's own state when repo_root's own tools/vector_dev_orchestrator/.state
        # is genuinely where the worker's state lives (the real production layout). Any
        # other layout -- a sandbox, a test, a --repo-root override -- would silently split
        # implementation and review onto two different task stores. Always pass the SAME
        # orchestrator explicitly so behavior never depends on that path coincidence.
        self.orchestrator = orchestrator or DevOrchestrator(self.repo_root)
        self.run_task_fn = run_task_fn or run_task
        self.review_fn = review_fn or resume_review_task
        self.commit_fn = commit_fn or commit_task_changes
        self.today_fn = today_fn or (lambda: date.today().isoformat())
        self.echo = echo

        self.backlog = BacklogStore(self.state_dir / "backlog.json")
        self.stop_path = self.state_dir / "STOP"
        self.lock_path = self.state_dir / "worker.lock"
        self.counter_path = self.state_dir / "worker_state.json"
        self.notify_path = self.state_dir / "notifications.jsonl"
        self.quota = quota_board or QuotaBoard(self.state_dir / "quota.json")

    # notifications: durable JSONL; "attention" means a human is needed
    def notify(self, level: str, message: str, item_id: str | None = None) -> None:
        record = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": level,
            "item_id": item_id,
            "message": message,
        }

        with self.notify_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        if self.echo:
            print(f"[{level}] {item_id or '-'}: {message}")

    # daily counter
    def _count_today(self) -> int:
        if not self.counter_path.exists():
            return 0
        try:
            state = json.loads(self.counter_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise RuntimeError(
                f"Worker counter state is corrupt: {self.counter_path}"
            ) from exc

        return int(state["count"]) if state.get("date") == self.today_fn() else 0

    def _bump_today(self) -> None:
        fd, temp_name = tempfile.mkstemp(
            prefix="worker_state.", suffix=".tmp", dir=self.state_dir, text=True
        )
        temporary_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {"date": self.today_fn(), "count": self._count_today() + 1},
                    handle,
                )
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(self.counter_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    # lock
    def _acquire_lock(self) -> bool:
        for _ in range(2):
            try:
                fd = os.open(
                    self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
            except FileExistsError:
                age = time.time() - self.lock_path.stat().st_mtime

                if age > self.config.lock_stale_seconds:
                    self.notify(
                        "attention",
                        f"Reclaiming stale worker lock ({int(age)}s old).",
                    )
                    self.lock_path.unlink(missing_ok=True)
                    continue

                return False

            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"pid": os.getpid(), "time": time.time()}))

            return True

        return False

    def _release_lock(self) -> None:
        self.lock_path.unlink(missing_ok=True)

    def touch_lock(self) -> None:
        """Refresh the lock's mtime so a long owner-started run is not 'stale'."""

        try:
            os.utime(self.lock_path, None)
        except OSError:
            pass

    # main loop
    def run(self, max_tasks: int | None = None) -> RunSummary:
        summary = RunSummary()

        if not self._acquire_lock():
            summary.stopped_because = "another worker holds the lock"
            return summary

        try:
            for item in self.backlog.recover_interrupted():
                self.notify(
                    "attention",
                    "Interrupted item moved to NEEDS_HUMAN, not replayed.",
                    item.item_id,
                )

            limit = (
                max_tasks
                if max_tasks is not None
                else self.config.max_tasks_per_run
            )
            failures = 0

            if self.config.refresh_quota_telemetry:
                self.quota.refresh_from_telemetry()

            self.reactivate_deferred()

            # Reviews that were waiting for quota run first, but only when the reviewer
            # provider is no longer in EMERGENCY (the owner can force one explicitly
            # with `resume-reviews --allow-emergency`).
            summary.resumed = self.resume_reviews()

            while len(summary.processed) < limit:
                if self.stop_path.exists():
                    summary.stopped_because = "STOP file present"
                    break

                if self._count_today() >= self.config.daily_cap:
                    summary.stopped_because = "daily cap reached"
                    break

                # The scheduled worker never advances an owner-started
                # program: those packages belong to the supervisor and its
                # own run budget, not the daily maintenance cap.
                item = self.backlog.next_pending(manual_only=True)

                if item is None:
                    summary.stopped_because = "backlog empty"
                    break

                hold = self.holding_reason()

                if hold is not None:
                    # State is preserved (item stays PENDING). Independent
                    # review is never faked with the same/other provider.
                    summary.stopped_because = f"provider unavailable: {hold}; work left pending"
                    break

                outcome = self._process(item, count_daily=True)
                summary.processed.append((item.item_id, outcome))

                if outcome == bl.DEFERRED:
                    summary.stopped_because = "provider became unavailable; item deferred"
                    break

                if outcome == bl.CRASHED:
                    summary.stopped_because = "crash (fail closed)"
                    break

                if outcome == bl.PASSED:
                    failures = 0
                elif outcome == bl.BLOCKED:
                    failures += 1

                if failures >= self.config.max_consecutive_failures:
                    summary.stopped_because = "consecutive failures"
                    self.notify(
                        "attention",
                        f"{failures} consecutive failures; worker stopped.",
                    )
                    break
            else:
                summary.stopped_because = "max tasks per run"
        finally:
            self._release_lock()

        return summary

    # --- provider availability ----------------------------------------

    def unavailable_provider(self) -> Provider | None:
        """A provider that is EXHAUSTED, or None.

        Every implementation needs BOTH providers (implementer + an
        independent reviewer from the other one), so either being out
        blocks integration-bound work. UNKNOWN does not block.
        """

        for provider in Provider:
            if not self.quota.available(provider):
                return provider

        return None

    def holding_reason(self) -> str | None:
        """Why new work must be held right now, or None.

        A provider EXHAUSTED, or BOTH providers in quota EMERGENCY (nobody left
        to implement). One provider in EMERGENCY is not a hold: the other one
        implements and the EMERGENCY provider's review is deferred (POLICY.md 9-10).
        """

        blocked = self.unavailable_provider()

        if blocked is not None:
            return f"{blocked.value} exhausted"

        if all(band is QuotaBand.EMERGENCY for band in self.quota.bands().values()):
            return "both providers are in quota EMERGENCY"

        return None

    def reactivate_deferred(self) -> list[str]:
        """Return DEFERRED items to PENDING once both providers are usable."""

        if self.holding_reason() is not None:
            return []

        revived: list[str] = []

        for item in self.backlog.all():
            if item.status == bl.DEFERRED:
                self.backlog.update(
                    item.item_id,
                    status=bl.PENDING,
                    result_note=f"Reactivated after deferral: {item.deferred_reason}",
                )
                revived.append(item.item_id)

        return revived

    @staticmethod
    def _spec_for(item: BacklogItem) -> TaskSpec | None:
        if not (item.allowed_paths or item.program_id):
            return None

        return TaskSpec(
            objective=item.objective,
            allowed_paths=tuple(item.allowed_paths),
            forbidden_scope=tuple(item.forbidden_scope),
            acceptance_criteria=tuple(item.acceptance_criteria),
            stop_conditions=tuple(item.stop_conditions),
            test_targets=tuple(item.test_targets),
            review_only=item.review_only,
            acceptance_critical=item.acceptance_critical,
            program_id=item.program_id,
            package_id=item.package_id,
        )

    def execute_item(self, item: BacklogItem, *, base_ref: str | None = None) -> str:
        """Run one backlog item outside the daily maintenance cap.

        Used by the supervisor for program packages (which are governed by
        the program's own run budget). Defers, without running anything, if
        a provider is exhausted.
        """

        reason = self.holding_reason()

        if reason is not None:
            self.backlog.update(
                item.item_id,
                status=bl.DEFERRED,
                deferred_reason=reason,
                result_note=f"Deferred: {reason}; nothing was run.",
            )
            return bl.DEFERRED

        return self._process(item, count_daily=False, base_ref=base_ref)

    def _process(
        self,
        item: BacklogItem,
        *,
        count_daily: bool = True,
        base_ref: str | None = None,
    ) -> str:
        self.backlog.update(item.item_id, status=bl.RUNNING, attempts=item.attempts + 1)

        if count_daily:
            self._bump_today()

        previous_owner = {
            "codex": Provider.CLAUDE,
            "claude": Provider.CODEX,
        }.get(item.preferred_owner or "")

        extra: dict[str, Any] = {}

        if base_ref is not None:
            # Program packages build on the accepted work already integrated.
            extra["base_ref"] = base_ref

        try:
            result = self.run_task_fn(
                self.repo_root,
                description=item.description,
                test_targets=item.test_targets,
                difficulty=Difficulty(item.difficulty),
                max_retries=item.max_retries,
                run_ci_gate=item.run_ci_gate,
                task_category=(
                    TaskCategory(item.task_category)
                    if item.task_category
                    else None
                ),
                quota_state=self.config.quota_state,
                quota_levels=self.quota.levels(),
                quota_bands=self.quota.bands(),
                spec=self._spec_for(item),
                previous_owner=previous_owner,
                orchestrator=self.orchestrator,
                **extra,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed on anything
            return self._record_crash(item, exc)

        return self._settle(item, result)

    def _record_crash(self, item: BacklogItem, exc: Exception) -> str:
        note = _bounded(f"{type(exc).__name__}: {str(exc)[:300]}", 400)

        if isinstance(exc, PermissionError):
            note += (
                " [likely a Codex sandbox-created file the owner account cannot "
                "read (Windows elevated sandbox); worktree preserved]"
            )

        self.backlog.update(
            item.item_id,
            status=bl.CRASHED,
            result_note=note,
            provider_calls=self.CRASH_PROVIDER_CALLS,
            failure_evidence={
                "category": "crash",
                "kind": "infrastructure",
                "command": "",
                "exit_code": None,
                "tail": _bounded(note, 400),
                "findings": [],
                "note": "",
            },
        )
        self.notify(
            "attention",
            f"Crashed ({type(exc).__name__}); task left non-terminal, "
            "worktree preserved. Worker stopped.",
            item.item_id,
        )
        return bl.CRASHED

    def _settle(self, item: BacklogItem, result: DriverResult) -> str:
        """Record a finished (or deferred) task cycle on its backlog item."""

        task = result.task
        worktree = result.worktree
        common: dict[str, Any] = {
            "task_id": task.task_id,
            "worktree_path": str(worktree.path) if worktree else None,
            "branch": worktree.branch_name if worktree else None,
            "result_note": _bounded(task.notes[-1], 500) if task.notes else "",
            "requested_difficulty": task.requested_difficulty,
            "inferred_difficulty": task.inferred_difficulty,
            "effective_difficulty": task.difficulty.value if getattr(task, "difficulty", None) else "",
            "difficulty_reason": task.difficulty_reason,
            "provider_calls": self.actual_provider_calls(task),
        }

        if task.status not in (TaskStatus.PASS, TaskStatus.WAITING_REVIEW):
            common["failure_evidence"] = build_failure_evidence(item, task)

        unavailable = self._unavailable_marker(task)

        if unavailable is not None and task.status is not TaskStatus.PASS:
            self.quota.mark_exhausted(
                unavailable, f"provider stopped a task with a usage-limit error ({task.task_id})"
            )
            self.backlog.update(
                item.item_id,
                status=bl.DEFERRED,
                deferred_reason=f"{unavailable.value} exhausted mid-task",
                **common,
            )
            self.notify(
                "attention",
                f"{unavailable.value} hit a usage limit; item deferred (worktree "
                "preserved, no substitute reviewer used).",
                item.item_id,
            )
            return bl.DEFERRED

        if task.status is TaskStatus.WAITING_REVIEW:
            # Implemented and tested, independent review deferred: NOT a pass, nothing is
            # committed or integrated until that review actually happens.
            self.backlog.update(
                item.item_id,
                status=bl.WAITING_REVIEW,
                awaiting_reviewer=task.reviewer.value if task.reviewer else "",
                **common,
            )
            self.notify(
                "info",
                f"WAITING_REVIEW: tests passed; independent review by "
                f"{task.reviewer.value if task.reviewer else '?'} deferred (worktree preserved).",
                item.item_id,
            )
            return bl.WAITING_REVIEW

        if task.status is TaskStatus.PASS and worktree is not None:
            commit = self.commit_fn(
                worktree.path,
                task.changed_files,
                build_commit_message(item, task),
            )

            if commit.committed:
                self.backlog.update(
                    item.item_id, status=bl.PASSED, commit=commit.sha, **common
                )
                self.notify(
                    "info",
                    f"PASS; committed {commit.sha[:10]} on {commit.branch} "
                    "(not merged).",
                    item.item_id,
                )
            else:
                common["result_note"] = f"PASS but NOT committed: {commit.reason}"
                self.backlog.update(item.item_id, status=bl.PASSED, **common)
                self.notify("attention", common["result_note"], item.item_id)

            return bl.PASSED

        if task.status is TaskStatus.NEEDS_HUMAN:
            self.backlog.update(item.item_id, status=bl.NEEDS_HUMAN, **common)
            self.notify(
                "attention",
                f"NEEDS_HUMAN: {common['result_note']}",
                item.item_id,
            )
            return bl.NEEDS_HUMAN

        self.backlog.update(item.item_id, status=bl.BLOCKED, **common)
        self.notify(
            "attention",
            f"{task.status.value.upper()}: {common['result_note']}",
            item.item_id,
        )
        return bl.BLOCKED

    def can_resume_review(self, item: BacklogItem, *, allow_emergency: bool = False) -> bool:
        """Whether the item's reviewer provider may be spent right now (calls nothing)."""

        reviewer = Provider(item.awaiting_reviewer) if item.awaiting_reviewer else None

        if reviewer is None:
            return True

        if not self.quota.available(reviewer):
            return False

        return allow_emergency or self.quota.band(reviewer) is not QuotaBand.EMERGENCY

    def resume_review_item(self, item: BacklogItem, *, allow_emergency: bool = False) -> str | None:
        """Run one deferred independent review; None if the reviewer is still unaffordable.

        The EMERGENCY provider is only spent when the owner explicitly allows it. A provider
        that is EXHAUSTED is never called. The worktree is re-opened, verified unchanged,
        re-tested, reviewed, and only then committed (PASS) - see ExecutionCycle.resume_review.
        """

        if not self.can_resume_review(item, allow_emergency=allow_emergency):
            return None

        self.backlog.update(item.item_id, status=bl.RUNNING)

        try:
            result = self.review_fn(
                self.repo_root,
                task_id=item.task_id,
                test_targets=item.test_targets,
                run_ci_gate=item.run_ci_gate,
                orchestrator=self.orchestrator,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed on anything
            return self._record_crash(item, exc)

        # keep the calls already spent on the implementation: the task carries the total
        return self._settle(item, result)

    def resume_reviews(
        self,
        *,
        allow_emergency: bool = False,
        max_items: int | None = None,
    ) -> list[tuple[str, str]]:
        """Run every affordable deferred review, most valuable (hardest) first."""

        waiting = [i for i in self.backlog.all() if i.status == bl.WAITING_REVIEW]
        waiting.sort(
            key=lambda i: difficulty_rank(Difficulty(i.effective_difficulty or i.difficulty)),
            reverse=True,
        )
        done: list[tuple[str, str]] = []

        for item in waiting:
            if max_items is not None and len(done) >= max_items:
                break

            if self.stop_path.exists():
                break

            outcome = self.resume_review_item(item, allow_emergency=allow_emergency)

            if outcome is not None:
                done.append((item.item_id, outcome))

        return done

    @staticmethod
    def actual_provider_calls(task: Any) -> int:
        """Provider invocations that actually happened for this task.

        Counted by the execution cycle at the moment of each real call
        (implementer, reviewer, fix), so an attempt that stopped before the
        reviewer was reached counts one call, not two. The run budget stays
        conservative separately: the supervisor pre-checks the worst case
        before starting a package and never counts fewer than actually ran.
        """

        return max(0, int(getattr(task, "provider_calls", 0) or 0))

    # A crash gives no task back, so what ran is unknown: count conservatively.
    CRASH_PROVIDER_CALLS = 2

    @staticmethod
    def _unavailable_marker(task: Any) -> Provider | None:
        prefix = "PROVIDER_UNAVAILABLE:"

        for note in getattr(task, "notes", []) or []:
            if isinstance(note, str) and note.startswith(prefix):
                try:
                    return Provider(note[len(prefix):].strip())
                except ValueError:
                    return None

        return None

    def integrate(
        self,
        run_tests_fn: Callable[[Path, list[str]], bool] | None = None,
    ) -> list[tuple[str, str]]:
        """Merge PASSED+committed items into the vector-integration branch."""

        stage = IntegrationStage(self.repo_root)
        pending = [
            i for i in self.backlog.all()
            if i.status == bl.PASSED and i.commit and not i.integration
        ]

        if not pending:
            return []

        report = stage.integrate(
            pending,
            run_tests_fn
            or (lambda wt, targets: CommandRunner(wt).run_pytest(targets).passed),
        )

        if report.stopped:
            self.notify("attention", f"Integration stopped: {report.stopped}")

        results: list[tuple[str, str]] = []

        for outcome in report.outcomes:
            self.backlog.update(
                outcome.item_id,
                integration=outcome.result,
                integrated_commit=outcome.commit,
            )
            results.append((outcome.item_id, outcome.result))

            if outcome.result == "merged":
                self.notify(
                    "info",
                    f"Integrated onto vector-integration ({(outcome.commit or '')[:10]}).",
                    outcome.item_id,
                )
            else:
                self.notify(
                    "attention",
                    f"Integration {outcome.result}: {outcome.detail}",
                    outcome.item_id,
                )

        return results

    def record_last_run(self, summary: RunSummary, integrated: list[tuple[str, str]]) -> None:
        (self.state_dir / "last_run.json").write_text(
            json.dumps(
                {
                    "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "processed": summary.processed,
                    "stopped_because": summary.stopped_because,
                    "integrated": integrated,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def status(self) -> dict[str, Any]:
        items = self.backlog.all()
        counts: dict[str, int] = {}

        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1

        return {
            "counts": counts,
            "today": self._count_today(),
            "daily_cap": self.config.daily_cap,
            "stopped": self.stop_path.exists(),
            "quota": {
                p.value: {
                    "level": e["level"],
                    "source": e.get("source"),
                    "reason": e.get("reason"),
                    "retry_after": e.get("retry_after"),
                }
                for p in Provider
                for e in (self.quota.entry(p),)
            },
            "bands": {p.value: self.quota.band(p).value for p in Provider},
            "hold": self.holding_reason(),
            "deferred": [
                (i.item_id, i.deferred_reason) for i in items if i.status == bl.DEFERRED
            ],
            "waiting_review": [
                (i.item_id, i.awaiting_reviewer, i.effective_difficulty) for i in items
                if i.status == bl.WAITING_REVIEW
            ],
            "needs_attention": [
                (i.item_id, i.status, i.result_note)
                for i in items
                if i.status in (bl.BLOCKED, bl.NEEDS_HUMAN, bl.CRASHED)
                or (i.status == bl.PASSED and not i.commit)
            ],
            "branches_to_review": [
                (i.item_id, i.branch, (i.commit or "")[:10])
                for i in items
                if i.status == bl.PASSED and i.commit
            ],
            "integration": IntegrationStage(self.repo_root).summary(),
            "integration_flags": [
                (i.item_id, i.integration)
                for i in items
                if i.integration in ("conflict", "tests_failed")
            ],
        }


# --- CLI --------------------------------------------------------------


def _default_worker(repo_root: str | None) -> AutonomousWorker:
    here = Path(__file__).resolve().parent
    root = Path(repo_root) if repo_root else here.parents[1]
    return AutonomousWorker(
        root,
        here / ".state" / "worker",
        config=WorkerConfig(refresh_quota_telemetry=True),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autonomous_worker.py")
    parser.add_argument("--repo-root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add")
    add.add_argument("--description", required=True)
    add.add_argument("--test", action="append", dest="tests", required=True)
    add.add_argument(
        "--difficulty", default="routine",
        choices=[d.value for d in Difficulty],
    )
    add.add_argument("--title", default="")
    add.add_argument("--max-retries", type=int, default=1)
    add.add_argument("--run-ci-gate", action="store_true")
    add.add_argument(
        "--task-category", default=None,
        choices=[c.value for c in TaskCategory],
    )
    add.add_argument(
        "--urgency", type=float, default=None,
        help="Optional 0.0-1.0 urgency rating, logged for future Laya "
        "training but not used for scheduling.",
    )

    run = sub.add_parser("run")
    run.add_argument("--max-tasks", type=int, default=None)
    run.add_argument("--daily-cap", type=int, default=None)
    run.add_argument(
        "--integrate", action="store_true",
        help="After the run, merge passed branches into vector-integration.",
    )
    sub.add_parser("integrate")

    quota = sub.add_parser("quota", help="Show or set provider quota levels.")
    quota_sub = quota.add_subparsers(dest="quota_command", required=True)
    quota_sub.add_parser("show")
    quota_sub.add_parser("refresh", help="Read real Codex telemetry into the board.")
    q_set = quota_sub.add_parser(
        "set",
        help="Pass a LEVEL/band, or --remaining N for a plain owner-reported percentage.",
    )
    q_set.add_argument("provider", choices=[p.value for p in Provider])
    q_set.add_argument(
        "level",
        nargs="?",
        default=None,
        choices=[q.value for q in ProviderQuota] + ["conserve", "reserve", "emergency"],
        help="availability level, or a POLICY.md quota band (conserve/reserve/emergency); "
        "omit this and pass --remaining instead for a plain percentage",
    )
    q_set.add_argument(
        "--remaining",
        type=float,
        default=None,
        help="owner-reported remaining quota, 0-100 (e.g. --remaining 72 for '28%% used'); "
        "the POLICY.md band/level are derived from this exact percentage, not typed by hand",
    )
    q_set.add_argument("--reason", default="set by owner")
    q_clear = quota_sub.add_parser("clear")
    q_clear.add_argument("provider", choices=[p.value for p in Provider])

    for name in ("status", "stop", "resume"):
        sub.add_parser(name)

    requeue = sub.add_parser("requeue")
    requeue.add_argument("item_id")

    resume_reviews = sub.add_parser(
        "resume-reviews",
        help="Run deferred independent reviews (WAITING_REVIEW) whose reviewer is affordable.",
    )
    resume_reviews.add_argument(
        "--allow-emergency", action="store_true",
        help="Owner override: spend an EMERGENCY reviewer provider on these reviews.",
    )
    resume_reviews.add_argument("--max", type=int, default=None, dest="max_items")

    supersede = sub.add_parser(
        "supersede",
        help="Retire a PENDING/DEFERRED item whose work was delivered by another accepted item.",
    )
    supersede.add_argument("item_id")
    supersede.add_argument("--by", required=True, help="What delivered it (item id / commit / program).")

    close_manual = sub.add_parser(
        "close-manual",
        help="OWNER-RUN ONLY. Record a needs_human/blocked item as completed via directly-"
        "supervised manual work done outside the bridge, with explicit owner sign-off already "
        "given elsewhere (e.g. chat). Never invoke this from an autonomous task.",
    )
    close_manual.add_argument("item_id")
    close_manual.add_argument(
        "--commit", required=True,
        help="The real, already-merged commit sha delivering this item's work.",
    )
    close_manual.add_argument(
        "--note", required=True,
        help="What was actually done, and where the owner's approval for THIS item is recorded.",
    )
    close_manual.add_argument(
        "--owner-approved", required=True, choices=["yes"],
        help="Must be exactly 'yes'. This flag does not itself grant approval -- it records that "
        "a human already gave it; the invoker is responsible for that being true.",
    )

    args = parser.parse_args(argv)
    worker = _default_worker(args.repo_root)

    if args.command == "add":
        item = worker.backlog.add(
            description=args.description,
            test_targets=args.tests,
            difficulty=args.difficulty,
            max_retries=args.max_retries,
            run_ci_gate=args.run_ci_gate,
            task_category=args.task_category,
            title=args.title,
            urgency=args.urgency,
        )
        print(f"queued {item.item_id}")
        return 0

    if args.command == "integrate":
        print(json.dumps(worker.integrate(), indent=2))
        return 0

    if args.command == "quota":
        if args.quota_command == "refresh":
            worker.quota.refresh_from_telemetry()
        elif args.quota_command == "set":
            if (args.remaining is None) == (args.level is None):
                print("pass exactly one of LEVEL/band or --remaining PERCENT", file=sys.stderr)
                return 1

            if args.remaining is not None:
                if not 0.0 <= args.remaining <= 100.0:
                    print("--remaining must be 0-100", file=sys.stderr)
                    return 1

                band = quota_band_for_percent(args.remaining)
                worker.quota.set(
                    Provider(args.provider), BAND_LEVEL[band],
                    reason=args.reason or f"owner-reported: {args.remaining:.0f}% remaining",
                    source="owner", band=band, remaining_percent=args.remaining,
                )
            elif args.level in ("conserve", "reserve", "emergency"):
                worker.quota.set_band(
                    Provider(args.provider), QuotaBand(args.level),
                    reason=args.reason, source="owner",
                )
            else:
                worker.quota.set(
                    Provider(args.provider), ProviderQuota(args.level),
                    reason=args.reason, source="owner",
                )
        elif args.quota_command == "clear":
            worker.quota.clear(Provider(args.provider))

        print(json.dumps(worker.status()["quota"], indent=2))
        return 0

    if args.command == "run":
        if args.daily_cap is not None:
            worker.config.daily_cap = args.daily_cap
        summary = worker.run(args.max_tasks)
        integrated = worker.integrate() if args.integrate else []
        worker.record_last_run(summary, integrated)
        print(json.dumps(
            {
                "processed": summary.processed,
                "stopped_because": summary.stopped_because,
                "integrated": integrated,
            },
            indent=2,
        ))
        return 2 if "lock" in summary.stopped_because else (
            1 if summary.stopped_because in ("crash (fail closed)", "consecutive failures") else 0
        )

    if args.command == "status":
        print(json.dumps(worker.status(), indent=2))
        return 0

    if args.command == "stop":
        worker.stop_path.write_text("stop", encoding="utf-8")
        print("STOP file written; workers exit before the next task.")
        return 0

    if args.command == "resume":
        worker.stop_path.unlink(missing_ok=True)
        print("STOP file removed.")
        return 0

    if args.command == "resume-reviews":
        if not worker._acquire_lock():
            print("another worker holds the lock")
            return 2

        try:
            if worker.config.refresh_quota_telemetry:
                worker.quota.refresh_from_telemetry()

            results = worker.resume_reviews(
                allow_emergency=args.allow_emergency, max_items=args.max_items
            )
            integrated = worker.integrate() if results else []
        finally:
            worker._release_lock()

        print(json.dumps({"reviewed": results, "integrated": integrated}, indent=2))
        return 0

    if args.command == "supersede":
        item = worker.backlog.get(args.item_id)

        if item.status not in (bl.PENDING, bl.DEFERRED):
            print(f"Item is {item.status}; only pending/deferred items can be superseded.")
            return 1

        worker.backlog.update(
            args.item_id,
            status=bl.SUPERSEDED,
            result_note=f"SUPERSEDED: the same work was delivered by {args.by}.",
        )
        print(f"superseded {args.item_id} by {args.by}")
        return 0

    if args.command == "requeue":
        item = worker.backlog.get(args.item_id)

        if item.status not in (bl.BLOCKED, bl.NEEDS_HUMAN, bl.CRASHED):
            print(f"Item is {item.status}; only blocked/needs_human/crashed can be requeued.")
            return 1

        worker.backlog.update(args.item_id, status=bl.PENDING, result_note="Requeued by a human.")
        print(f"requeued {args.item_id} (approval-gated items will stop again unless reworded)")
        return 0

    if args.command == "close-manual":
        item = worker.backlog.get(args.item_id)

        if item.status not in (bl.NEEDS_HUMAN, bl.BLOCKED):
            print(
                f"Item is {item.status}; only needs_human/blocked items can be closed via "
                "close-manual."
            )
            return 1

        commit = args.commit.strip()
        note = args.note.strip()

        if not commit or not note:
            print("--commit and --note must both be real, non-empty text.")
            return 1

        worker.backlog.update(
            args.item_id,
            status=bl.PASSED,
            commit=commit,
            integration="manual",
            result_note=f"MANUAL COMPLETION (owner-approved, outside the bridge): {note}",
        )
        print(f"closed {args.item_id} as manually completed, commit {commit}")
        return 0

    return 1


# --- self-test --------------------------------------------------------


def _self_test() -> None:
    from dev_driver import DriverResult
    from models import DevTask, ModelChoice, Provider, TaskStage
    from worktree_manager import WorktreeInfo, WorktreeManager

    temp = Path(tempfile.mkdtemp(prefix="vector_worker_test_"))

    # Every backlog.add() call below logs to laya_log -- isolate the whole
    # self-test to a temp path, never the real default log, which is a
    # shared, persistent artifact this test must never write to.
    os.environ["VECTOR_LAYA_LOG_PATH"] = str(temp / "laya_decisions.jsonl")

    git = shutil.which("git")
    assert git

    def sh(cwd: Path, *args: str) -> str:
        proc = subprocess.run(
            [git, "-C", str(cwd), *args],
            capture_output=True, text=True, shell=False,
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout.strip()

    try:
        repo = temp / "repo"
        repo.mkdir()
        sh(repo, "init")
        sh(repo, "config", "user.email", "worker-test@example.invalid")
        sh(repo, "config", "user.name", "Worker Test")
        (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        sh(repo, "add", "tracked.txt")
        sh(repo, "commit", "-m", "base")
        base_head = sh(repo, "rev-parse", "HEAD")

        manager = WorktreeManager(repo, temp / "wts", git_executable=git)

        def make_task(status: TaskStatus, info: WorktreeInfo | None, changed: list[str]) -> DevTask:
            task = DevTask(description="Fake task.")
            task.task_id = info.task_id if info else "notask"
            task.status = status
            task.stage = TaskStage.COMPLETE
            task.changed_files = changed
            task.owner = Provider.CLAUDE
            task.reviewer = Provider.CODEX
            task.implementer_model = ModelChoice(Provider.CLAUDE, "haiku", "low")
            task.reviewer_model = ModelChoice(Provider.CODEX, "gpt-5.6-luna", "low")
            task.notes.append(f"final note {status.value}")
            return task

        def new_worker(
            name: str,
            fn: Callable[..., DriverResult],
            **config: Any,
        ) -> AutonomousWorker:
            return AutonomousWorker(
                repo, temp / f"state_{name}",
                config=WorkerConfig(**config), run_task_fn=fn, echo=False,
            )

        def add(worker: AutonomousWorker, text: str) -> BacklogItem:
            return worker.backlog.add(
                description=text, test_targets=["tests/t.py"],
                difficulty="scout", max_retries=0,
            )

        def notes(worker: AutonomousWorker) -> list[dict[str, Any]]:
            return [
                json.loads(line)
                for line in worker.notify_path.read_text(encoding="utf-8").splitlines()
            ]

        # 1. PASS -> committed on the task branch only; main untouched.
        info1 = manager.create("t1")
        (info1.path / "tracked.txt").write_text("changed by t1\n", encoding="utf-8")
        seen: dict[str, Any] = {}

        def pass_fn(root: Path, **kwargs: Any) -> DriverResult:
            seen.update(kwargs)
            return DriverResult(make_task(TaskStatus.PASS, info1, ["tracked.txt"]), info1)

        w1 = new_worker("pass", pass_fn, quota_state=QuotaState(codex_remaining_percent=20.0))
        item1 = add(w1, "First task")
        w1.backlog.update(
            item1.item_id, task_category="documentation", title="First task title"
        )
        summary = w1.run()
        done = w1.backlog.get(item1.item_id)

        assert summary.processed == [(item1.item_id, bl.PASSED)]
        assert done.status == bl.PASSED and done.commit
        assert done.branch == "vector-dev/t1"
        assert sh(repo, "rev-parse", "vector-dev/t1") == done.commit
        assert sh(repo, "rev-parse", "HEAD") == base_head, "main must not move"
        assert sh(info1.path, "show", "--name-only", "--format=", "HEAD") == "tracked.txt"
        assert "NOT merged" in sh(info1.path, "log", "-1", "--format=%B")
        assert notes(w1)[-1]["level"] == "info"
        # The spec reached run_task intact.
        assert seen["difficulty"] is Difficulty.SCOUT and seen["max_retries"] == 0
        assert seen["task_category"] is TaskCategory.DOCUMENTATION
        assert seen["quota_state"].codex_remaining_percent == 20.0
        assert w1.status()["branches_to_review"] == [(item1.item_id, "vector-dev/t1", done.commit[:10])]
        assert sh(info1.path, "log", "-1", "--format=%s") == "dev-orchestrator: First task title"

        # 1b. Integration: PASSED item is merged onto vector-integration only
        # after its targeted tests pass on the merged tree; live never moves.
        assert w1.integrate(run_tests_fn=lambda wt, targets: False) == [(item1.item_id, "tests_failed")]
        assert w1.backlog.get(item1.item_id).integration == "tests_failed"
        assert w1.integrate(run_tests_fn=lambda wt, targets: True) == [], "flagged items are not retried"
        w1.backlog.update(item1.item_id, integration="")
        merged = w1.integrate(run_tests_fn=lambda wt, targets: True)
        assert merged == [(item1.item_id, "merged")]
        assert w1.backlog.get(item1.item_id).integrated_commit
        live_branch = sh(repo, "rev-parse", "--abbrev-ref", "HEAD")
        assert sh(repo, "rev-parse", live_branch) == base_head, "live branch untouched"
        assert sh(repo, "show", "vector-integration:tracked.txt") == "changed by t1"
        assert w1.status()["integration"]["commits_ahead_of_live"] >= 2
        summary_run = RunSummary(processed=[(item1.item_id, bl.PASSED)])
        w1.record_last_run(summary_run, merged)
        assert json.loads((w1.state_dir / "last_run.json").read_text(encoding="utf-8"))["integrated"]

        # 2. Unexpected extra file -> PASS is recorded but nothing committed.
        info2 = manager.create("t2")
        (info2.path / "tracked.txt").write_text("changed by t2\n", encoding="utf-8")
        (info2.path / "stray.txt").write_text("unexpected\n", encoding="utf-8")
        w2 = new_worker(
            "stray",
            lambda root, **kw: DriverResult(make_task(TaskStatus.PASS, info2, ["tracked.txt"]), info2),
        )
        item2 = add(w2, "Stray file task")
        w2.run()
        stray = w2.backlog.get(item2.item_id)
        assert stray.status == bl.PASSED and stray.commit is None
        assert "NOT committed" in stray.result_note and "stray.txt" in stray.result_note
        assert sh(repo, "rev-parse", "vector-dev/t2") == base_head
        assert (info2.path / "stray.txt").exists(), "evidence untouched"
        assert notes(w2)[-1]["level"] == "attention"
        assert w2.status()["needs_attention"]

        # 3. Branch guard: refuses to commit on a non vector-dev branch.
        (repo / "tracked.txt").write_text("edited on main\n", encoding="utf-8")
        refused = commit_task_changes(repo, ["tracked.txt"], "msg")
        assert not refused.committed and "not a vector-dev/" in refused.reason
        assert sh(repo, "rev-parse", "HEAD") == base_head
        assert sh(repo, "diff", "--cached", "--name-only") == ""
        sh(repo, "checkout", "--", "tracked.txt")

        # Empty change list is refused.
        assert not commit_task_changes(info1.path, [], "m").committed

        # 4. BLOCKED x2 trips the circuit breaker; third item untouched.
        w4 = new_worker(
            "blocked",
            lambda root, **kw: DriverResult(make_task(TaskStatus.BLOCKED, None, []), None),
            max_consecutive_failures=2,
        )
        b1, b2, b3 = (add(w4, f"Blocked {n}") for n in "123")
        s4 = w4.run(max_tasks=10)
        assert s4.stopped_because == "consecutive failures"
        assert [w4.backlog.get(i.item_id).status for i in (b1, b2, b3)] == [
            bl.BLOCKED, bl.BLOCKED, bl.PENDING,
        ]

        # 5. NEEDS_HUMAN (approval gate) is not counted as a system failure.
        w5 = new_worker(
            "human",
            lambda root, **kw: DriverResult(make_task(TaskStatus.NEEDS_HUMAN, None, []), None),
            max_consecutive_failures=2, daily_cap=10,
        )
        for n in "123":
            add(w5, f"Needs human {n}")
        s5 = w5.run(max_tasks=10)
        assert len(s5.processed) == 3 and s5.stopped_because == "backlog empty"

        # 6. Crash: item marked crashed, loop stops, later item stays pending.
        def crash_fn(root: Path, **kw: Any) -> DriverResult:
            raise RuntimeError("provider exploded")

        w6 = new_worker("crash", crash_fn)
        c1, c2 = add(w6, "Crash 1"), add(w6, "Crash 2")
        s6 = w6.run(max_tasks=10)
        assert s6.stopped_because == "crash (fail closed)"
        assert w6.backlog.get(c1.item_id).status == bl.CRASHED
        assert w6.backlog.get(c2.item_id).status == bl.PENDING

        # 7. Daily cap, then rollover to the next day.
        day = {"value": "2026-01-01"}
        w7 = AutonomousWorker(
            repo, temp / "state_cap",
            config=WorkerConfig(daily_cap=2, max_consecutive_failures=99),
            run_task_fn=lambda root, **kw: DriverResult(make_task(TaskStatus.NEEDS_HUMAN, None, []), None),
            today_fn=lambda: day["value"], echo=False,
        )
        for n in "123":
            add(w7, f"Cap {n}")
        s7 = w7.run(max_tasks=10)
        assert len(s7.processed) == 2 and s7.stopped_because == "daily cap reached"
        assert w7.backlog.next_pending() is not None
        day["value"] = "2026-01-02"
        s7b = w7.run(max_tasks=10)
        assert len(s7b.processed) == 1 and w7.backlog.next_pending() is None

        # 8. STOP file halts before any work.
        w8 = new_worker("stop", crash_fn)
        add(w8, "Should not run")
        w8.stop_path.write_text("stop", encoding="utf-8")
        s8 = w8.run()
        assert s8.processed == [] and s8.stopped_because == "STOP file present"
        assert w8.backlog.next_pending() is not None

        # 9. Lock: a live lock blocks a second worker; a stale one is reclaimed.
        w9 = new_worker("lock", crash_fn)
        add(w9, "Locked out")
        assert w9._acquire_lock()
        s9 = w9.run()
        assert s9.processed == [] and "lock" in s9.stopped_because
        old = time.time() - (w9.config.lock_stale_seconds + 60)
        os.utime(w9.lock_path, (old, old))
        s9b = w9.run()  # reclaims stale lock, runs (and crashes -> fail closed)
        assert s9b.stopped_because == "crash (fail closed)"
        assert not w9.lock_path.exists(), "lock released afterwards"

        # 10. Item left RUNNING by a dead worker is never replayed.
        w10 = new_worker("recover", crash_fn)
        r1 = add(w10, "Interrupted")
        w10.backlog.update(r1.item_id, status=bl.RUNNING)
        s10 = w10.run()
        assert w10.backlog.get(r1.item_id).status == bl.NEEDS_HUMAN
        assert s10.processed == [] and notes(w10)[0]["level"] == "attention"

        # 10b. Program packages: spec + quota levels + preferred owner reach
        # run_task; they never consume (or are pulled by) the daily cap.
        pkg_seen: dict[str, Any] = {}

        def pkg_fn(root: Path, **kw: Any) -> DriverResult:
            pkg_seen.update(kw)
            task = make_task(TaskStatus.NEEDS_HUMAN, None, [])
            task.requested_difficulty = "routine"
            task.inferred_difficulty = "hard"
            task.difficulty_reason = "security floor"
            task.provider_calls = 2
            return DriverResult(task, None)

        w11 = new_worker("program", pkg_fn, daily_cap=1)
        w11.quota.set(Provider.CLAUDE, ProviderQuota.CONSTRAINED, reason="owner test", source="owner")
        pkg = w11.backlog.add(
            description="Package", test_targets=["tests/t.py"], difficulty="routine",
            program_id="prog1", package_id="p1", objective="Do the thing",
            allowed_paths=["core/"], acceptance_criteria=["it works"],
            preferred_owner="codex",
        )
        manual = add(w11, "Manual maintenance")
        s11 = w11.run(max_tasks=5)
        assert [i for i, _ in s11.processed] == [manual.item_id], "scheduled run skips program packages"
        assert w11._count_today() == 1
        assert w11.backlog.get(pkg.item_id).status == bl.PENDING
        assert w11.execute_item(w11.backlog.get(pkg.item_id)) == bl.NEEDS_HUMAN
        assert w11._count_today() == 1, "program package must not consume the daily cap"
        assert pkg_seen["spec"].allowed_paths == ("core/",)
        assert pkg_seen["spec"].program_id == "prog1"
        assert pkg_seen["spec"].acceptance_criteria == ("it works",)
        assert pkg_seen["previous_owner"] is Provider.CLAUDE, "preferred codex => claude was previous"
        assert pkg_seen["quota_levels"][Provider.CLAUDE] is ProviderQuota.CONSTRAINED
        assert pkg_seen["quota_levels"][Provider.CODEX] is ProviderQuota.UNKNOWN
        recorded = w11.backlog.get(pkg.item_id)
        assert (recorded.requested_difficulty, recorded.inferred_difficulty) == ("routine", "hard")
        assert recorded.difficulty_reason == "security floor" and recorded.provider_calls == 2

        # Failure evidence: categories separate test-spec errors from implementation failures.
        from models import ReviewFinding, ReviewSeverity, TestResult

        def failing(code: int, stdout: str = "", notes: list[str] | None = None) -> Any:
            task = make_task(TaskStatus.BLOCKED, None, [])
            task.tests = [TestResult(command="python -m pytest -q tests/t.py", exit_code=code,
                                     passed=False, stdout=stdout, stderr="")]
            task.notes.extend(notes or [])
            task.provider_calls = 1
            return task

        spec_item = w11.backlog.get(pkg.item_id)
        spec_item.allowed_paths = ["core/x.py", "tests/test_new.py"]
        usage_error = "ERROR: file or directory not found: tests/ -k uploader"
        ev = build_failure_evidence(spec_item, failing(4, usage_error))
        assert (ev["category"], ev["kind"], ev["exit_code"]) == ("test_spec", "test_spec", 4)
        assert "tests/ -k uploader" in ev["tail"]
        ev = build_failure_evidence(spec_item, failing(4, "ERROR: file or directory not found: tests/test_new.py"))
        assert (ev["category"], ev["kind"]) == ("test_file_missing", "implementation"), "deliverable not created"
        ev = build_failure_evidence(spec_item, failing(4, "ERROR: file or directory not found: tests/other.py"))
        assert ev["kind"] == "test_spec", "a missing file that is not a deliverable is a spec error"
        assert build_failure_evidence(spec_item, failing(1, "1 failed"))["category"] == "test_failure"
        assert build_failure_evidence(spec_item, failing(1, "1 failed"))["kind"] == "implementation"
        assert build_failure_evidence(spec_item, failing(5))["category"] == "no_tests_collected"
        assert build_failure_evidence(spec_item, failing(2))["category"] == "collection_error"
        assert build_failure_evidence(spec_item, failing(3))["kind"] == "infrastructure"
        assert build_failure_evidence(spec_item, failing(-1))["kind"] == "infrastructure"

        # bounded and redacted
        noisy = "x" * 50000 + " token sk-abcdefghijklmnopqrstuvwxyz0123456789 end"
        big = build_failure_evidence(spec_item, failing(1, noisy))
        assert len(big["tail"]) <= 1300 and "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in big["tail"]
        secret_only = build_failure_evidence(
            spec_item, failing(1, "Bearer abcdefghijklmnopqrstuvwxyz012345 leaked"))
        assert "abcdefghijklmnopqrstuvwxyz012345" not in secret_only["tail"]

        rejected = make_task(TaskStatus.BLOCKED, None, [])
        rejected.review_findings = [ReviewFinding(ReviewSeverity.BLOCKER, "handles None wrongly")]
        rejected.tests = [TestResult(command="pytest", exit_code=0, passed=True)]
        ev = build_failure_evidence(spec_item, rejected)
        assert ev["category"] == "review_rejected" and "handles None wrongly" in ev["findings"][0]
        leaky = make_task(TaskStatus.BLOCKED, None, [])
        leaky.review_findings = [
            ReviewFinding(ReviewSeverity.BLOCKER, "hardcoded key sk-abcdefghijklmnopqrstuvwxyz0123456789 in config")
        ]
        leaky.tests = [TestResult(command="pytest", exit_code=0, passed=True)]
        leak_ev = build_failure_evidence(spec_item, leaky)
        assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in json.dumps(leak_ev), "findings are redacted"
        assert "[REDACTED]" in leak_ev["findings"][0]
        scoped = make_task(TaskStatus.BLOCKED, None, [])
        scoped.notes.append("SCOPE VIOLATION: files changed outside allowed paths")
        assert build_failure_evidence(spec_item, scoped)["category"] == "scope_violation"
        assert w11.status()["quota"]["codex"]["level"] == "unknown"

        # 10c. Exhausted provider: nothing runs, state preserved, no substitution.
        ran: list[str] = []

        def spy_fn(root: Path, **kw: Any) -> DriverResult:
            ran.append("ran")
            return DriverResult(make_task(TaskStatus.NEEDS_HUMAN, None, []), None)

        w12 = new_worker("exhausted", spy_fn)
        w12.quota.set(Provider.CODEX, ProviderQuota.EXHAUSTED, reason="owner test", source="owner")
        held = add(w12, "Held while codex is out")
        s12 = w12.run()
        assert s12.processed == [] and ran == []
        assert "provider unavailable: codex" in s12.stopped_because
        assert w12.backlog.get(held.item_id).status == bl.PENDING
        deferred_pkg = w12.backlog.add(
            description="Pkg", test_targets=["tests/t.py"], program_id="p", package_id="a"
        )
        assert w12.execute_item(deferred_pkg) == bl.DEFERRED and ran == []
        assert w12.backlog.get(deferred_pkg.item_id).status == bl.DEFERRED
        assert w12.status()["deferred"]
        w12.quota.clear(Provider.CODEX)
        assert w12.reactivate_deferred() == [deferred_pkg.item_id]
        assert w12.backlog.get(deferred_pkg.item_id).status == bl.PENDING

        # 10d. A provider stopping mid-task defers (not a failure) and marks the board.
        def exhausted_fn(root: Path, **kw: Any) -> DriverResult:
            task = make_task(TaskStatus.BLOCKED, None, [])
            task.notes.append("PROVIDER_UNAVAILABLE:claude")
            return DriverResult(task, None)

        w13 = new_worker("midtask", exhausted_fn, max_consecutive_failures=1)
        mid1, mid2 = add(w13, "Mid 1"), add(w13, "Mid 2")
        s13 = w13.run(max_tasks=5)
        assert s13.processed == [(mid1.item_id, bl.DEFERRED)]
        assert "deferred" in s13.stopped_because and "consecutive" not in s13.stopped_because
        assert w13.backlog.get(mid1.item_id).status == bl.DEFERRED
        assert w13.backlog.get(mid2.item_id).status == bl.PENDING
        assert w13.quota.level(Provider.CLAUDE) is ProviderQuota.EXHAUSTED
        assert w13.quota.entry(Provider.CLAUDE)["source"] == "error"

        # 10e. A superseded item is terminal and inert: never run, requeued or flagged.
        w14 = new_worker("superseded", crash_fn)
        dup = add(w14, "Duplicate of work already delivered")
        w14.backlog.update(dup.item_id, status=bl.SUPERSEDED, result_note="SUPERSEDED: by prog-x")
        assert w14.backlog.next_pending() is None and w14.backlog.get(dup.item_id).is_terminal()
        assert w14.run().processed == [] and w14.status()["needs_attention"] == []

        # 10e2. Regression (found by a real live run): run_task_fn and review_fn must receive
        # the exact SAME orchestrator -- not each independently build its own default from
        # bare repo_root, which only happens to coincide with the real state layout in
        # production and silently splits implement/review onto two different task stores
        # anywhere else (a sandbox, a test, a --repo-root override). A custom, non-default
        # orchestrator/state_root here would have hidden that bug; assert identity instead.
        from orchestrator import DevOrchestrator as _DevOrchestrator

        seen_orch: dict[str, Any] = {}

        def capture_impl(root: Path, **kw: Any) -> DriverResult:
            seen_orch["implement"] = kw.get("orchestrator")
            return DriverResult(make_task(TaskStatus.NEEDS_HUMAN, None, []), None)

        def capture_review(root: Path, **kw: Any) -> DriverResult:
            seen_orch["review"] = kw.get("orchestrator")
            return DriverResult(make_task(TaskStatus.NEEDS_HUMAN, None, []), None)

        custom_orch = _DevOrchestrator(repo, temp / "custom_orch_state")
        w_orch = AutonomousWorker(
            repo, temp / "state_orch_identity",
            run_task_fn=capture_impl, review_fn=capture_review, orchestrator=custom_orch, echo=False,
        )
        assert w_orch.orchestrator is custom_orch
        probe = add(w_orch, "Orchestrator identity probe")
        w_orch._process(probe)
        assert seen_orch["implement"] is custom_orch, "run_task_fn did not receive the worker's orchestrator"
        w_orch.backlog.update(probe.item_id, status=bl.WAITING_REVIEW, awaiting_reviewer="codex")
        w_orch.resume_review_item(w_orch.backlog.get(probe.item_id))
        assert seen_orch["review"] is custom_orch, "review_fn did not receive the worker's orchestrator"
        assert seen_orch["implement"] is seen_orch["review"], "implement and review used different orchestrators"

        # A worker built with no explicit orchestrator still defaults sensibly (production path).
        w_default_orch = new_worker("default_orch", crash_fn)
        assert isinstance(w_default_orch.orchestrator, _DevOrchestrator)
        assert w_default_orch.orchestrator.repo_root == repo.resolve()

        # 10f. POLICY.md sec. 9-10: reviewer provider in EMERGENCY -> the other provider implements,
        # the independent review is deferred (WAITING_REVIEW, never PASS) and resumed later.
        from types import SimpleNamespace

        import itertools

        task_counter = itertools.count(1)
        seen_w: dict[str, Any] = {}
        review_calls: list[str] = []
        shim = SimpleNamespace(path=temp, branch_name="vector-dev/w1")

        def waiting_fn(root: Path, **kw: Any) -> DriverResult:
            seen_w.update(kw)
            task = make_task(TaskStatus.WAITING_REVIEW, None, ["tracked.txt"])
            task.task_id = f"wt{next(task_counter)}"
            task.provider_calls = 1
            task.difficulty = Difficulty.HARD if "hard" in kw["description"] else Difficulty.ROUTINE
            return DriverResult(task, shim)

        def review_fn(root: Path, **kw: Any) -> DriverResult:
            review_calls.append(kw["task_id"])
            task = make_task(TaskStatus.PASS, None, ["tracked.txt"])
            task.task_id = kw["task_id"]
            task.provider_calls = 2
            return DriverResult(task, shim)

        w15 = AutonomousWorker(
            repo, temp / "state_waiting",
            config=WorkerConfig(daily_cap=20, max_tasks_per_run=5),
            run_task_fn=waiting_fn, review_fn=review_fn,
            commit_fn=lambda wt, files, msg: CommitResult(True, sha="c" * 40, branch="vector-dev/w1"),
            echo=False,
        )
        w15.quota.set_band(Provider.CODEX, QuotaBand.EMERGENCY, reason="owner: ~1% weekly", source="owner")
        easy = add(w15, "Ordinary work while codex is low")
        hard = add(w15, "A hard problem while codex is low")
        run15 = w15.run(max_tasks=5)
        assert seen_w["quota_bands"][Provider.CODEX] is QuotaBand.EMERGENCY
        assert seen_w["quota_bands"][Provider.CLAUDE] is QuotaBand.UNKNOWN
        assert [o for _, o in run15.processed] == [bl.WAITING_REVIEW, bl.WAITING_REVIEW]
        assert run15.stopped_because == "backlog empty", "waiting-for-review is not a failure"
        assert w15.holding_reason() is None, "one provider in EMERGENCY is not a hold"
        waiting_items = [w15.backlog.get(i.item_id) for i in (easy, hard)]
        assert all(i.status == bl.WAITING_REVIEW and i.awaiting_reviewer == "codex" and not i.commit for i in waiting_items)
        assert all(i.provider_calls == 1 and not i.failure_evidence for i in waiting_items)
        assert not w15.backlog.get(easy.item_id).is_terminal()
        assert w15.status()["needs_attention"] == [] and len(w15.status()["waiting_review"]) == 2
        assert w15.status()["bands"] == {"codex": "emergency", "claude": "unknown"}
        assert w15.integrate(run_tests_fn=lambda wt, targets: True) == [], "unreviewed work is never integrated"

        # Still EMERGENCY (no owner override): no review, nothing spent, still waiting.
        assert w15.resume_reviews() == [] and review_calls == []
        # An EXHAUSTED reviewer is never called, even with the owner override.
        w15.quota.set(Provider.CODEX, ProviderQuota.EXHAUSTED, reason="owner", source="owner")
        assert w15.resume_reviews(allow_emergency=True) == [] and review_calls == []
        w15.quota.set_band(Provider.CODEX, QuotaBand.EMERGENCY, reason="owner: ~1% weekly", source="owner")
        # Owner explicitly spends the emergency reserve: hardest first, bounded by --max.
        first_done = w15.resume_reviews(allow_emergency=True, max_items=1)
        assert first_done == [(hard.item_id, bl.PASSED)] and len(review_calls) == 1
        assert w15.backlog.get(hard.item_id).commit == "c" * 40
        assert w15.backlog.get(easy.item_id).status == bl.WAITING_REVIEW

        # Codex recovers (band cleared): the scheduled run resumes the rest by itself.
        w15.quota.clear(Provider.CODEX)
        auto = w15.run(max_tasks=5)
        assert auto.resumed == [(easy.item_id, bl.PASSED)] and len(review_calls) == 2
        assert auto.processed == [] and w15.backlog.get(easy.item_id).status == bl.PASSED

        # A crash while resuming a review fails closed (recorded, worker told to stop).
        def boom_review(root: Path, **kw: Any) -> DriverResult:
            raise RuntimeError("review exploded")

        w16 = AutonomousWorker(
            repo, temp / "state_waiting_boom", config=WorkerConfig(daily_cap=20),
            run_task_fn=waiting_fn, review_fn=boom_review, echo=False,
        )
        w16.quota.set_band(Provider.CODEX, QuotaBand.EMERGENCY, reason="owner", source="owner")
        stuck = add(w16, "Waiting then crashing")
        w16.run(max_tasks=1)
        w16.quota.clear(Provider.CODEX)
        assert w16.resume_reviews() == [(stuck.item_id, bl.CRASHED)]
        assert w16.backlog.get(stuck.item_id).status == bl.CRASHED

        # BOTH providers in EMERGENCY: nobody can implement -> hold, nothing runs.
        w17 = new_worker("both_emergency", crash_fn)
        for provider in Provider:
            w17.quota.set_band(provider, QuotaBand.EMERGENCY, reason="owner", source="owner")
        add(w17, "Nobody can implement this right now")
        held_run = w17.run()
        assert held_run.processed == [] and "both providers are in quota EMERGENCY" in held_run.stopped_because
        assert w17.holding_reason() == "both providers are in quota EMERGENCY"

        # Claude in EMERGENCY, Codex healthy: mirror image - no hold, Codex-first.
        w18 = new_worker("claude_low", crash_fn)
        w18.quota.set_band(Provider.CLAUDE, QuotaBand.EMERGENCY, reason="owner", source="owner")
        assert w18.holding_reason() is None

        # 10g. `quota set PROVIDER --remaining N` (a plain owner-reported percentage, e.g.
        # "28% used") derives the exact POLICY.md band/level rather than being typed by hand.
        # main()'s CLI always writes to the real tool-dir .state/worker (there is no
        # --state-dir override), which is the LIVE bridge's own quota board -- back it up
        # and restore it so this self-test never disturbs real owner-set quota state.
        real_quota_path = Path(__file__).resolve().parent / ".state" / "worker" / "quota.json"
        real_quota_backup = (
            real_quota_path.read_bytes() if real_quota_path.exists() else None
        )

        try:
            assert main([
                "--repo-root", str(repo),
                "quota", "set", "claude", "--remaining", "72", "--reason", "owner-reported 28% used",
            ]) == 0
            w19 = _default_worker(str(repo))
            assert w19.quota.band(Provider.CLAUDE) is QuotaBand.NORMAL
            assert w19.quota.level(Provider.CLAUDE) is ProviderQuota.NORMAL
            assert w19.quota.remaining_percent(Provider.CLAUDE) == 72.0
            assert w19.quota.entry(Provider.CLAUDE)["reason"] == "owner-reported 28% used"

            assert main(["--repo-root", str(repo), "quota", "set", "codex", "--remaining", "8"]) == 0
            assert w19.quota.band(Provider.CODEX) is QuotaBand.EMERGENCY

            # Exactly one of LEVEL or --remaining is required; both or neither is refused.
            assert main(["--repo-root", str(repo), "quota", "set", "claude", "normal", "--remaining", "50"]) == 1
            assert main(["--repo-root", str(repo), "quota", "set", "claude"]) == 1
            assert main(["--repo-root", str(repo), "quota", "set", "claude", "--remaining", "150"]) == 1
        finally:
            if real_quota_backup is None:
                real_quota_path.unlink(missing_ok=True)
            else:
                real_quota_path.write_bytes(real_quota_backup)

        # 10h. close-manual: OWNER-RUN CLI verb recording a needs_human/blocked item as
        # completed via directly-supervised manual work done outside the bridge. Like the
        # quota test above, main()'s CLI always binds to the real tool-dir .state/worker
        # backlog (there is no --state-dir override) -- back it up and restore it so this
        # self-test never disturbs real backlog history.
        real_backlog_path = Path(__file__).resolve().parent / ".state" / "worker" / "backlog.json"
        real_backlog_backup = (
            real_backlog_path.read_bytes() if real_backlog_path.exists() else None
        )

        try:
            cm_worker = _default_worker(str(repo))
            item20 = cm_worker.backlog.add(
                description="Manually completed elsewhere", test_targets=["tests/t.py"],
                difficulty="scout", max_retries=0,
            )
            cm_worker.backlog.update(item20.item_id, status=bl.NEEDS_HUMAN)

            pending20 = cm_worker.backlog.add(
                description="Still pending", test_targets=["tests/t.py"],
                difficulty="scout", max_retries=0,
            )

            # Wrong status (still pending) is refused, item left untouched.
            assert main([
                "--repo-root", str(repo), "close-manual", pending20.item_id,
                "--commit", "deadbeef", "--note", "x", "--owner-approved", "yes",
            ]) == 1
            assert cm_worker.backlog.get(pending20.item_id).status == bl.PENDING

            # Blank --commit is refused, item left untouched.
            assert main([
                "--repo-root", str(repo), "close-manual", item20.item_id,
                "--commit", "   ", "--note", "did the work", "--owner-approved", "yes",
            ]) == 1
            assert cm_worker.backlog.get(item20.item_id).status == bl.NEEDS_HUMAN

            # A real close-manual call succeeds and records evidence.
            assert main([
                "--repo-root", str(repo), "close-manual", item20.item_id,
                "--commit", "cafef00d",
                "--note", "Built by Codex, verified+merged by Claude, owner approved in chat.",
                "--owner-approved", "yes",
            ]) == 0
            closed20 = cm_worker.backlog.get(item20.item_id)
            assert closed20.status == bl.PASSED
            assert closed20.commit == "cafef00d"
            assert closed20.integration == "manual"
            assert "MANUAL COMPLETION" in closed20.result_note

            # BLOCKED items are eligible too, not only NEEDS_HUMAN.
            item20b = cm_worker.backlog.add(
                description="Blocked, then fixed manually", test_targets=["tests/t.py"],
                difficulty="scout", max_retries=0,
            )
            cm_worker.backlog.update(item20b.item_id, status=bl.BLOCKED)
            assert main([
                "--repo-root", str(repo), "close-manual", item20b.item_id,
                "--commit", "f00dcafe", "--note", "fixed", "--owner-approved", "yes",
            ]) == 0
            assert cm_worker.backlog.get(item20b.item_id).status == bl.PASSED

            # --owner-approved is a closed choice set: anything but the literal
            # "yes" is refused by argparse itself, before the handler ever runs.
            try:
                main([
                    "--repo-root", str(repo), "close-manual", item20b.item_id,
                    "--commit", "x", "--note", "x", "--owner-approved", "definitely-not",
                ])
            except SystemExit as exc:
                assert exc.code != 0
            else:
                raise AssertionError("--owner-approved must reject anything but 'yes'")
        finally:
            if real_backlog_backup is None:
                real_backlog_path.unlink(missing_ok=True)
            else:
                real_backlog_path.write_bytes(real_backlog_backup)

        # 11. Evidence is never deleted by anything above.
        for name in ("t1", "t2"):
            assert (temp / "wts" / name).exists()
    finally:
        os.environ.pop("VECTOR_LAYA_LOG_PATH", None)
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(main())
    _self_test()
