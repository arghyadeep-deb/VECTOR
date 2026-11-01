"""Deterministic supervisor scenarios A-M (no provider calls, no quota use).

Run:  python supervisor.py   (or: python supervisor_scenarios.py)

Providers are replaced by a scripted driver so the SUPERVISOR logic
(planning, floors, routing, budgets, correction/re-plan, restart recovery,
quota honesty, owner-approval pauses) is proven without spending Codex or
Claude quota. The real bridge is exercised separately by the live smoke test.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import backlog as bl
from autonomous_worker import AutonomousWorker, CommitResult, WorkerConfig
from dev_driver import DriverResult
from difficulty_inference import infer_difficulty
from models import (
    DevTask,
    Difficulty,
    Provider,
    ProviderQuota,
    QuotaBand,
    TaskStatus,
    TaskSpec,
    TestResult,
)
from orchestrator import DevOrchestrator
from planner import PlanningInput, Planner
from router import difficulty_rank
from quota import QuotaBoard, codex_quota_probe
from supervisor import (
    ACTIVE,
    BUDGET_EXHAUSTED,
    COMPLETED,
    NEEDS_HUMAN,
    P_ACCEPTED,
    P_NEEDS_HUMAN,
    P_PLANNED,
    P_SKIPPED,
    PAUSED,
    RunBudget,
    Supervisor,
    SupervisorError,
    WAITING_REVIEW,
    P_WAITING_REVIEW,
)

README = Path(__file__).resolve().parent / "README.md"


class Died(BaseException):
    """Simulates the process being killed mid-package (not catchable as Exception)."""


def pkg(pid: str, title: str, objective: str, deps: tuple[str, ...] = (), **extra: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "package_id": pid,
        "title": title,
        "objective": objective,
        "scope": objective,
        "allowed_paths": [f"core/{pid}.py", f"tests/test_{pid}.py"],
        "acceptance_criteria": [f"{title} behaves as described", "existing tests still pass"],
        "test_targets": [f"tests/test_{pid}.py"],
        "behavioral_evidence": [f"a test exercises the new {title} behaviour"],
        "dependencies": list(deps),
        "difficulty": "routine",
    }
    raw.update(extra)
    return raw


class ScriptedDriver:
    """Stands in for dev_driver.run_task; script[package_id] is a list of steps."""

    def __init__(self, script: dict[str, list[str]] | None = None) -> None:
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls: list[dict[str, Any]] = []
        self.on_call: Callable[[], None] = lambda: None
        self.waiting: dict[str, int] = {}  # task_id -> provider calls when it stopped at WAITING_REVIEW

    def count(self, package_id: str) -> int:
        return sum(1 for c in self.calls if c["package_id"] == package_id)

    def __call__(self, root: Path, **kw: Any) -> DriverResult:
        spec = kw.get("spec")
        pid = spec.package_id if spec else "manual"
        self.calls.append({"package_id": pid, "description": kw["description"], "kw": kw})
        self.on_call()
        queue = self.script.get(pid, [])
        step = queue.pop(0) if queue else "PASS"

        if step == "DIE":
            raise Died()

        if step == "CRASH":
            raise RuntimeError("scripted crash")

        if step == "CRASH_PERMISSION":
            raise PermissionError("[Errno 13] Permission denied: 'tests/test_new.py'")

        task = DevTask(description=kw["description"])
        task.owner, task.reviewer = Provider.CLAUDE, Provider.CODEX
        task.requested_difficulty = kw["difficulty"].value
        task.inferred_difficulty = kw["difficulty"].value
        task.difficulty_reason = "scripted"
        task.reviewer_evidence = ["review"]
        worktree = None

        task.provider_calls = 2  # implementer + reviewer, the normal full attempt

        if step == "PASS":
            task.status = TaskStatus.PASS
            task.changed_files = ["core/x.py"]
            task.notes.append("PASS")
            worktree = SimpleNamespace(path=root, branch_name=f"vector-dev/{task.task_id[:8]}")
        elif step == "WAIT":
            # Tests passed; the Codex review is deferred (POLICY.md sec. 10): not a pass.
            task.status = TaskStatus.WAITING_REVIEW
            task.provider_calls = 1
            task.notes.append("Independent review deferred (reviewer in EMERGENCY).")
            worktree = SimpleNamespace(path=root, branch_name=f"vector-dev/{task.task_id[:8]}")
            self.waiting[task.task_id] = 1
        elif step == "HUMAN":
            task.status = TaskStatus.NEEDS_HUMAN
            task.provider_calls = 0
            task.notes.append("approval gate")
        elif step.startswith(("BLOCK_SPEC:", "BLOCK_TEST:")):
            # Tests failed right after implementation: the reviewer is never reached.
            kind, _, text = step.partition(":")
            code = 4 if kind == "BLOCK_SPEC" else 1
            task.status = TaskStatus.BLOCKED
            task.provider_calls = getattr(self, "spec_calls", 1)
            task.tests = [
                TestResult(
                    command="python -m pytest -q tests/t.py",
                    exit_code=code,
                    passed=False,
                    stdout=text,
                    stderr="",
                )
            ]
            task.notes.append("Targeted tests failed after implementation.")
        elif step.startswith("EXHAUST:"):
            task.status = TaskStatus.BLOCKED
            task.provider_calls = 1
            task.notes.append(f"PROVIDER_UNAVAILABLE:{step.split(':', 1)[1]}")
        elif step.startswith("BLOCK:"):
            task.status = TaskStatus.BLOCKED
            task.notes.append(step.split(":", 1)[1])
        else:
            raise AssertionError(f"unknown script step {step}")

        return DriverResult(task, worktree)


def fake_commit(worktree: Path, files: list[str], message: str) -> CommitResult:
    return CommitResult(True, sha=os.urandom(20).hex(), branch="vector-dev/fake")


class Harness:
    def __init__(
        self,
        root: Path,
        *,
        script: dict[str, list[str]] | None = None,
        proposals: list[list[dict[str, Any]]] | None = None,
        daily_cap: int = 3,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self.root = root
        self.repo = root / "repo"
        self.repo.mkdir(parents=True)

        def git(*a: str) -> None:
            subprocess.run(["git", "-C", str(self.repo), *a], check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "h@example.invalid")
        git("config", "user.name", "H")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        git("add", "seed.txt")
        git("commit", "-q", "-m", "seed")

        self.driver = ScriptedDriver(script)
        self.daily_cap = daily_cap
        self.now_fn = now_fn
        self.proposals = list(proposals or [])
        self.planning_inputs: list[PlanningInput] = []
        self.integration_override: dict[str, str] = {}
        self.reviews: list[str] = []
        self.review_outcome = "PASS"
        self.build()

    def fake_integrate(self) -> list[tuple[str, str]]:
        """Stands in for IntegrationStage: merge unless the test says otherwise."""

        out: list[tuple[str, str]] = []

        for item in self.worker.backlog.all():
            if item.status == bl.PASSED and item.commit and not item.integration:
                result = self.integration_override.get(item.package_id or "", "merged")
                self.worker.backlog.update(
                    item.item_id,
                    integration=result,
                    integrated_commit=item.commit if result == "merged" else None,
                )
                out.append((item.item_id, result))

        return out

    def review(
        self, root: Path, *, task_id: str, test_targets: list[str],
        run_ci_gate: bool = False, orchestrator: Any = None,
    ) -> DriverResult:
        """Stands in for dev_driver.resume_review_task (the deferred independent review)."""

        self.reviews.append(task_id)
        task = DevTask(description="resumed review")
        task.task_id = task_id
        task.owner, task.reviewer = Provider.CLAUDE, Provider.CODEX
        task.provider_calls = self.driver.waiting.get(task_id, 1) + 1  # implementer + this review
        task.reviewer_evidence = ["review"]

        if self.review_outcome == "PASS":
            task.status = TaskStatus.PASS
            task.changed_files = ["core/x.py"]
            task.notes.append("PASS")
            return DriverResult(task, SimpleNamespace(path=root, branch_name="vector-dev/resumed"))

        task.status = TaskStatus.BLOCKED
        task.notes.append("Reviewer found BLOCKER: the parser still corrupts input 1")
        return DriverResult(task, None)

    def proposer(self, planning: PlanningInput) -> list[dict[str, Any]]:
        self.planning_inputs.append(planning)
        return self.proposals.pop(0) if self.proposals else []

    def build(self) -> None:
        """(Re)create worker + supervisor from the same on-disk state (a 'restart')."""

        self.worker = AutonomousWorker(
            self.repo,
            self.root / "state" / "worker",
            config=WorkerConfig(daily_cap=self.daily_cap, max_tasks_per_run=5),
            run_task_fn=self.driver,
            review_fn=self.review,
            commit_fn=fake_commit,
            echo=False,
        )
        planner = Planner(self.repo, self.proposer) if self.proposals or self.planning_inputs else None
        self.sup = Supervisor(
            self.repo, self.root / "state" / "supervisor", self.worker, planner,
            now_fn=self.now_fn, integrate_fn=self.fake_integrate,
        )


def _with_temp(fn: Callable[[Path], None]) -> None:
    root = Path(tempfile.mkdtemp(prefix="vector_scenario_"))

    try:
        fn(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def three(prefix: str = "") -> list[dict[str, Any]]:
    return [
        pkg("p1", "Alpha parser hardening", "Harden the alpha parser against truncated input."),
        pkg("p2", "Beta scheduler jitter", "Add bounded jitter to the beta scheduler tick.", ("p1",)),
        pkg("p3", "Gamma exporter batching", "Batch the gamma exporter writes into groups.", ("p1", "p2")),
    ]


# --- A: planner decomposes a program -----------------------------------


def scenario_A(root: Path) -> None:
    h = Harness(root, proposals=[three()])
    program = h.sup.start_program("Harden the alpha, beta and gamma modules.")

    assert [p.package_id for p in program.packages] == ["p1", "p2", "p3"]
    assert program.usage.provider_calls == 1, "the planning call is counted"
    wp = program.packages[0].work_package()

    for field_name in (
        "objective", "scope", "allowed_paths", "forbidden_scope", "acceptance_criteria",
        "test_targets", "behavioral_evidence", "stop_conditions", "risk",
        "effective_difficulty", "reviewer_policy",
    ):
        assert getattr(wp, field_name), field_name

    assert program.packages[2].work_package().dependencies == ("p1", "p2")
    assert h.planning_inputs[0].repo_state.get("head"), "planner inspected repo state"

    report = h.sup.run_program(program.program_id)
    done = h.sup.load(program.program_id)
    assert done.status == COMPLETED, (done.status, done.status_reason)
    assert [pid for pid, _ in report.executed] == ["p1", "p2", "p3"]
    assert [c["package_id"] for c in h.driver.calls] == ["p1", "p2", "p3"]
    assert len(done.ledger) == 3 and all(e["commit"] for e in done.ledger)
    first = h.driver.calls[0]["kw"]["spec"]
    assert first.allowed_paths == ("core/p1.py", "tests/test_p1.py") and first.program_id == done.program_id
    assert any("Behavioral evidence" in c for c in first.acceptance_criteria)
    assert h.worker._count_today() == 0, "program work never touches the daily cap"
    assert "base_ref" not in h.driver.calls[0]["kw"], "the first package builds on live HEAD"
    assert [c["kw"].get("base_ref") for c in h.driver.calls[1:]] == ["vector-integration"] * 2, (
        "dependent packages build on the accepted, integrated work"
    )


# --- B: safety floors upgrade an under-labelled task -------------------


def scenario_B(root: Path) -> None:
    orch = DevOrchestrator(root, root / "orch")
    task = orch.prepare_task(
        description="Rename a private helper for readability.",
        difficulty=Difficulty.SCOUT,
        spec=TaskSpec(
            objective="Rename a private helper.",
            allowed_paths=("core/security/scanner.py",),
            test_targets=("tests/test_scanner.py",),
        ),
    )
    assert task.requested_difficulty == "scout"
    assert difficulty_rank(task.difficulty) >= difficulty_rank(Difficulty.HARD), task.difficulty
    assert "security" in task.difficulty_reason.lower()
    persisted = orch.state.load(task.task_id)
    assert (persisted.requested_difficulty, persisted.inferred_difficulty) == (
        task.requested_difficulty, task.inferred_difficulty
    )

    # wording alone also floors it; a requested level can raise but never lower.
    text = infer_difficulty("Tighten encryption of the credential store.", requested="scout")
    assert difficulty_rank(text.effective) >= difficulty_rank(Difficulty.HARD)
    assert difficulty_rank(text.floor) >= difficulty_rank(Difficulty.HARD)
    raised = infer_difficulty("Rename a helper.", requested="critical")
    assert raised.effective is Difficulty.CRITICAL
    migration = infer_difficulty("Run the database schema change.", requested="routine")
    assert difficulty_rank(migration.effective) >= difficulty_rank(Difficulty.HARD)


# --- C: routine work does not use the strongest route ------------------


def scenario_C(root: Path) -> None:
    orch = DevOrchestrator(root, root / "orch")
    routine = orch.prepare_task(
        description=(
            "Fix the off-by-one in the pagination helper and cover it with a regression "
            "test, keeping the change small and preserving public names."
        ),
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CODEX,
        spec=TaskSpec(allowed_paths=("core/paging.py",), test_targets=("tests/test_paging.py",)),
    )
    assert routine.difficulty in (Difficulty.SCOUT, Difficulty.ROUTINE)
    assert routine.implementer_model.model not in ("opus", "gpt-6-astra")
    assert routine.reviewer_model.model not in ("opus", "gpt-6-astra")

    critical = orch.prepare_task(
        description="Refactor the scanner internals.",
        difficulty=Difficulty.CRITICAL,
        previous_owner=Provider.CODEX,
    )
    assert critical.implementer_model != routine.implementer_model, "stronger route only when warranted"


# --- D/E: implementer and independent reviewer differ ------------------


def scenario_D_E(root: Path) -> None:
    orch = DevOrchestrator(root, root / "orch")
    claude_owned = orch.prepare_task(
        description="Tidy the alpha helper naming.", difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CODEX,
    )
    assert claude_owned.owner is Provider.CLAUDE and claude_owned.reviewer is Provider.CODEX

    codex_owned = orch.prepare_task(
        description="Tidy the beta helper naming.", difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )
    assert codex_owned.owner is Provider.CODEX and codex_owned.reviewer is Provider.CLAUDE

    # The supervisor honours a justified owner preference by biasing previous_owner.
    h = Harness(root / "pref", proposals=[[
        pkg("p1", "Alpha parser hardening", "Harden the alpha parser against truncated input.",
            preferred_owner="codex", preferred_owner_reason="long mechanical refactor"),
    ]])
    _commit_files(h, "core/p1.py", "tests/test_p1.py")  # existing files: no new-file routing
    prog = h.sup.start_program("Harden alpha.")
    h.sup.run_program(prog.program_id)
    assert h.driver.calls[0]["kw"]["previous_owner"] is Provider.CLAUDE, "prefer codex => claude was 'previous'"


# --- F: rejection -> one bounded correction -> re-review ---------------


def scenario_F(root: Path) -> None:
    h = Harness(root, script={"p1": ["BLOCK:Reviewer found BLOCKER in the alpha parser 101"]},
                proposals=[three()[:1]])
    prog = h.sup.start_program("Harden alpha.")
    h.sup.run_program(prog.program_id)
    done = h.sup.load(prog.program_id)

    assert done.status == COMPLETED and done.packages[0].state == P_ACCEPTED
    assert h.driver.count("p1") == 2, "exactly one correction"
    assert done.packages[0].corrections == 1 and done.usage.correction_cycles == 1
    retry_prompt = h.driver.calls[1]["description"]
    assert "PREVIOUS ATTEMPT WAS BLOCKED" in retry_prompt and "BLOCKER in the alpha parser" in retry_prompt
    assert "PREVIOUS ATTEMPT" not in h.driver.calls[0]["description"]
    items = [i for i in h.worker.backlog.all() if i.package_id == "p1"]
    assert [i.status for i in items] == [bl.BLOCKED, bl.PASSED], "the blocked attempt stays as evidence"
    assert done.usage.provider_calls >= 1 + 2 + 2, "provider calls are accounted"


# --- G: persistent blocker -> re-plan once -> then stop -----------------


def scenario_G(root: Path) -> None:
    block = "BLOCK:Reviewer found BLOCKER: alpha parser still corrupts input {n}"
    replan = [
        pkg("p1", "Delta table driven lexer", "Replace hand rolled alpha scanning with a small table driven lexer."),
    ]

    # G1: the same blocker survives the correction -> one re-plan -> success.
    h = Harness(
        root / "g1",
        script={"p1": [block.format(n=1), block.format(n=2)]},
        proposals=[three()[:2], replan],
    )
    prog = h.sup.start_program("Harden alpha then beta.")
    h.sup.run_program(prog.program_id)
    done = h.sup.load(prog.program_id)

    assert h.driver.count("p1") == 2, "one attempt + one correction, no more"
    assert done.usage.replans == 1
    assert len(h.planning_inputs) == 2 and h.planning_inputs[1].blockers, "planner is shown the blocker"
    assert h.planning_inputs[1].blockers[0].count == 2
    assert h.driver.count("r1-p1") == 1
    assert done.status == COMPLETED, (done.status, done.status_reason)
    states = {p.package_id: p.state for p in done.packages}
    assert states["p1"] == P_SKIPPED and states["r1-p1"] == P_ACCEPTED
    assert "p2" not in states or states["p2"] in (P_SKIPPED,)

    # G2: the re-planned package is blocked too -> stop for the owner; hard-bounded calls.
    h2 = Harness(
        root / "g2",
        script={
            "p1": [block.format(n=1), block.format(n=2)],
            "r1-p1": [block.format(n=3), block.format(n=4)],
        },
        proposals=[three()[:2], replan],
    )
    prog2 = h2.sup.start_program("Harden alpha then beta.")
    h2.sup.run_program(prog2.program_id)
    stalled = h2.sup.load(prog2.program_id)
    assert stalled.status == NEEDS_HUMAN and "same blocker" in stalled.status_reason
    assert len(h2.driver.calls) == 4, "hard bound: 2 attempts per package, 1 re-plan"
    assert stalled.usage.replans == 1
    again = h2.sup.run_program(prog2.program_id)
    assert again.executed == [] and len(h2.driver.calls) == 4, "a stopped program does not loop"

    # G3: no planner available -> stops right after the failed correction.
    h3 = Harness(root / "g3", script={"p1": [block.format(n=1), block.format(n=2)]})
    prog3 = h3.sup.start_program("Harden alpha.", plan=_plan_of([three()[0]]))
    h3.sup.run_program(prog3.program_id)
    assert h3.sup.load(prog3.program_id).status == NEEDS_HUMAN and h3.driver.count("p1") == 2


def _commit_files(h: "Harness", *paths: str) -> None:
    for rel in paths:
        target = h.repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# existing\n", encoding="utf-8")

    for args in (("add", "-A"), ("commit", "-q", "-m", "existing files")):
        subprocess.run(["git", "-C", str(h.repo), *args], check=True, capture_output=True)


def _plan_of(raw: list[dict[str, Any]]) -> Any:
    from planner import validate_plan

    return validate_plan(raw, PlanningInput(goal="g", repo_state={"head": "x"}))


# --- H: restart preserves program/task state ---------------------------


def scenario_H(root: Path) -> None:
    # H1: the process dies mid-package.
    h = Harness(root / "h1", script={"p2": ["DIE"]}, proposals=[three()])
    prog = h.sup.start_program("Harden alpha, beta, gamma.")

    try:
        h.sup.run_program(prog.program_id)
    except Died:
        pass
    else:
        raise AssertionError("scripted death should propagate")

    h.worker.lock_path.write_text("{}", encoding="utf-8")  # a killed process leaves its lock
    old = time.time() - (h.worker.config.lock_stale_seconds + 60)
    os.utime(h.worker.lock_path, (old, old))
    h.build()  # fresh objects, same disk state

    on_disk = h.sup.load(prog.program_id)
    assert on_disk.packages[0].state == P_ACCEPTED and len(on_disk.ledger) == 1
    assert on_disk.packages[1].state == "running", "write-ahead state survived"

    report = h.sup.run_program(prog.program_id)
    after = h.sup.load(prog.program_id)
    assert after.status == NEEDS_HUMAN and after.packages[1].state == P_NEEDS_HUMAN
    assert h.driver.count("p1") == 1 and h.driver.count("p2") == 1 and h.driver.count("p3") == 0
    assert report.executed == [], "the interrupted package was NOT replayed"
    assert len(after.ledger) == 1, "accepted work survived the restart"

    try:
        h.sup.resume(prog.program_id)
    except SupervisorError:
        pass
    else:
        raise AssertionError("resume must refuse while a package still needs the owner")

    h.sup.retry_package(prog.program_id, "p2")
    h.sup.resume(prog.program_id)
    h.sup.run_program(prog.program_id)
    final = h.sup.load(prog.program_id)
    assert final.status == COMPLETED
    assert (h.driver.count("p1"), h.driver.count("p2"), h.driver.count("p3")) == (1, 2, 1)

    # completed programs are never rerun
    calls = len(h.driver.calls)
    assert h.sup.run_program(prog.program_id).executed == [] and len(h.driver.calls) == calls

    # H2: the worker finished but the supervisor died before recording it.
    h2 = Harness(root / "h2", proposals=[three()[:1]])
    prog2 = h2.sup.start_program("Harden alpha.")

    def die(*a: Any, **k: Any) -> None:
        raise Died()

    h2.sup._apply_outcome = die  # type: ignore[method-assign]

    try:
        h2.sup.run_program(prog2.program_id)
    except Died:
        pass

    h2.build()
    mid = h2.sup.load(prog2.program_id)
    assert mid.packages[0].state == "running"
    assert h2.worker.backlog.get(mid.packages[0].item_id).status == bl.PASSED
    h2.sup.run_program(prog2.program_id)
    settled = h2.sup.load(prog2.program_id)
    assert settled.status == COMPLETED and settled.packages[0].state == P_ACCEPTED
    assert h2.driver.count("p1") == 1, "a package that already passed is never re-executed"

    # H3: paused stays paused across a restart; and queued-but-unstarted work is not duplicated.
    h3 = Harness(root / "h3", proposals=[three()])
    prog3 = h3.sup.start_program("Harden alpha, beta, gamma.")
    h3.sup.pause(prog3.program_id, "owner is away")
    h3.build()
    assert h3.sup.run_program(prog3.program_id).executed == [] and not h3.driver.calls
    assert h3.sup.load(prog3.program_id).status == PAUSED
    h3.sup.resume(prog3.program_id)
    pkg1 = h3.sup.load(prog3.program_id).packages[0]
    queued = h3.sup._queue(h3.sup.load(prog3.program_id), pkg1)
    again = h3.sup._queue(h3.sup.load(prog3.program_id), pkg1)
    assert queued.item_id == again.item_id, "an unfinished package item is reused, never duplicated"

    # H4: a pause requested while a run is in flight is honoured between packages.
    h4 = Harness(root / "h4", proposals=[three()])
    prog4 = h4.sup.start_program("Harden alpha, beta, gamma.")
    h4.driver.on_call = lambda: h4.sup.pause(prog4.program_id, "pause mid-run")
    h4.sup.run_program(prog4.program_id)
    paused = h4.sup.load(prog4.program_id)
    assert paused.status == PAUSED and len(h4.driver.calls) == 1
    assert paused.packages[0].state == P_ACCEPTED, "the in-flight package still completes"


# --- I: scheduled cap and program budget are distinct -------------------


def scenario_I(root: Path) -> None:
    h = Harness(root / "cap", daily_cap=1)
    # a supplied plan longer than the package budget: the budget, not the plan, stops the run
    prog = h.sup.start_program(
        "Harden alpha, beta, gamma.", budget=RunBudget(max_packages=2), plan=_plan_of(three())
    )
    m1 = h.worker.backlog.add(description="Manual maintenance one", test_targets=["tests/t.py"])
    m2 = h.worker.backlog.add(description="Manual maintenance two", test_targets=["tests/t.py"])

    first = h.worker.run()
    assert [i for i, _ in first.processed] == [m1.item_id]
    assert first.stopped_because == "daily cap reached"
    assert h.worker.backlog.get(m2.item_id).status == bl.PENDING
    assert h.driver.count("p1") == 0, "the scheduled worker does not advance programs"

    h.sup.run_program(prog.program_id)  # daily cap is exhausted, program still runs
    stopped = h.sup.load(prog.program_id)
    assert stopped.status == BUDGET_EXHAUSTED and "max work packages" in stopped.status_reason
    assert [h.driver.count(p) for p in ("p1", "p2", "p3")] == [1, 1, 0]
    assert h.worker._count_today() == 1, "program packages never consume the daily cap"
    assert h.worker.backlog.get(m2.item_id).status == bl.PENDING

    try:
        h.sup.resume(prog.program_id)
    except SupervisorError:
        pass
    else:
        raise AssertionError("resume must refuse an exhausted budget")

    h.sup.extend_budget(prog.program_id, max_packages=3)

    try:
        h.sup.extend_budget(prog.program_id, max_packages=1)
    except SupervisorError:
        pass
    else:
        raise AssertionError("budgets can only be raised")

    h.sup.resume(prog.program_id)
    h.sup.run_program(prog.program_id)
    assert h.sup.load(prog.program_id).status == COMPLETED and h.driver.count("p3") == 1

    # elapsed-time budget
    clock = {"t": 1000.0}
    h2 = Harness(root / "time", proposals=[three()], now_fn=lambda: clock["t"])
    h2.driver.on_call = lambda: clock.__setitem__("t", clock["t"] + 4000.0)
    prog2 = h2.sup.start_program("g", budget=RunBudget(max_elapsed_seconds=5000.0))
    h2.sup.run_program(prog2.program_id)
    timed = h2.sup.load(prog2.program_id)
    assert timed.status == BUDGET_EXHAUSTED and "elapsed" in timed.status_reason
    assert h2.driver.count("p2") == 1 and h2.driver.count("p3") == 0
    assert timed.usage.elapsed_seconds >= 8000.0

    # provider-call budget: stops BEFORE starting a package it cannot afford (no half-run)
    h3 = Harness(root / "calls", proposals=[three()])
    prog3 = h3.sup.start_program("g", budget=RunBudget(max_provider_calls=6))
    h3.sup.run_program(prog3.program_id)
    limited = h3.sup.load(prog3.program_id)
    assert limited.status == BUDGET_EXHAUSTED and "provider calls" in limited.status_reason
    assert h3.driver.count("p1") == 1 and h3.driver.count("p2") == 0
    assert limited.packages[1].state == P_PLANNED, "unstarted work is left intact"

    # correction budget: no more than the configured number of corrections
    h4 = Harness(
        root / "corr",
        script={"p1": ["BLOCK:alpha failing 1", "BLOCK:alpha failing 2"]},
        proposals=[three()[:1]],
    )
    prog4 = h4.sup.start_program("g", budget=RunBudget(max_correction_cycles=0))
    h4.sup.run_program(prog4.program_id)
    assert h4.driver.count("p1") == 1, "no correction budget => no correction"
    assert h4.sup.load(prog4.program_id).status == NEEDS_HUMAN


# --- J: quota states are honest ----------------------------------------


def scenario_J(root: Path) -> None:
    board = QuotaBoard(root / "quota.json")
    assert set(board.levels().values()) == {ProviderQuota.UNKNOWN}, "no telemetry => UNKNOWN, never NORMAL"

    empty_sessions = root / "no_sessions"
    empty_sessions.mkdir()
    level, reason = codex_quota_probe(empty_sessions)
    assert level is ProviderQuota.UNKNOWN and reason
    board.refresh_from_telemetry(empty_sessions)
    assert board.level(Provider.CLAUDE) is ProviderQuota.UNKNOWN, "Claude has no telemetry source"
    assert board.level(Provider.CODEX) is ProviderQuota.UNKNOWN

    h = Harness(root / "h")
    status = h.worker.status()["quota"]
    assert status["claude"]["level"] == "unknown" and status["codex"]["level"] == "unknown"

    # UNKNOWN reduces no capability: same routes as NORMAL for the same task.
    routes = {}

    for name, levels in (
        ("unknown", {Provider.CLAUDE: ProviderQuota.UNKNOWN, Provider.CODEX: ProviderQuota.UNKNOWN}),
        ("normal", {Provider.CLAUDE: ProviderQuota.NORMAL, Provider.CODEX: ProviderQuota.NORMAL}),
    ):
        orch = DevOrchestrator(root, root / f"orch_{name}")
        task = orch.prepare_task(
            description="Refactor the scheduler tick loop.",
            difficulty=Difficulty.SERIOUS,
            previous_owner=Provider.CODEX,
            quota_levels=levels,
        )
        routes[name] = (task.implementer_model, task.reviewer_model)

    assert routes["unknown"] == routes["normal"]

    # CONSTRAINED may conserve a routine implementer but never the reviewer or a security route.
    orch = DevOrchestrator(root, root / "orch_c")
    constrained = orch.prepare_task(
        description="Rename a private helper.", difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CODEX,
        spec=TaskSpec(allowed_paths=("core/security/scanner.py",), test_targets=("tests/t.py",)),
        quota_levels={Provider.CLAUDE: ProviderQuota.CONSTRAINED, Provider.CODEX: ProviderQuota.CONSTRAINED},
    )
    orch_n = DevOrchestrator(root, root / "orch_n")
    normal = orch_n.prepare_task(
        description="Rename a private helper.", difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CODEX,
        spec=TaskSpec(allowed_paths=("core/security/scanner.py",), test_targets=("tests/t.py",)),
        quota_levels={Provider.CLAUDE: ProviderQuota.NORMAL, Provider.CODEX: ProviderQuota.NORMAL},
    )
    assert constrained.reviewer_model == normal.reviewer_model, "review is never downgraded to save quota"
    assert constrained.implementer_model == normal.implementer_model, "security work is never downgraded"


# --- K: an unavailable provider is never silently replaced ---------------


def scenario_K(root: Path) -> None:
    h = Harness(root / "k1", proposals=[three()])
    prog = h.sup.start_program("Harden alpha, beta, gamma.")
    h.worker.quota.set(Provider.CODEX, ProviderQuota.EXHAUSTED, reason="owner test", source="owner")
    report = h.sup.run_program(prog.program_id)

    assert "provider unavailable: codex" in report.stopped_because
    assert not h.driver.calls, "no work, and no review by a substitute, while a provider is out"
    assert all(i.package_id != "p1" for i in h.worker.backlog.all()), "nothing was even queued"
    assert h.sup.load(prog.program_id).packages[0].state == P_PLANNED
    assert h.sup.load(prog.program_id).status == ACTIVE, "state preserved, program stays resumable"

    # scheduled maintenance is held the same way
    m = h.worker.backlog.add(description="Manual maintenance", test_targets=["tests/t.py"])
    held = h.worker.run()
    assert "provider unavailable" in held.stopped_because and not h.driver.calls
    assert h.worker.backlog.get(m.item_id).status == bl.PENDING

    # the provider comes back: the same program continues exactly where it was
    h.worker.quota.clear(Provider.CODEX)
    h.sup.run_program(prog.program_id)
    assert h.sup.load(prog.program_id).status == COMPLETED

    # a provider hitting its limit mid-package defers the package (not a failure)
    h2 = Harness(root / "k2", script={"p1": ["EXHAUST:claude"]}, proposals=[three()[:2]])
    prog2 = h2.sup.start_program("Harden alpha and beta.")
    r2 = h2.sup.run_program(prog2.program_id)
    mid = h2.sup.load(prog2.program_id)
    assert r2.executed == [("p1", bl.DEFERRED)] and "deferred" in r2.stopped_because
    assert mid.packages[0].state == P_PLANNED and mid.usage.correction_cycles == 0
    assert h2.worker.quota.level(Provider.CLAUDE) is ProviderQuota.EXHAUSTED
    assert h2.sup.load(prog2.program_id).status == ACTIVE

    h2.sup.run_program(prog2.program_id)  # still exhausted: nothing runs
    assert h2.driver.count("p1") == 1

    h2.worker.quota.clear(Provider.CLAUDE)
    h2.sup.run_program(prog2.program_id)
    assert h2.sup.load(prog2.program_id).status == COMPLETED
    assert h2.driver.count("p1") == 2 and h2.driver.count("p2") == 1

    # an owner-set EXHAUSTED level is never overwritten by automatic sources
    board = QuotaBoard(root / "owner_quota.json")
    board.set(Provider.CODEX, ProviderQuota.EXHAUSTED, reason="owner", source="owner")
    assert board.mark_exhausted(Provider.CODEX, "error") is False
    board.refresh_from_telemetry(root / "no_sessions")
    assert board.entry(Provider.CODEX)["source"] == "owner"


# --- L: owner-approval work pauses safely -------------------------------


def scenario_L(root: Path) -> None:
    orch = DevOrchestrator(root, root / "orch")
    gated = orch.prepare_task(description="Deploy to production and push to origin.", difficulty=Difficulty.ROUTINE)
    assert gated.status is TaskStatus.NEEDS_HUMAN

    proposals = [[
        pkg("p1", "Alpha parser hardening", "Harden the alpha parser against truncated input."),
        pkg("p2", "Rotate provider credentials", "Rotate the API key stored for the provider and purchase more credits.",
            allowed_paths=["core/keys.py"]),
        pkg("p3", "Gamma exporter batching", "Batch the gamma exporter writes into groups."),
        pkg("p4", "Beta follow up", "Follow up on the rotated provider credentials in beta.", ("p2",)),
    ]]
    h = Harness(root / "l", proposals=proposals)
    prog = h.sup.start_program("Harden alpha, rotate keys, batch gamma.")
    assert prog.packages[1].work_package().needs_owner and prog.packages[1].work_package().owner_reasons

    h.sup.run_program(prog.program_id)
    stopped = h.sup.load(prog.program_id)
    assert stopped.status == NEEDS_HUMAN and "p2" in stopped.status_reason
    assert [c["package_id"] for c in h.driver.calls] == ["p1"], "nothing gated was queued or run"
    assert all(i.package_id != "p2" for i in h.worker.backlog.all())
    assert stopped.packages[1].state == P_NEEDS_HUMAN
    assert any(n["level"] == "attention" for n in _notes(h.worker))

    h.sup.skip_package(prog.program_id, "p2", "owner declines the rotation")
    h.sup.resume(prog.program_id)
    h.sup.run_program(prog.program_id)
    done = h.sup.load(prog.program_id)
    states = {p.package_id: p.state for p in done.packages}
    assert states == {"p1": P_ACCEPTED, "p2": P_SKIPPED, "p3": P_ACCEPTED, "p4": P_SKIPPED}, states
    assert done.status == COMPLETED

    # ordinary code/test/retry work needs no approval
    assert not h.sup.load(prog.program_id).packages[0].work_package().needs_owner


def _notes(worker: AutonomousWorker) -> list[dict[str, Any]]:
    if not worker.notify_path.exists():
        return []
    return [json.loads(line) for line in worker.notify_path.read_text(encoding="utf-8").splitlines()]


# --- M: a fresh session can operate the bridge from the README ----------


README_MUST_MENTION = {
    "architecture": ("controller", "worktree"),
    "host supervisor": ("supervisor",),
    "how claude and codex are invoked": ("stdin", "--output-schema", "--json-schema"),
    "start the worker": ("autonomous_worker.py run",),
    "queue a manual task": ("autonomous_worker.py add",),
    "start an autonomous program": ("supervisor.py program start",),
    "task states": ("needs_human", "deferred", "crashed"),
    "difficulty levels": ("scout", "critical"),
    "difficulty classification": ("effective_difficulty", "floor"),
    "model routing": ("gpt-5.6", "opus"),
    "implementer/reviewer": ("independent", "reviewer"),
    "worktree isolation": ("vector-dev/",),
    "review/fix/re-review": ("re-review",),
    "escalation": ("escalat",),
    "limits": ("daily cap", "max_packages"),
    "scheduled worker": ("Task Scheduler", "logged in"),
    "restart recovery": ("restart",),
    "logs and evidence": (".state", "notifications.jsonl"),
    "status": ("status",),
    "pause/stop": ("pause", "STOP"),
    "owner approval": ("owner approval", "push"),
    "quota": ("UNKNOWN", "EXHAUSTED"),
}


def scenario_M(root: Path) -> None:
    text = README.read_text(encoding="utf-8")
    lowered = text.lower()
    missing = [
        f"{topic}: {needle}"
        for topic, needles in README_MUST_MENTION.items()
        for needle in needles
        if needle.lower() not in lowered
    ]
    assert not missing, f"README does not cover: {missing}"
    assert len(text.splitlines()) > 150


# --- N: accepted work is integrated before dependents build on it --------


def scenario_N(root: Path) -> None:
    h = Harness(root, proposals=[three()])
    h.integration_override = {"p2": "conflict"}
    prog = h.sup.start_program("Harden alpha, beta, gamma.")
    h.sup.run_program(prog.program_id)
    stopped = h.sup.load(prog.program_id)

    assert stopped.status == NEEDS_HUMAN and "p2 could not be integrated (conflict)" in stopped.status_reason
    states = {p.package_id: p.state for p in stopped.packages}
    assert states == {"p1": P_ACCEPTED, "p2": P_NEEDS_HUMAN, "p3": P_PLANNED}, states
    assert [e["package_id"] for e in stopped.ledger] == ["p1"], "unintegrated work is not 'accepted'"
    assert h.driver.count("p3") == 0, "nothing builds on work that did not integrate"


# --- O: Codex's Windows sandbox cannot safely create NEW files -------------


def scenario_O(root: Path) -> None:
    # O1: a package whose allowed file paths do not exist yet is implemented by
    # Claude even if the plan preferred Codex; Codex still reviews (never the same provider).
    new_file = pkg("p1", "Alpha parser hardening", "Harden the alpha parser against truncated input.",
                   preferred_owner="codex", preferred_owner_reason="mechanical")
    h = Harness(root / "o1", proposals=[[new_file]])
    prog = h.sup.start_program("Harden alpha.")
    h.sup.run_program(prog.program_id)
    assert h.driver.calls[0]["kw"]["previous_owner"] is Provider.CODEX, "claude implements new-file work"

    # O2: existing files only -> the normal ownership rules apply (codex may implement).
    h2 = Harness(root / "o2", proposals=[[new_file]])
    _commit_files(h2, "core/p1.py", "tests/test_p1.py")
    prog2 = h2.sup.start_program("Harden alpha.")
    h2.sup.run_program(prog2.program_id)
    assert h2.driver.calls[0]["kw"]["previous_owner"] is Provider.CLAUDE

    # O3: directory allowance hides new files -> a PermissionError crash gets ONE
    # correction with Claude as implementer instead of stopping the program.
    dir_pkg = pkg("p1", "Alpha parser hardening", "Harden the alpha parser against truncated input.",
                  allowed_paths=["core/", "tests/"])
    h3 = Harness(root / "o3", script={"p1": ["CRASH_PERMISSION"]}, proposals=[[dir_pkg]])
    prog3 = h3.sup.start_program("Harden alpha.")
    h3.sup.run_program(prog3.program_id)
    done = h3.sup.load(prog3.program_id)
    assert done.status == COMPLETED and h3.driver.count("p1") == 2
    assert h3.driver.calls[1]["kw"]["previous_owner"] is Provider.CODEX, "retry is implemented by claude"
    assert done.usage.correction_cycles == 1
    crashed = [i for i in h3.worker.backlog.all() if i.status == bl.CRASHED]
    assert crashed and "Codex sandbox" in crashed[0].result_note

    # O4: the fallback is bounded: a second PermissionError stops for the owner.
    h4 = Harness(root / "o4", script={"p1": ["CRASH_PERMISSION", "CRASH_PERMISSION"]}, proposals=[[dir_pkg]])
    prog4 = h4.sup.start_program("Harden alpha.")
    h4.sup.run_program(prog4.program_id)
    assert h4.sup.load(prog4.program_id).status == NEEDS_HUMAN and h4.driver.count("p1") == 2


# --- P: repair of the demonstrated canary defects ---------------------------

SECRET = "sk-abcdefghijklmnopqrstuvwxyz0123456789"


def scenario_P(root: Path) -> None:
    from backlog import BacklogStore
    from planner import PlannerError, validate_plan
    from runner import invalid_test_target_reason

    good = pkg("p1", "Alpha parser hardening", "Harden the alpha parser against truncated input.")
    bad_target = dict(good, test_targets=["tests/ -k uploader"])

    # P1. Embedded CLI arguments can never masquerade as a path.
    planning = PlanningInput(goal="g", repo_state={"head": "x"})
    for embedded in (
        "tests/ -k uploader",
        "tests/test_x.py -k 'a or b'",
        "-k uploader",
        "--maxfail=1",
        "tests/a.py tests/b.py",
        "tests/a.py;calc",
        "tests/a.py::test_x -x",
        "/abs/tests/a.py",
        "../escape.py",
    ):
        rejected = validate_plan([dict(good, test_targets=[embedded])], planning)
        assert rejected.packages == [] and rejected.invalid, embedded
        assert "invalid test target" in rejected.invalid[0][1], embedded

    normalised = validate_plan([dict(good, test_targets=["tests\\test_p1.py", "tests/test_q.py::test_y[a-1]"])], planning)
    assert normalised.packages[0].test_targets == ("tests/test_p1.py", "tests/test_q.py::test_y[a-1]")
    assert invalid_test_target_reason("tests/test_p1.py") is None

    # P2. A malformed proposal gets ONE repair round with the validator's own words.
    h = Harness(root / "p2", proposals=[[bad_target], [good]])
    program = h.sup.start_program("Harden alpha.")
    assert [p.package_id for p in program.packages] == ["p1"]
    assert len(h.planning_inputs) == 2 and h.planning_inputs[0].feedback == []
    assert "invalid test target" in h.planning_inputs[1].feedback[0]
    assert "tests/ -k uploader" in h.planning_inputs[1].feedback[0]
    assert "NEVER put pytest arguments" in __import__("planner").build_planning_prompt(h.planning_inputs[1])
    assert "REJECTED BY THE VALIDATOR" in __import__("planner").build_planning_prompt(h.planning_inputs[1])
    assert program.usage.provider_calls == 2, "both proposer calls are counted"
    h.sup.run_program(program.program_id)
    assert h.sup.load(program.program_id).status == COMPLETED

    # P3. Still malformed after the repair round -> fail closed, nothing persisted or run.
    h2 = Harness(root / "p3", proposals=[[bad_target], [bad_target]])
    try:
        h2.sup.start_program("Harden alpha.")
    except SupervisorError as exc:
        assert "still invalid after one repair round" in str(exc)
    else:
        raise AssertionError("a plan that is still malformed must not start")
    assert h2.sup.list_programs() == [] and not h2.driver.calls
    assert len(h2.planning_inputs) == 2, "exactly one repair round, no more"

    # P4. Malformed manual items and direct driver calls are refused at the door as well.
    try:
        BacklogStore(root / "p4.json").add(description="x task", test_targets=["tests/ -k y"])
    except ValueError as exc:
        assert "Invalid pytest target" in str(exc)
    else:
        raise AssertionError("backlog must refuse an embedded-argument target")

    from dev_driver import run_task

    try:
        run_task(root, description="x", test_targets=["tests/a.py -k y"])
    except ValueError as exc:
        assert "Invalid pytest target" in str(exc)
    else:
        raise AssertionError("run_task must refuse before creating any worktree")

    # P5. A pytest exit-4 specification failure skips the pointless correction, reaches
    # the re-plan with bounded diagnostic evidence, and the re-plan can fix the target.
    usage_error = "ERROR: file or directory not found: tests/ -k uploader " + "x" * 60000 + f" token {SECRET}"
    replan = [pkg("p9", "Delta table driven lexer", "Replace hand rolled alpha scanning with a table driven lexer.")]
    h3 = Harness(
        root / "p5",
        script={"p1": [f"BLOCK_SPEC:{usage_error}"]},
        proposals=[[good], replan],
    )
    prog = h3.sup.start_program("Harden alpha.")
    h3.sup.run_program(prog.program_id)
    done = h3.sup.load(prog.program_id)
    assert h3.driver.count("p1") == 1, "a wrong test SPEC is not 'corrected' by re-running the same package"
    assert done.usage.correction_cycles == 0 and done.usage.replans == 1
    assert done.status == COMPLETED and h3.driver.count("r1-p9") == 1
    blocker = h3.planning_inputs[1].blockers[0]
    assert "category=test_spec kind=test_spec exit_code=4" in blocker.evidence
    assert "file or directory not found" in blocker.evidence
    assert len(blocker.evidence) <= 1100, len(blocker.evidence)
    assert SECRET not in blocker.evidence, "secrets never reach planner evidence"
    from planner import build_planning_prompt

    prompt = build_planning_prompt(h3.planning_inputs[1])
    assert "kind=test_spec" in prompt and SECRET not in prompt and len(prompt) <= 14000
    on_disk = (root / "p5" / "state" / "supervisor" / "programs" / f"{prog.program_id}.json").read_text(encoding="utf-8")
    assert SECRET not in on_disk and "x" * 3000 not in on_disk, "persisted evidence is redacted and bounded"
    item = next(i for i in h3.worker.backlog.all() if i.package_id == "p1")
    assert item.failure_evidence["kind"] == "test_spec" and len(item.failure_evidence["tail"]) <= 1300
    assert SECRET not in json.dumps(item.failure_evidence)
    assert done.ledger[0]["package_id"] == "r1-p9" and len(done.ledger) == 1, "blocked work never enters the ledger"

    # P5b. Secrets in a blocker NOTE (not just test output) never reach state or planner prompts.
    leaky_note = f"BLOCK:Reviewer found hardcoded credential {SECRET} in the alpha parser"
    hl = Harness(root / "p5b", script={"p1": [leaky_note, leaky_note]}, proposals=[[good], replan])
    pl = hl.sup.start_program("Harden alpha.")
    hl.sup.run_program(pl.program_id)
    state_text = (root / "p5b" / "state" / "supervisor" / "programs" / f"{pl.program_id}.json").read_text(encoding="utf-8")
    backlog_text = (root / "p5b" / "state" / "worker" / "backlog.json").read_text(encoding="utf-8")
    assert SECRET not in state_text and SECRET not in backlog_text
    assert all(SECRET not in build_planning_prompt(pi) for pi in hl.planning_inputs)

    # P5c. Malformed node ids are refused too (empty segments, stray colons).
    for node in ("tests/a.py::", "tests/a.py:::x", "tests/a.py::t[", "::x"):
        assert validate_plan([dict(good, test_targets=[node])], planning).packages == [], node
    assert validate_plan([dict(good, test_targets=["tests/a.py::TestK::test_y[a:b]"])], planning).ids == ["p1"]

    # P6. An implementation assertion failure is a DIFFERENT kind: it IS corrected once,
    # the correction is shown the evidence, and only then does the re-plan happen.
    failing = "FAILED tests/t.py::test_x - assert 1 == 2\n1 failed"
    h4 = Harness(
        root / "p6",
        script={"p1": [f"BLOCK_TEST:{failing}", f"BLOCK_TEST:{failing}"]},
        proposals=[[good], replan],
    )
    prog4 = h4.sup.start_program("Harden alpha.")
    h4.sup.run_program(prog4.program_id)
    after = h4.sup.load(prog4.program_id)
    assert h4.driver.count("p1") == 2 and after.usage.correction_cycles == 1, "correction still happens"
    retry_text = h4.driver.calls[1]["description"]
    assert "category=test_failure kind=implementation exit_code=1" in retry_text
    assert "assert 1 == 2" in retry_text, "the correction is told what actually failed"
    replan_blocker = h4.planning_inputs[1].blockers[0]
    assert "kind=implementation" in replan_blocker.evidence and "exit_code=1" in replan_blocker.evidence
    assert "kind=test_spec" not in replan_blocker.evidence
    assert after.usage.replans == 1 and after.status == COMPLETED

    # P7. Provider-call accounting reflects invocations that actually happened.
    h5 = Harness(
        root / "p7",
        script={"p1": ["BLOCK_TEST:1 failed", "PASS"]},
        proposals=[[good, pkg("p2", "Beta scheduler jitter", "Add bounded jitter to the beta scheduler tick.")]],
    )
    prog5 = h5.sup.start_program("Harden alpha and beta.")
    h5.sup.run_program(prog5.program_id)
    items = {(i.package_id, i.status): i.provider_calls for i in h5.worker.backlog.all()}
    assert items[("p1", bl.BLOCKED)] == 1, "implementer only; the reviewer was never reached"
    assert items[("p1", bl.PASSED)] == 2 and items[("p2", bl.PASSED)] == 2
    assert h5.sup.load(prog5.program_id).usage.provider_calls == 1 + 1 + 2 + 2, "planner + actual invocations"

    crash = Harness(root / "p7b", script={"p1": ["CRASH"]}, proposals=[[good]])
    cp = crash.sup.start_program("Harden alpha.")
    crash.sup.run_program(cp.program_id)
    assert crash.worker.backlog.all()[0].provider_calls == AutonomousWorker.CRASH_PROVIDER_CALLS, (
        "a crash returns no task: what ran is unknown, so it is counted conservatively"
    )

    # ... while the budget check stays conservative: a package that could exceed the
    # remaining provider-call budget is never started, however few calls happen to be used.
    tight = Harness(root / "p7c", proposals=[three()])
    tp = tight.sup.start_program("g", budget=RunBudget(max_provider_calls=4))
    tight.sup.run_program(tp.program_id)
    limited = tight.sup.load(tp.program_id)
    assert limited.status == BUDGET_EXHAUSTED and not tight.driver.calls
    assert limited.usage.provider_calls <= 4

    # P8. Reviewer-not-reached stays fail-closed: nothing committed, integrated or accepted.
    h6 = Harness(root / "p8", script={"p1": ["BLOCK_SPEC:ERROR: file or directory not found: bad -k"]},
                 proposals=[[good]])
    p8 = h6.sup.start_program("Harden alpha.")
    h6.sup.run_program(p8.program_id)
    final = h6.sup.load(p8.program_id)
    assert final.status == NEEDS_HUMAN and final.ledger == [] and not final.base_ref
    assert all(not i.commit and not i.integration for i in h6.worker.backlog.all())

    # P8b. Planning and re-planning are provider calls and can never push a program past its
    # budget (found by the independent Codex review of this repair).
    def budgeted(name: str, spec_calls: int, replan_proposals: list, max_calls: int = 5) -> tuple[Any, Any]:
        hb = Harness(
            root / name,
            script={"p1": ["BLOCK_SPEC:ERROR: file or directory not found: x -k y"]},
            proposals=[[good], *replan_proposals],
        )
        hb.driver.spec_calls = spec_calls
        pb = hb.sup.start_program("Harden alpha.", budget=RunBudget(max_provider_calls=max_calls))
        hb.sup.run_program(pb.program_id)
        return hb, hb.sup.load(pb.program_id)

    # one call left -> a single proposal is allowed and the budget lands exactly on the limit
    hb1, ok = budgeted("p8b1", 3, [replan])
    assert ok.usage.provider_calls == 5 and hb1.planning_inputs[1].max_calls == 1
    assert ok.usage.provider_calls <= ok.budget.max_provider_calls
    assert ok.status == BUDGET_EXHAUSTED, "the re-planned package cannot be afforded, so it is not started"
    assert hb1.driver.count("r1-p9") == 0 and ok.packages[-1].state == P_PLANNED

    # one call left and that proposal is malformed -> no repair round is affordable: fail closed
    hb2, broke = budgeted("p8b2", 3, [[dict(replan[0], test_targets=["tests/ -k y"])]])
    assert broke.status == NEEDS_HUMAN and "no provider-call budget remains" in broke.status_reason
    assert broke.usage.provider_calls == 5 and len(hb2.planning_inputs) == 2

    # zero calls left -> no planner call at all; resumable after extend + retry
    hb3, dry = budgeted("p8b3", 4, [replan])
    assert dry.status == BUDGET_EXHAUSTED and len(hb3.planning_inputs) == 1
    assert dry.usage.provider_calls == 5 <= dry.budget.max_provider_calls
    assert "extend" in dry.status_reason

    # P9. Existing bounds are unchanged.
    from supervisor import Program

    assert Program(program_id="x", goal="g").max_replans == 1
    assert RunBudget().max_correction_cycles == 4 and RunBudget().max_packages == 6
    assert AutonomousWorker.CRASH_PROVIDER_CALLS == 2
    assert issubclass(PlannerError, RuntimeError)


# --- Q: programs chain (base on integration, inherit the accepted ledger) ----


def scenario_Q(root: Path) -> None:
    # No integration branch yet: the first program is cut from live HEAD, as before.
    h = Harness(root / "q1", proposals=[three()[:1]])
    first = h.sup.start_program("Harden alpha.")
    assert first.base_ref == "" and first.ledger == []
    h.sup.run_program(first.program_id)
    done = h.sup.load(first.program_id)
    assert done.status == COMPLETED and len(done.ledger) == 1 and done.base_ref == "vector-integration"

    # A later program starts from vector-integration (once it exists) and inherits what
    # earlier programs got accepted, so the planner is told not to redo it.
    subprocess.run(["git", "-C", str(h.repo), "branch", "vector-integration"], check=True, capture_output=True)
    h.proposals.append([pkg("p7", "Zeta queue draining", "Drain the zeta queue with bounded batches.")])
    second = h.sup.start_program("Harden zeta.")
    assert second.base_ref == "vector-integration"
    assert [e["package_id"] for e in second.ledger] == ["p1"], "accepted work is inherited, not re-planned"
    assert [e.package_id for e in h.planning_inputs[-1].ledger] == ["p1"]
    h.sup.run_program(second.program_id)
    call = h.driver.calls[-1]
    assert call["package_id"] == "p7" and call["kw"].get("base_ref") == "vector-integration"
    assert len(h.sup.load(second.program_id).ledger) == 2

    # inherit_accepted=False keeps a program's ledger clean.
    h.proposals.append([pkg("p8", "Eta cache warming", "Warm the eta cache lazily on first read.")])
    third = h.sup.start_program("Harden eta.", inherit_accepted=False)
    assert third.ledger == []


# --- R: canonical routing policy (POLICY.md sec. 1-8) -----------------------


def scenario_R(root: Path) -> None:
    from models import TaskCategory
    from router import (
        ModelRouter,
        default_difficulty_for_category,
        quota_band_for_percent,
    )

    router = ModelRouter()

    # 1-2. The ladders, exactly as the owner wrote them.
    codex = {
        Difficulty.SCOUT: ("gpt-5.6-luna", None),
        Difficulty.ROUTINE: ("gpt-5.6-terra", None),
        Difficulty.SERIOUS: ("gpt-5.6-sol", None),
        Difficulty.HARD: ("gpt-6-astra", "low"),
        Difficulty.CRITICAL: ("gpt-6-astra", "medium"),
    }
    claude = {
        Difficulty.SCOUT: ("haiku", None),
        Difficulty.ROUTINE: ("sonnet", None),
        Difficulty.SERIOUS: ("sonnet", "high"),
        Difficulty.HARD: ("sonnet", "high"),
        Difficulty.CRITICAL: ("opus", None),
    }

    for level, (model, effort) in codex.items():
        choice = router.choose_implementer(provider=Provider.CODEX, difficulty=level)
        assert choice.model == model and (effort is None or choice.effort == effort), (level, choice)

    for level, (model, effort) in claude.items():
        choice = router.choose_implementer(provider=Provider.CLAUDE, difficulty=level)
        assert choice.model == model and (effort is None or choice.effort == effort), (level, choice)

    assert router.choose_implementer(provider=Provider.CLAUDE, difficulty=Difficulty.ROUTINE).model != "opus"

    # 3-4. Categories: normal difficulty per category, and the floors (which only ever raise).
    normal = {
        TaskCategory.EXPLORATION: Difficulty.SCOUT, TaskCategory.DOCUMENTATION: Difficulty.SCOUT,
        TaskCategory.TRIVIAL_EDIT: Difficulty.SCOUT, TaskCategory.IMPLEMENTATION: Difficulty.ROUTINE,
        TaskCategory.DEBUGGING: Difficulty.ROUTINE, TaskCategory.TEST_REPAIR: Difficulty.ROUTINE,
        TaskCategory.INTEGRATION: Difficulty.SERIOUS, TaskCategory.ARCHITECTURE: Difficulty.SERIOUS,
        TaskCategory.SECURITY_SENSITIVE: Difficulty.HARD,
    }
    assert {c: default_difficulty_for_category(c) for c in TaskCategory} == normal
    assert router.apply_category_floor(Difficulty.SCOUT, TaskCategory.ARCHITECTURE) is Difficulty.SERIOUS
    assert router.apply_category_floor(Difficulty.ROUTINE, TaskCategory.SECURITY_SENSITIVE) is Difficulty.HARD
    assert router.apply_category_floor(Difficulty.CRITICAL, TaskCategory.SECURITY_SENSITIVE) is Difficulty.CRITICAL
    assert router.apply_category_floor(Difficulty.CRITICAL, TaskCategory.EXPLORATION) is Difficulty.CRITICAL
    assert infer_difficulty("Update the README documentation for the queue.").effective in (
        Difficulty.SCOUT, Difficulty.ROUTINE
    )

    # 8. Quota band edges: NORMAL >=60, CONSERVE 30-60, RESERVE 15-30, EMERGENCY <15, UNKNOWN none.
    for percent, band in (
        (100, QuotaBand.NORMAL), (60, QuotaBand.NORMAL), (59.9, QuotaBand.CONSERVE),
        (30, QuotaBand.CONSERVE), (29.9, QuotaBand.RESERVE), (15, QuotaBand.RESERVE),
        (14.9, QuotaBand.EMERGENCY), (1, QuotaBand.EMERGENCY), (None, QuotaBand.UNKNOWN),
    ):
        assert quota_band_for_percent(percent) is band, (percent, band)

    # 5. Reviewer strength follows the UNCONSERVED difficulty; only the implementer is conserved.
    # CONSERVE/RESERVE cap the IMPLEMENTER'S tier but never flip ownership or weaken review.
    for band in (QuotaBand.CONSERVE, QuotaBand.RESERVE):
        decision = router.route(
            description="Implement the ordinary feature as described.",
            base_difficulty=Difficulty.SERIOUS, previous_owner=Provider.CODEX,
            quota_bands={Provider.CLAUDE: band, Provider.CODEX: QuotaBand.NORMAL},
        )
        assert decision.owner is Provider.CLAUDE, band
        assert decision.reviewer_model.model == "gpt-5.6-sol", "review is never weakened to save quota"

    # EMERGENCY flips OWNERSHIP itself (sec. 9: EMERGENCY is not spent as implementer while
    # the other provider has capacity), not just the implementer's tier.
    emergency = router.route(
        description="Implement the ordinary feature as described.",
        base_difficulty=Difficulty.SERIOUS, previous_owner=Provider.CODEX,
        quota_bands={Provider.CLAUDE: QuotaBand.EMERGENCY, Provider.CODEX: QuotaBand.NORMAL},
    )
    assert emergency.owner is Provider.CODEX and "codex-first" in emergency.ownership_note
    assert emergency.reviewer_model.model == "sonnet", "review is never weakened to save quota"

    # 8b. Hard/critical/security work is never downgraded to save quota.
    for level in (Difficulty.HARD, Difficulty.CRITICAL):
        decision = router.route(
            description="Refactor the scheduler internals.", base_difficulty=level,
            previous_owner=Provider.CODEX,
            quota_bands={Provider.CLAUDE: QuotaBand.RESERVE, Provider.CODEX: QuotaBand.NORMAL},
        )
        assert decision.implementer_model.model == claude[level][0]

    # 9-10. Codex EMERGENCY => Claude-first; the review that needs Codex is deferred.
    decision = router.route(
        description="Fix a normal parser bug.", base_difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,  # the 50/50 scheduler would choose Codex
        quota_bands={Provider.CODEX: QuotaBand.EMERGENCY, Provider.CLAUDE: QuotaBand.NORMAL},
    )
    assert decision.owner is Provider.CLAUDE and decision.reviewer is Provider.CODEX
    assert decision.review_deferred and "claude-first" in decision.ownership_note

    # ... and the mirror image (Claude EMERGENCY => Codex-first, Claude's review deferred).
    mirror = router.route(
        description="Fix a normal parser bug.", base_difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CODEX,  # scheduler would choose Claude
        quota_bands={Provider.CLAUDE: QuotaBand.EMERGENCY, Provider.CODEX: QuotaBand.NORMAL},
    )
    assert mirror.owner is Provider.CODEX and mirror.review_deferred and "codex-first" in mirror.ownership_note

    # 11. Healthy quotas (or UNKNOWN): normal 50/50 alternation, nothing deferred.
    for bands in (
        {Provider.CODEX: QuotaBand.NORMAL, Provider.CLAUDE: QuotaBand.NORMAL},
        {Provider.CODEX: QuotaBand.UNKNOWN, Provider.CLAUDE: QuotaBand.UNKNOWN},
        {Provider.CODEX: QuotaBand.CONSERVE, Provider.CLAUDE: QuotaBand.RESERVE},
    ):
        first = router.route(description="Fix a bug.", base_difficulty=Difficulty.ROUTINE, previous_owner=None, quota_bands=bands)
        second = router.route(description="Fix a bug.", base_difficulty=Difficulty.ROUTINE, previous_owner=first.owner, quota_bands=bands)
        assert first.owner is Provider.CODEX and second.owner is Provider.CLAUDE
        assert not first.review_deferred and not first.ownership_note

    # Both in EMERGENCY: no forced flip (nobody better to give it to); the worker holds the work.
    both = router.route(
        description="Fix a bug.", base_difficulty=Difficulty.ROUTINE, previous_owner=Provider.CODEX,
        quota_bands={Provider.CODEX: QuotaBand.EMERGENCY, Provider.CLAUDE: QuotaBand.EMERGENCY},
    )
    assert both.owner is Provider.CLAUDE and both.ownership_note == ""

    # 7. Escalation: one bounded tier per allowed escalation, never past CRITICAL.
    assert router.escalate_difficulty(Difficulty.SERIOUS) is Difficulty.HARD
    assert router.escalate_difficulty(Difficulty.CRITICAL) is Difficulty.CRITICAL
    from models import DevTask as _Task

    assert _Task(description="x").max_escalations == 1


# --- S: WAITING_REVIEW while Codex is in EMERGENCY (POLICY.md sec. 10-11) -----


def scenario_S(root: Path) -> None:
    def make(name: str, script: dict[str, list[str]] | None = None, **kw: Any) -> tuple[Harness, Any]:
        packages = [
            pkg("p1", "Alpha parser hardening", "Harden the alpha parser against truncated input."),
            pkg("p2", "Beta scheduler jitter", "Add bounded jitter to the beta scheduler tick.", ("p1",)),
            pkg("p3", "Gamma exporter batching", "Batch the gamma exporter writes into groups."),
        ]
        h = Harness(root / name, script=script, proposals=[packages], **kw)
        h.worker.quota.set_band(Provider.CODEX, QuotaBand.EMERGENCY, reason="owner: ~1% weekly", source="owner")
        return h, h.sup.start_program("Harden alpha, beta and gamma.")

    # S1. p1 stops at WAITING_REVIEW; its dependent waits; the independent p3 is still delivered.
    h, prog = make("s1", {"p1": ["WAIT"]})
    report = h.sup.run_program(prog.program_id)
    state = h.sup.load(prog.program_id)
    assert state.status == WAITING_REVIEW, (state.status, state.status_reason)
    assert {p.package_id: p.state for p in state.packages} == {
        "p1": P_WAITING_REVIEW, "p2": P_PLANNED, "p3": P_ACCEPTED,
    }
    assert [c["package_id"] for c in h.driver.calls] == ["p1", "p3"], "p2 must not build on unreviewed work"
    assert [e["package_id"] for e in state.ledger] == ["p3"], "unreviewed work is not 'accepted'"
    p1_item = next(i for i in h.worker.backlog.all() if i.package_id == "p1")
    assert p1_item.status == bl.WAITING_REVIEW and not p1_item.commit and not p1_item.integration
    assert h.reviews == [] and state.usage.provider_calls == 1 + 1 + 2, "planner + p1 implementer + p3 (2)"
    assert "wait for an independent review" in state.status_reason and report.status == WAITING_REVIEW
    assert state.status != COMPLETED

    # S2. Still EMERGENCY: running again spends nothing and changes nothing.
    h.sup.run_program(prog.program_id)
    assert h.reviews == [] and h.sup.load(prog.program_id).status == WAITING_REVIEW
    assert len(h.driver.calls) == 2

    # S3. Restart while waiting (state is on disk), Codex recovers -> the review runs, p1 is
    # accepted and integrated, then its dependent p2 finally runs; the program completes.
    h.build()
    h.worker.quota.clear(Provider.CODEX)
    h.sup.run_program(prog.program_id)
    done = h.sup.load(prog.program_id)
    assert done.status == COMPLETED, (done.status, done.status_reason)
    assert h.reviews == [p1_item.task_id] and len(h.reviews) == 1
    assert [e["package_id"] for e in done.ledger] == ["p3", "p1", "p2"]
    assert h.worker.backlog.get(p1_item.item_id).commit and h.worker.backlog.get(p1_item.item_id).integration == "merged"
    assert done.usage.provider_calls == 1 + 1 + 2 + 1 + 2, "the resumed review adds only ITS call, not the implementer's again"
    assert h.driver.count("p1") == 1, "p1 is never re-implemented"

    # S4. The owner may spend the emergency reserve explicitly.
    h2, prog2 = make("s4", {"p1": ["WAIT"]})
    h2.sup.run_program(prog2.program_id)
    h2.sup.allow_emergency_review = True
    h2.sup.run_program(prog2.program_id)
    assert len(h2.reviews) == 1 and h2.sup.load(prog2.program_id).status == COMPLETED

    # ... but never an EXHAUSTED provider.
    h3, prog3 = make("s4b", {"p1": ["WAIT"]})
    h3.sup.run_program(prog3.program_id)
    h3.worker.quota.set(Provider.CODEX, ProviderQuota.EXHAUSTED, reason="owner", source="owner")
    h3.sup.allow_emergency_review = True
    h3.sup.run_program(prog3.program_id)
    assert h3.reviews == [] and h3.sup.load(prog3.program_id).status == WAITING_REVIEW

    # S5. A resumed review that finds a BLOCKER goes through the normal bounded correction path.
    h4, prog4 = make("s5", {"p1": ["WAIT"]})
    h4.sup.run_program(prog4.program_id)
    h4.worker.quota.clear(Provider.CODEX)
    h4.review_outcome = "BLOCK"
    h4.sup.run_program(prog4.program_id)
    after = h4.sup.load(prog4.program_id)
    assert h4.reviews and after.packages[0].corrections == 1, "one bounded correction after the rejected review"
    assert after.status == COMPLETED and h4.driver.count("p1") == 2, "the correction attempt ran and passed"

    # S6. The resumed review respects the provider-call budget (never overspends).
    h5, prog5 = make("s6", {"p1": ["WAIT"]})
    h5.sup.extend_budget(prog5.program_id, max_provider_calls=40)
    h5.sup.run_program(prog5.program_id)
    used = h5.sup.load(prog5.program_id).usage.provider_calls
    tight = h5.sup.load(prog5.program_id)
    tight.budget.max_provider_calls = used + 1  # cannot afford a worst-case review (4 calls)
    h5.sup.save(tight)
    h5.worker.quota.clear(Provider.CODEX)
    h5.sup.run_program(prog5.program_id)
    limited = h5.sup.load(prog5.program_id)
    assert limited.status == BUDGET_EXHAUSTED and h5.reviews == []
    assert limited.usage.provider_calls <= limited.budget.max_provider_calls


SCENARIOS: list[tuple[str, Callable[[Path], None]]] = [
    ("A planner decomposes a program", scenario_A),
    ("B safety floor upgrades an under-labelled task", scenario_B),
    ("C routine work avoids the strongest route", scenario_C),
    ("D/E claude-owned -> codex review, codex-owned -> claude review", scenario_D_E),
    ("F rejection -> bounded correction -> re-review", scenario_F),
    ("G persistent blocker -> re-plan once -> stop", scenario_G),
    ("H restart preserves program/task state", scenario_H),
    ("I scheduled cap vs program budget are distinct", scenario_I),
    ("J quota UNKNOWN is honest", scenario_J),
    ("K unavailable provider is never silently replaced", scenario_K),
    ("L owner-approval work pauses safely", scenario_L),
    ("O codex sandbox: new-file work goes to claude, permission crash gets one fallback", scenario_O),
    ("P canary repair: target validation, failure evidence, honest call accounting", scenario_P),
    ("Q programs chain: base on integration, inherit the accepted ledger", scenario_Q),
    ("R canonical routing policy: ladders, floors, bands, Claude-first", scenario_R),
    ("S WAITING_REVIEW during a Codex emergency: never a false PASS, resumes later", scenario_S),
    ("N accepted work is integrated before dependents build on it", scenario_N),
    ("M README lets a fresh session operate the bridge", scenario_M),
]


def run_all(only: list[str] | None = None) -> None:
    for name, fn in SCENARIOS:
        if only and name.split()[0] not in only:
            continue
        _with_temp(fn)
        print(f"  ok  {name}")

    print("SUPERVISOR_SCENARIOS_OK")


if __name__ == "__main__":
    run_all(sys.argv[1:] or None)
