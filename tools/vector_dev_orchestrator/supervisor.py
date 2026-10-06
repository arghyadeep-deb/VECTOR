"""Autonomous supervisor: runs an owner-started PROGRAM to completion.

A program is a goal decomposed by the planner into small work packages. The
supervisor executes them one at a time through the existing worker/bridge
(routing -> worktree -> implement -> tests -> independent cross-provider
review -> bounded fix), keeps an accepted-evidence ledger, and continues
until the program completes or something genuinely needs the owner.

Budgets are separate from scheduled maintenance:
  * the scheduled worker has a DAILY task cap and never touches program
    packages (backlog `next_pending(manual_only=True)`);
  * an owner-started program has its own RunBudget (max work packages, max
    provider calls, max correction cycles, max elapsed time) and its
    packages never consume the daily cap.

Continuation is bounded:
  accepted package  -> ledger updated -> next dependency-ready package
  blocked package   -> at most ONE correction (fresh attempt that is shown
                       what blocked the last one) -> retest -> re-review
  correction fails  -> one bounded RE-PLAN (planner sees the blocker) ->
                       otherwise the program stops for the owner
No infinite repair loops: corrections and re-plans are both capped.

Autonomy stops (program -> needs_human) for: destructive owner-data
operations, credential/API-key changes, spending, publishing/pushing,
irreversible external actions, major product-scope decisions, unresolved
high-impact security trade-offs, architecture replacement. Packages are
screened by approval.py before anything is queued.

Everything is persisted atomically under <state_dir>/programs/. After a
crash/restart nothing is replayed blindly: a package interrupted mid-run
becomes needs_human, a package whose backlog item already finished is
reconciled from that item, completed packages/programs are never rerun and
paused programs stay paused.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import backlog as bl
from autonomous_worker import AutonomousWorker, _bounded
from integration import INTEGRATION_BRANCH
from models import Provider
from planner import (
    BlockerRecord,
    LedgerEntry,
    Plan,
    Planner,
    PlannerError,
    PlanningInput,
    WorkPackage,
    fingerprint_text,
)
from text_signals import safe_state_id

# program statuses
ACTIVE = "active"
PAUSED = "paused"
COMPLETED = "completed"
STOPPED = "stopped"
NEEDS_HUMAN = "needs_human"
BUDGET_EXHAUSTED = "budget_exhausted"
# Every runnable package is done or blocked behind work whose independent review is
# deferred (reviewer provider in quota EMERGENCY). Never "completed".
WAITING_REVIEW = "waiting_review"

_RESUMABLE = {PAUSED, NEEDS_HUMAN, BUDGET_EXHAUSTED, WAITING_REVIEW}
_FINAL = {COMPLETED, STOPPED}

# package states
P_PLANNED = "planned"
P_RUNNING = "running"
P_ACCEPTED = "accepted"
P_FAILED = "failed"
P_NEEDS_HUMAN = "needs_human"
P_SKIPPED = "skipped"
P_WAITING_REVIEW = "waiting_review"

_UNSATISFIABLE = {P_FAILED, P_NEEDS_HUMAN, P_SKIPPED}


class SupervisorError(RuntimeError):
    """An owner/operator request the supervisor refuses."""


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- data --------------------------------------------------------------


@dataclass(slots=True)
class RunBudget:
    max_packages: int = 6
    max_provider_calls: int = 40
    max_correction_cycles: int = 4
    max_elapsed_seconds: float = 6 * 3600.0


@dataclass(slots=True)
class Usage:
    packages_started: int = 0
    provider_calls: int = 0
    correction_cycles: int = 0
    replans: int = 0
    elapsed_seconds: float = 0.0


@dataclass(slots=True)
class PackageState:
    package: dict[str, Any]
    state: str = P_PLANNED
    item_id: str | None = None
    corrections: int = 0
    last_fingerprint: str = ""
    note: str = ""
    commit: str = ""
    started: bool = False
    # provider calls of the current item already added to the program's usage
    calls_counted: int = 0

    @property
    def package_id(self) -> str:
        return str(self.package["package_id"])

    @property
    def title(self) -> str:
        return str(self.package["title"])

    def work_package(self) -> WorkPackage:
        raw = dict(self.package)

        for key in (
            "allowed_paths", "forbidden_scope", "acceptance_criteria", "test_targets",
            "behavioral_evidence", "dependencies", "stop_conditions", "owner_reasons",
        ):
            raw[key] = tuple(raw.get(key, ()))

        return WorkPackage(**raw)


@dataclass(slots=True)
class Program:
    program_id: str
    goal: str
    status: str = ACTIVE
    status_reason: str = ""
    budget: RunBudget = field(default_factory=RunBudget)
    usage: Usage = field(default_factory=Usage)
    packages: list[PackageState] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    blockers: dict[str, dict[str, Any]] = field(default_factory=dict)
    max_replans: int = 1
    # Set once accepted work is on vector-integration: later packages build on it.
    base_ref: str = ""
    created_at: str = field(default_factory=_iso)
    updated_at: str = field(default_factory=_iso)

    def package(self, package_id: str) -> PackageState:
        for pkg in self.packages:
            if pkg.package_id == package_id:
                return pkg
        raise SupervisorError(f"Unknown package {package_id!r} in {self.program_id}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Program":
        data = dict(raw)
        data["budget"] = RunBudget(**data.get("budget", {}))
        data["usage"] = Usage(**data.get("usage", {}))
        data["packages"] = [PackageState(**p) for p in data.get("packages", [])]
        return cls(**data)


@dataclass(slots=True)
class RunReport:
    program_id: str
    executed: list[tuple[str, str]] = field(default_factory=list)  # (package_id, outcome)
    stopped_because: str = ""
    status: str = ""


# --- supervisor --------------------------------------------------------


_ID_NOISE = re.compile(r"\b[0-9a-f]{8,}\b|\d+")


def _blocker_fingerprint(note: str) -> str:
    return fingerprint_text(_ID_NOISE.sub(" ", note or ""))


class Supervisor:
    def __init__(
        self,
        repo_root: Path,
        state_dir: Path,
        worker: AutonomousWorker,
        planner: Planner | None = None,
        *,
        now_fn: Callable[[], float] = time.time,
        integrate_fn: Callable[[], list[tuple[str, str]]] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.state_dir = Path(state_dir)
        self.dir = self.state_dir / "programs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.worker = worker
        self.planner = planner
        self.now_fn = now_fn
        # After every accepted package its branch is merged (tests re-run on the
        # merged tree) into vector-integration so dependent packages build on it.
        self.integrate_fn = integrate_fn or worker.integrate
        # Owner override: spend an EMERGENCY reviewer provider on deferred reviews.
        self.allow_emergency_review = False

    # --- persistence ---------------------------------------------------

    def _path(self, program_id: str) -> Path:
        return self.dir / f"{safe_state_id(program_id, field='program_id')}.json"

    def _control_path(self, program_id: str) -> Path:
        return self.dir / f"{safe_state_id(program_id, field='program_id')}.control"

    def save(self, program: Program) -> None:
        program.updated_at = _iso()
        path = self._path(program.program_id)
        fd, temp_name = tempfile.mkstemp(prefix="program.", suffix=".tmp", dir=self.dir, text=True)

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(program.to_dict(), handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())

            Path(temp_name).replace(path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def load(self, program_id: str) -> Program:
        path = self._path(program_id)

        if not path.exists():
            raise SupervisorError(f"Unknown program {program_id!r}")

        try:
            return Program.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise SupervisorError(
                f"Program file is corrupt and will not be overwritten: {path}"
            ) from exc

    def list_programs(self) -> list[Program]:
        return [self.load(p.stem) for p in sorted(self.dir.glob("*.json"))]

    # --- planning ------------------------------------------------------

    def _planning_input(self, program: Program, *, max_packages: int) -> PlanningInput:
        # Planning may spend at most what is left of the provider-call budget
        # (never more than 2: one proposal + one repair round).
        left = program.budget.max_provider_calls - program.usage.provider_calls

        return PlanningInput(
            max_calls=max(1, min(2, left)),
            goal=program.goal,
            ledger=[LedgerEntry(**e) for e in program.ledger],
            blockers=[
                BlockerRecord(
                    fp, b["description"], int(b.get("count", 1)), str(b.get("evidence", ""))
                )
                for fp, b in program.blockers.items()
            ],
            max_packages=max_packages,
        )

    def start_program(
        self,
        goal: str,
        *,
        budget: RunBudget | None = None,
        plan: Plan | None = None,
        max_replans: int = 1,
        inherit_accepted: bool = True,
    ) -> Program:
        """Plan (read-only) and persist a new program. Executes nothing.

        Programs chain: when `vector-integration` exists the new program is cut
        from it (so it builds on work earlier programs got accepted) and, with
        `inherit_accepted`, starts with their accepted-evidence ledger so the
        planner never reopens finished work.
        """

        if not goal.strip():
            raise SupervisorError("A program goal is required.")

        program = Program(
            program_id=f"prog-{uuid4().hex[:8]}",
            goal=goal.strip(),
            budget=budget or RunBudget(),
            max_replans=max_replans,
        )

        if self._integration_exists():
            program.base_ref = INTEGRATION_BRANCH

        if inherit_accepted:
            seen = {(e["package_id"], e.get("commit", "")) for e in program.ledger}

            for earlier in self.list_programs():
                for entry in earlier.ledger:
                    key = (entry["package_id"], entry.get("commit", ""))

                    if entry.get("status") == "accepted" and key not in seen:
                        program.ledger.append(dict(entry))
                        seen.add(key)

        if plan is None:
            if self.planner is None:
                raise SupervisorError("No planner configured and no plan supplied.")

            if program.budget.max_provider_calls < 1:
                raise SupervisorError("The provider-call budget cannot pay for even one planner call.")

            try:
                plan = self.planner.plan(
                    self._planning_input(program, max_packages=program.budget.max_packages)
                )
            except PlannerError as exc:
                raise SupervisorError(f"Planning failed: {exc}") from exc

            program.usage.provider_calls += plan.proposer_calls  # planner (+ repair) calls

        program.packages = [PackageState(package=p.to_dict()) for p in plan.packages]

        if not program.packages:
            program.status = COMPLETED
            program.status_reason = "; ".join(plan.warnings) or "Nothing valid left to do."

        self.save(program)
        return program

    # --- owner controls ------------------------------------------------

    def pause(self, program_id: str, reason: str = "paused by owner") -> Program:
        program = self.load(program_id)

        if program.status in _FINAL:
            raise SupervisorError(f"Program is {program.status}; nothing to pause.")

        # A running loop only sees a control file; it applies it between packages.
        self._control_path(program_id).write_text(f"pause:{reason}", encoding="utf-8")
        program.status = PAUSED
        program.status_reason = reason
        self.save(program)
        return program

    def stop(self, program_id: str, reason: str = "stopped by owner") -> Program:
        program = self.load(program_id)

        if program.status == COMPLETED:
            raise SupervisorError("Program already completed.")

        self._control_path(program_id).write_text(f"stop:{reason}", encoding="utf-8")
        program.status = STOPPED
        program.status_reason = reason
        self.save(program)
        return program

    def resume(self, program_id: str) -> Program:
        program = self.load(program_id)

        if program.status not in _RESUMABLE:
            raise SupervisorError(f"Program is {program.status}; only {sorted(_RESUMABLE)} can resume.")

        unresolved = [p.package_id for p in program.packages if p.state == P_NEEDS_HUMAN]

        if unresolved:
            raise SupervisorError(
                f"Packages {unresolved} still need the owner: `skip` or `retry` them first."
            )

        if program.status == BUDGET_EXHAUSTED:
            b, u = program.budget, program.usage
            unstarted = any(p.state == P_PLANNED and not p.started for p in program.packages)
            still = self._budget_stop(program, 0.0, next_calls=self.worst_case_calls(1)) or (
                "max work packages reached"
                if unstarted and u.packages_started >= b.max_packages
                else ""
            )

            if still:
                raise SupervisorError(f"Budget is still exhausted ({still}); `extend` it first.")

        self._control_path(program_id).unlink(missing_ok=True)
        program.status = ACTIVE
        program.status_reason = ""
        self.save(program)
        return program

    def extend_budget(self, program_id: str, **limits: float) -> Program:
        program = self.load(program_id)

        for key, value in limits.items():
            if not hasattr(program.budget, key):
                raise SupervisorError(f"Unknown budget field {key!r}")
            if value is None:
                continue
            if value < getattr(program.budget, key):
                raise SupervisorError("Budgets can only be raised, never lowered, mid-program.")
            setattr(program.budget, key, value)

        self.save(program)
        return program

    def skip_package(self, program_id: str, package_id: str, reason: str = "skipped by owner") -> Program:
        program = self.load(program_id)
        pkg = program.package(package_id)

        if pkg.state == P_ACCEPTED:
            raise SupervisorError("Accepted packages cannot be skipped.")

        pkg.state, pkg.note = P_SKIPPED, reason
        self.save(program)
        return program

    def retry_package(self, program_id: str, package_id: str) -> Program:
        program = self.load(program_id)
        pkg = program.package(package_id)

        if pkg.state not in (P_FAILED, P_NEEDS_HUMAN):
            raise SupervisorError(f"Package is {pkg.state}; only failed/needs_human can be retried.")

        pkg.state, pkg.corrections, pkg.last_fingerprint = P_PLANNED, 0, ""
        pkg.note = "Retried by owner."
        self.save(program)
        return program

    # --- budget --------------------------------------------------------

    def _budget_stop(self, program: Program, run_elapsed: float, *, next_calls: int = 0) -> str:
        b, u = program.budget, program.usage

        if u.elapsed_seconds + run_elapsed >= b.max_elapsed_seconds:
            return f"max elapsed time reached ({b.max_elapsed_seconds:.0f}s)"
        if u.provider_calls + next_calls > b.max_provider_calls:
            return (
                f"max provider calls would be exceeded "
                f"({u.provider_calls}+{next_calls} > {b.max_provider_calls})"
            )
        return ""

    @staticmethod
    def worst_case_calls(max_retries: int) -> int:
        """Upper bound for one package attempt: implement + review, each fix adds fix + re-review."""

        return 2 + 2 * max_retries

    # --- the run loop --------------------------------------------------

    def run_program(self, program_id: str, *, max_packages_this_run: int | None = None) -> RunReport:
        program = self.load(program_id)
        report = RunReport(program_id, status=program.status)

        if program.status not in (ACTIVE, WAITING_REVIEW):
            report.stopped_because = f"program is {program.status}"
            return report

        if not self.worker._acquire_lock():
            report.stopped_because = "another worker holds the lock"
            return report

        run_start = self.now_fn()

        try:
            for item in self.worker.backlog.recover_interrupted():
                self.worker.notify(
                    "attention", "Interrupted item moved to NEEDS_HUMAN, not replayed.", item.item_id
                )

            if self.worker.config.refresh_quota_telemetry:
                self.worker.quota.refresh_from_telemetry()

            self._reconcile_running(program)
            self.worker.reactivate_deferred()
            self._resume_waiting_reviews(program, run_start)
            self.save(program)

            while True:
                if self._apply_control(program):
                    break

                if program.status != ACTIVE:
                    break

                if max_packages_this_run is not None and len(report.executed) >= max_packages_this_run:
                    report.stopped_because = "max packages this run"
                    break

                if self.worker.stop_path.exists():
                    report.stopped_because = "STOP file present"
                    break

                package = self._next_package(program)

                if package is None:
                    self._finish(program)
                    self.save(program)
                    break

                if package.work_package().needs_owner:
                    reasons = ", ".join(package.work_package().owner_reasons)
                    package.state = P_NEEDS_HUMAN
                    package.note = f"Owner approval required: {reasons}"
                    program.status, program.status_reason = NEEDS_HUMAN, (
                        f"{package.package_id} needs the owner ({reasons})"
                    )
                    self.worker.notify("attention", program.status_reason, program.program_id)
                    self.save(program)
                    break

                hold = self.worker.holding_reason()

                if hold is not None:
                    report.stopped_because = (
                        f"provider unavailable: {hold}; state preserved, nothing faked"
                    )
                    break

                if not package.started and program.usage.packages_started >= program.budget.max_packages:
                    self._exhaust(program, f"max work packages reached ({program.budget.max_packages})")
                    break

                calls = self.worst_case_calls(1)
                reason = self._budget_stop(
                    program, self.now_fn() - run_start, next_calls=calls
                )

                if reason:
                    self._exhaust(program, reason)
                    break

                item = self._queue(program, package)

                if not package.started:
                    package.started = True
                    program.usage.packages_started += 1

                package.state, package.item_id = P_RUNNING, item.item_id
                self.save(program)  # write-ahead: a crash now is recoverable

                outcome = self.worker.execute_item(item, base_ref=program.base_ref or None)
                self._apply_outcome(program, package, outcome)
                report.executed.append((package.package_id, outcome))
                self.save(program)
                self.worker.touch_lock()

                if outcome == bl.DEFERRED:
                    report.stopped_because = "provider became unavailable; package deferred"
                    break
        finally:
            program.usage.elapsed_seconds += max(0.0, self.now_fn() - run_start)
            self.save(program)
            self.worker._release_lock()

        report.status = program.status

        if not report.stopped_because:
            report.stopped_because = program.status_reason or program.status

        return report

    def _resume_waiting_reviews(self, program: Program, run_start: float) -> None:
        """Run deferred independent reviews that have become affordable (or owner-allowed)."""

        waiting = [p for p in program.packages if p.state == P_WAITING_REVIEW]

        if program.status == WAITING_REVIEW:
            program.status, program.status_reason = ACTIVE, ""

        for package in waiting:
            try:
                item = self.worker.backlog.get(package.item_id or "")
            except KeyError:
                continue

            if item.status != bl.WAITING_REVIEW:
                continue

            if not self.worker.can_resume_review(item, allow_emergency=self.allow_emergency_review):
                continue

            reason = self._budget_stop(
                program, self.now_fn() - run_start, next_calls=self.worst_case_calls(1)
            )

            if reason:
                self._exhaust(program, reason)
                return

            outcome = self.worker.resume_review_item(
                item, allow_emergency=self.allow_emergency_review
            )

            if outcome is None:
                continue

            self._apply_outcome(program, package, outcome)
            self.save(program)

            if program.status != ACTIVE:
                return

    def _apply_control(self, program: Program) -> bool:
        path = self._control_path(program.program_id)

        if not path.exists():
            return False

        try:
            command, _, reason = path.read_text(encoding="utf-8").partition(":")
        except OSError:
            return False

        path.unlink(missing_ok=True)
        program.status = STOPPED if command == "stop" else PAUSED
        program.status_reason = reason or command
        self.save(program)
        return True

    def _exhaust(self, program: Program, reason: str) -> None:
        program.status, program.status_reason = BUDGET_EXHAUSTED, reason
        self.worker.notify("attention", f"Program budget exhausted: {reason}", program.program_id)
        self.save(program)

    # --- package selection ---------------------------------------------

    def _next_package(self, program: Program) -> PackageState | None:
        by_id = {p.package_id: p for p in program.packages}

        for pkg in program.packages:
            if pkg.state != P_PLANNED:
                continue

            deps = [by_id.get(d) for d in pkg.work_package().dependencies]

            if any(d is None or d.state in _UNSATISFIABLE for d in deps):
                pkg.state, pkg.note = P_SKIPPED, "a dependency was not accepted"
                continue

            if all(d.state == P_ACCEPTED for d in deps if d is not None):
                return pkg

        return None

    def _finish(self, program: Program) -> None:
        states = {p.state for p in program.packages}

        if P_NEEDS_HUMAN in states or P_RUNNING in states:
            program.status = NEEDS_HUMAN
            program.status_reason = "a package needs the owner"
        elif P_FAILED in states:
            program.status = NEEDS_HUMAN
            program.status_reason = "packages failed after their bounded correction and re-plan"
        elif P_WAITING_REVIEW in states:
            waiting = [p.package_id for p in program.packages if p.state == P_WAITING_REVIEW]
            program.status = WAITING_REVIEW
            program.status_reason = (
                f"{len(waiting)} package(s) wait for an independent review that is deferred "
                f"({', '.join(waiting)}); run again once the reviewer provider recovers"
            )
        elif P_PLANNED in states:
            program.status = NEEDS_HUMAN
            program.status_reason = "planned packages are unreachable (unsatisfied dependencies)"
        else:
            program.status = COMPLETED
            accepted = sum(1 for p in program.packages if p.state == P_ACCEPTED)
            program.status_reason = f"{accepted} package(s) accepted"

    # --- queueing ------------------------------------------------------

    def _integration_exists(self) -> bool:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.repo_root), "rev-parse", "--verify", "--quiet",
                 f"refs/heads/{INTEGRATION_BRANCH}"],
                capture_output=True, shell=False, check=False, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return False

        return proc.returncode == 0

    def _creates_new_files(self, wp: WorkPackage, ref: str) -> bool:
        """True if a concrete allowed file path does not exist yet at `ref`."""

        for path in wp.allowed_paths:
            if path.endswith("/") or any(ch in path for ch in "*?["):
                continue

            try:
                proc = subprocess.run(
                    ["git", "-C", str(self.repo_root), "cat-file", "-e", f"{ref}:{path}"],
                    capture_output=True, shell=False, check=False, timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                return False

            if proc.returncode != 0:
                return True

        return False

    def _existing_item(self, program: Program, package: PackageState) -> bl.BacklogItem | None:
        for item in self.worker.backlog.all():
            if (
                item.program_id == program.program_id
                and item.package_id == package.package_id
                and not item.is_terminal()
            ):
                return item
        return None

    def _queue(self, program: Program, package: PackageState) -> bl.BacklogItem:
        """Backlog item for the package; reuses an unfinished one (no duplicates)."""

        existing = self._existing_item(program, package)

        if existing is not None:
            return existing

        wp = package.work_package()
        owner = wp.preferred_owner

        if owner != "claude" and self._creates_new_files(wp, program.base_ref or "HEAD"):
            # Codex's Windows sandbox creates NEW files the owner account cannot
            # read (modifying existing files is fine), which crashes the bridge.
            # Claude implements new-file work; Codex still reviews it.
            owner = "claude"

        description = wp.description()

        if package.corrections and package.note:
            description += (
                "\n\nPREVIOUS ATTEMPT WAS BLOCKED. Address this specifically and do not "
                f"repeat the same approach:\n{package.note[:1100]}"
            )

        package.calls_counted = 0

        return self.worker.backlog.add(
            description=description,
            test_targets=list(wp.test_targets),
            difficulty=wp.requested_difficulty,
            max_retries=1,
            title=wp.title,
            program_id=program.program_id,
            package_id=wp.package_id,
            objective=wp.objective,
            allowed_paths=list(wp.allowed_paths),
            forbidden_scope=list(wp.forbidden_scope),
            acceptance_criteria=list(wp.acceptance_criteria)
            + [f"Behavioral evidence: {e}" for e in wp.behavioral_evidence],
            stop_conditions=list(wp.stop_conditions),
            acceptance_critical=wp.acceptance_critical,
            preferred_owner=owner,
        )

    # --- outcomes ------------------------------------------------------

    def _reconcile_running(self, program: Program) -> None:
        """After a crash/restart: settle packages the last run left RUNNING."""

        for package in program.packages:
            if package.state != P_RUNNING:
                continue

            try:
                item = self.worker.backlog.get(package.item_id or "")
            except KeyError:
                package.state, package.note = P_NEEDS_HUMAN, "Backlog item vanished mid-run."
                program.status, program.status_reason = NEEDS_HUMAN, "interrupted package"
                continue

            if item.status == bl.PENDING:
                # died before the worker started it: safe to run normally
                package.state = P_PLANNED
            else:
                self._apply_outcome(program, package, item.status)

    def _apply_outcome(self, program: Program, package: PackageState, outcome: str) -> None:
        item = self.worker.backlog.get(package.item_id or "")
        # count only calls not yet counted for this item (a resumed review adds just its own)
        program.usage.provider_calls += max(0, item.provider_calls - package.calls_counted)
        package.calls_counted = max(package.calls_counted, item.provider_calls)
        result_note = _bounded(item.result_note or "", 600)  # redacted before it can be reused
        package.note = result_note or package.note

        if outcome == bl.WAITING_REVIEW:
            # Implemented and tested; the independent review is deferred. Not accepted, not
            # integrated, no ledger entry. Dependents wait; independent packages continue.
            package.state = P_WAITING_REVIEW
            package.note = f"waiting for independent review by {item.awaiting_reviewer or '?'}"
            return

        if outcome == bl.PASSED:
            if not item.commit:
                package.state = P_NEEDS_HUMAN
                package.note = f"Passed review but was not committed: {result_note}"
                program.status, program.status_reason = NEEDS_HUMAN, f"{package.package_id} not committed"
                return

            merged = self._integrate(item)

            if merged != "merged":
                package.state = P_NEEDS_HUMAN
                package.note = f"Passed review but integration was '{merged}': {result_note}"
                program.status = NEEDS_HUMAN
                program.status_reason = (
                    f"{package.package_id} could not be integrated ({merged}); "
                    "later packages would not build on it"
                )
                self.worker.notify("attention", program.status_reason, program.program_id)
                return

            program.base_ref = INTEGRATION_BRANCH
            package.state, package.commit = P_ACCEPTED, item.commit
            wp = package.work_package()
            program.ledger.append(
                asdict(
                    LedgerEntry(
                        package_id=wp.package_id,
                        title=wp.title,
                        objective=wp.objective,
                        status="accepted",
                        evidence=(
                            f"item {item.item_id}; task {item.task_id}; branch {item.branch}; "
                            "targeted tests passed; independent cross-provider review PASS"
                        ),
                        commit=item.commit,
                    )
                )
            )
            return

        if outcome == bl.DEFERRED:
            package.state = P_PLANNED
            package.note = f"deferred: {item.deferred_reason}"
            return

        if (
            outcome == bl.CRASHED
            and "PermissionError" in (item.result_note or "")
            and package.corrections < 1
            and package.package.get("preferred_owner") != "claude"
            and program.usage.correction_cycles < program.budget.max_correction_cycles
        ):
            # Codex left files the owner cannot read: one bounded correction with
            # Claude as the implementer (Codex still reviews independently).
            package.package["preferred_owner"] = "claude"
            package.package["preferred_owner_reason"] = "codex sandbox produced unreadable files"
            package.corrections += 1
            program.usage.correction_cycles += 1
            package.state = P_PLANNED
            package.note = f"retrying with claude as implementer after: {result_note[:120]}"
            return

        if outcome in (bl.NEEDS_HUMAN, bl.CRASHED):
            package.state = P_NEEDS_HUMAN
            program.status = NEEDS_HUMAN
            program.status_reason = (
                f"{package.package_id} {'crashed' if outcome == bl.CRASHED else 'needs the owner'}: "
                f"{result_note[:160]}"
            )
            self.worker.notify("attention", program.status_reason, program.program_id)
            return

        self._handle_blocked(program, package, item)

    def _integrate(self, item: bl.BacklogItem) -> str:
        """Merge an accepted item onto vector-integration; returns its result."""

        try:
            results = dict(self.integrate_fn())
        except Exception as exc:  # noqa: BLE001 - fail closed
            return f"error: {type(exc).__name__}"

        return results.get(item.item_id) or self.worker.backlog.get(item.item_id).integration or "not integrated"

    @staticmethod
    def _evidence_text(ev: dict[str, Any], note: str) -> str:
        """Bounded, already-redacted diagnosis for corrections, re-plans and the owner."""

        if not ev:
            return note[:600]

        parts = [
            f"category={ev.get('category')} kind={ev.get('kind')} exit_code={ev.get('exit_code')}",
        ]

        if ev.get("command"):
            parts.append(f"command: {str(ev['command'])[-200:]}")

        for finding in list(ev.get("findings") or [])[:3]:
            parts.append(f"review finding: {str(finding)[:160]}")

        if ev.get("tail"):
            tail = str(ev["tail"])
            tail = tail if len(tail) <= 700 else tail[:200] + " ... " + tail[-500:]
            parts.append(f"output tail: {tail}")
        elif ev.get("note"):
            parts.append(f"note: {str(ev['note'])[:200]}")

        return "\n".join(parts)[:1100]

    def _handle_blocked(self, program: Program, package: PackageState, item: bl.BacklogItem) -> None:
        note = _bounded(item.result_note or "blocked without a note", 400)
        ev = dict(item.failure_evidence or {})
        category = str(ev.get("category", "unknown"))
        kind = str(ev.get("kind", "implementation"))
        evidence_text = self._evidence_text(ev, note)
        fingerprint = _blocker_fingerprint(
            f"{category} {ev.get('exit_code')} {ev.get('tail') or note}"
        )
        seen = program.blockers.setdefault(
            fingerprint,
            {"description": f"{package.title}: [{category}] {note[:120]}", "count": 0},
        )
        seen["count"] += 1
        seen["evidence"] = evidence_text
        seen["kind"] = kind
        package.last_fingerprint = fingerprint
        package.note = evidence_text  # what a correction (or the owner) is shown

        # A wrong test SPECIFICATION cannot be fixed by re-running the same package:
        # the plan has to change, so go straight to the (single, bounded) re-plan.
        correctable = kind != "test_spec"

        if (
            correctable
            and package.corrections < 1
            and program.usage.correction_cycles < program.budget.max_correction_cycles
        ):
            package.corrections += 1
            program.usage.correction_cycles += 1
            package.state = P_PLANNED  # one bounded correction, then retest + re-review
            return

        package.state = P_FAILED
        self._stalled(program, package)

    def _stalled(self, program: Program, package: PackageState) -> None:
        """Same fundamental blocker survived its correction: re-plan once, else stop."""

        for other in program.packages:
            if other.state == P_PLANNED and package.package_id in other.work_package().dependencies:
                other.state, other.note = P_SKIPPED, f"dependency {package.package_id} failed"

        if self.planner is None or program.usage.replans >= program.max_replans:
            program.status = NEEDS_HUMAN
            program.status_reason = (
                f"{package.package_id} is stuck on the same blocker after its correction"
                + ("; re-plan budget used" if self.planner else "; no planner configured")
                + f" [{(program.blockers.get(package.last_fingerprint) or {}).get('kind', 'unknown')}]"
            )
            self.worker.notify("attention", program.status_reason, program.program_id)
            return

        remaining = program.budget.max_packages - program.usage.packages_started

        if remaining < 1:
            program.status = NEEDS_HUMAN
            program.status_reason = f"{package.package_id} failed and no package budget is left to re-plan"
            return

        if program.budget.max_provider_calls - program.usage.provider_calls < 1:
            # Re-planning is a provider call too; never spend past the budget.
            program.status = BUDGET_EXHAUSTED
            program.status_reason = (
                f"{package.package_id} failed but no provider calls remain to re-plan; "
                "`extend` the budget, then `retry` the package"
            )
            self.worker.notify("attention", program.status_reason, program.program_id)
            return

        program.usage.replans += 1

        try:
            plan = self.planner.plan(self._planning_input(program, max_packages=remaining))
        except PlannerError as exc:
            program.usage.provider_calls += int(getattr(exc, "calls", 1))
            program.status = NEEDS_HUMAN
            program.status_reason = f"re-plan failed: {exc}"
            self.worker.notify("attention", program.status_reason, program.program_id)
            return

        program.usage.provider_calls += plan.proposer_calls
        taken = {p.package_id for p in program.packages}
        prefix = f"r{program.usage.replans}-"
        rename = {p.package_id: prefix + p.package_id for p in plan.packages}
        fresh: list[PackageState] = []

        for wp in plan.packages:
            new_id = rename[wp.package_id]

            if new_id in taken:
                continue

            fresh.append(
                PackageState(
                    package=replace(
                        wp,
                        package_id=new_id,
                        dependencies=tuple(rename.get(d, d) for d in wp.dependencies),
                    ).to_dict()
                )
            )

        # unstarted packages are superseded by the new plan
        program.packages = [
            p for p in program.packages if not (p.state == P_PLANNED and not p.started)
        ] + fresh

        if fresh:
            package.state = P_SKIPPED
            package.note = (
                f"failed after its correction on the same blocker; superseded by re-plan "
                f"{prefix.rstrip('-')} ({package.note[:80]})"
            )
        else:
            program.status = NEEDS_HUMAN
            program.status_reason = (
                f"re-plan after {package.package_id}'s blocker produced nothing viable; owner input needed"
            )
            self.worker.notify("attention", program.status_reason, program.program_id)

    # --- status --------------------------------------------------------

    def status(self, program_id: str) -> dict[str, Any]:
        program = self.load(program_id)
        b, u = program.budget, program.usage

        return {
            "program_id": program.program_id,
            "goal": program.goal,
            "status": program.status,
            "reason": program.status_reason,
            "budget": asdict(b),
            "usage": asdict(u),
            "remaining": {
                "packages": max(0, b.max_packages - u.packages_started),
                "provider_calls": max(0, b.max_provider_calls - u.provider_calls),
                "correction_cycles": max(0, b.max_correction_cycles - u.correction_cycles),
                "elapsed_seconds": max(0.0, b.max_elapsed_seconds - u.elapsed_seconds),
            },
            "packages": [
                {
                    "id": p.package_id,
                    "title": p.title,
                    "state": p.state,
                    "corrections": p.corrections,
                    "commit": p.commit[:10],
                    "note": p.note[:120],
                }
                for p in program.packages
            ],
            "ledger": [
                {"package": e["package_id"], "title": e["title"], "commit": e["commit"][:10]}
                for e in program.ledger
            ],
            "blockers": [
                {"description": v["description"], "count": v["count"]}
                for v in program.blockers.values()
            ],
        }


# --- CLI ---------------------------------------------------------------


def _build(repo_root: str | None, planner_provider: str = "claude") -> Supervisor:
    from autonomous_worker import _default_worker
    from planner import claude_read_only_provider, codex_read_only_provider, make_model_proposer

    here = Path(__file__).resolve().parent
    worker = _default_worker(repo_root)
    provider_fn = (
        codex_read_only_provider(worker.repo_root)
        if planner_provider == "codex"
        else claude_read_only_provider(worker.repo_root)
    )
    planner = Planner(worker.repo_root, make_model_proposer(provider_fn))
    return Supervisor(worker.repo_root, here / ".state" / "supervisor", worker, planner)


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="supervisor.py")
    parser.add_argument("--repo-root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    program = sub.add_parser("program")
    ps = program.add_subparsers(dest="pcommand", required=True)

    start = ps.add_parser("start", help="Plan (read-only) and persist a program; add --run to execute.")
    start.add_argument("--goal", required=True)
    start.add_argument("--planner", choices=["claude", "codex"], default="claude")
    start.add_argument("--run", action="store_true")

    def budget_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--max-packages", type=int, default=None)
        p.add_argument("--max-provider-calls", type=int, default=None)
        p.add_argument("--max-corrections", type=int, default=None)
        p.add_argument("--max-hours", type=float, default=None)

    budget_args(start)
    ps.add_parser("list")

    for name in ("run", "status", "pause", "resume", "stop"):
        p = ps.add_parser(name)
        p.add_argument("program_id")
        if name == "run":
            p.add_argument("--max-packages-this-run", type=int, default=None)
            p.add_argument(
                "--allow-emergency-review", action="store_true",
                help="Owner override: spend an EMERGENCY reviewer provider on deferred reviews.",
            )

    ext = ps.add_parser("extend", help="Raise (never lower) a budget.")
    ext.add_argument("program_id")
    budget_args(ext)

    for name in ("skip", "retry"):
        p = ps.add_parser(name)
        p.add_argument("program_id")
        p.add_argument("package_id")

    args = parser.parse_args(argv)
    sup = _build(args.repo_root, getattr(args, "planner", "claude"))

    try:
        if args.pcommand == "start":
            budget = RunBudget()
            for src, dst in (("max_packages", "max_packages"),
                             ("max_provider_calls", "max_provider_calls"),
                             ("max_corrections", "max_correction_cycles")):
                if getattr(args, src) is not None:
                    setattr(budget, dst, getattr(args, src))
            if args.max_hours is not None:
                budget.max_elapsed_seconds = args.max_hours * 3600
            created = sup.start_program(args.goal, budget=budget)
            _print(sup.status(created.program_id))
            if args.run and created.status == ACTIVE:
                _print(asdict(sup.run_program(created.program_id)))
            return 0

        if args.pcommand == "list":
            _print([{"id": p.program_id, "status": p.status, "goal": p.goal[:80]} for p in sup.list_programs()])
        elif args.pcommand == "run":
            sup.allow_emergency_review = args.allow_emergency_review
            report = sup.run_program(args.program_id, max_packages_this_run=args.max_packages_this_run)
            _print(asdict(report))
        elif args.pcommand == "status":
            _print(sup.status(args.program_id))
        elif args.pcommand == "pause":
            sup.pause(args.program_id)
            _print(sup.status(args.program_id))
        elif args.pcommand == "resume":
            sup.resume(args.program_id)
            _print(sup.status(args.program_id))
        elif args.pcommand == "stop":
            sup.stop(args.program_id)
            _print(sup.status(args.program_id))
        elif args.pcommand == "extend":
            sup.extend_budget(
                args.program_id,
                max_packages=args.max_packages,
                max_provider_calls=args.max_provider_calls,
                max_correction_cycles=args.max_corrections,
                max_elapsed_seconds=None if args.max_hours is None else args.max_hours * 3600,
            )
            _print(sup.status(args.program_id))
        elif args.pcommand == "skip":
            sup.skip_package(args.program_id, args.package_id)
            _print(sup.status(args.program_id))
        elif args.pcommand == "retry":
            sup.retry_package(args.program_id, args.package_id)
            _print(sup.status(args.program_id))
    except SupervisorError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(main())

    import supervisor_scenarios

    supervisor_scenarios.run_all()
