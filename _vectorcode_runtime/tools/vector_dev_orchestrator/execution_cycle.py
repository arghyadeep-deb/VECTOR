"""Bounded implementation/test/review cycle for VECTOR development."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from claude_adapter import ClaudeAdapter
from codex_adapter import CodexAdapter
from laya_log import log_decision, read_decisions
from models import (
    DevTask,
    Provider,
    ReviewFinding,
    ReviewSeverity,
    TaskStage,
    TaskStatus,
    TestResult,
)
from git_guard import GitDelta, GitGuard
from orchestrator import DevOrchestrator
from postflight_guard import PostflightGuard
from quota import detect_provider_exhaustion
from text_signals import norm_repo_path
from runner import CommandResult, CommandRunner


def _log_postflight_decision(
    task: DevTask,
    postflight: Any,
    changed_files: list[str],
) -> None:
    """Log postflight_guard's own deterministic verdict as ground truth.

    No Laya prediction exists yet in this pass -- this captures the
    deterministic policy's verdict itself as a training example for the
    future completion_review_required schema.
    """

    log_decision(
        schema="completion_review_required",
        state=task.description,
        question="Does this change require human review before it can pass?",
        choice=postflight.requires_human,
        meta={
            "changed_files": list(changed_files),
            "risk": postflight.risk.value,
            "findings": [
                {"path": f.path, "risk": f.risk.value, "reason": f.reason}
                for f in postflight.findings
            ],
            "task_category": task.task_category.value,
            "difficulty": task.difficulty.value,
        },
    )


class ExecutionCycle:
    """Run one bounded implementation -> test -> review -> CI cycle."""

    # Structured-output schema requested from the reviewer CLI (Codex
    # --output-schema / Claude --json-schema) when the installed CLI
    # supports it. This is a deterministic fix for the failure mode
    # where a reviewer's prose was substantively correct but omitted
    # the mandatory VERDICT line: when the CLI actually enforces this
    # schema, the final response CANNOT be free text that forgets the
    # verdict, because "verdict" is a required enum field.
    #
    # This is purely additive safety, not a required contract: if a
    # provider ignores the schema request or the CLI doesn't honor it
    # for some call, parse_structured_review() falls back to the
    # legacy FINDING/VERDICT line protocol, which remains fail-closed
    # on its own (see parse_review_verdict / parse_review_findings).
    # NOTE: Codex's structured-output enforcement uses OpenAI-style
    # strict JSON Schema validation, which requires (recursively, on
    # every object node): additionalProperties: false, AND every
    # property key listed in "required" (optionality is expressed via
    # a nullable type union instead of omitting the key from
    # "required"). Confirmed empirically: an earlier version of this
    # schema without these was rejected with HTTP 400
    # invalid_json_schema ("'additionalProperties' is required to be
    # supplied and to be false") before Codex ever attempted the
    # review. Keeping the schema strict-mode-compliant is required for
    # Codex and is harmless for Claude (a stricter schema is still a
    # valid schema).
    _REVIEW_JSON_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["PASS", "CHANGES_REQUIRED"],
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": [
                                "INFO",
                                "WARNING",
                                "ERROR",
                                "BLOCKER",
                            ],
                        },
                        "file": {"type": ["string", "null"]},
                        "line": {"type": ["integer", "null"]},
                        "summary": {"type": "string"},
                    },
                    "required": [
                        "severity",
                        "file",
                        "line",
                        "summary",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["verdict", "findings"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        repo_root: Path,
        *,
        orchestrator: DevOrchestrator | None = None,
        codex: Any | None = None,
        claude: Any | None = None,
        runner: Any | None = None,
        git_guard: Any | None = None,
        postflight_guard: Any | None = None,
        evidence_fn: Callable[[DevTask], str] | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.evidence_fn = evidence_fn or self._collect_review_evidence

        self.orchestrator = (
            orchestrator
            if orchestrator is not None
            else DevOrchestrator(self.repo_root)
        )

        self.codex = (
            codex
            if codex is not None
            else CodexAdapter(self.repo_root)
        )

        self.claude = (
            claude
            if claude is not None
            else ClaudeAdapter(self.repo_root)
        )

        self.runner = (
            runner
            if runner is not None
            else CommandRunner(self.repo_root)
        )

        self.git_guard = (
            git_guard
            if git_guard is not None
            else GitGuard(self.repo_root)
        )

        self.postflight_guard = (
            postflight_guard
            if postflight_guard is not None
            else PostflightGuard()
        )

    def run_once(
        self,
        task: DevTask,
        *,
        test_targets: list[str],
        run_ci_gate: bool = False,
    ) -> DevTask:
        """Run one bounded cycle with no autonomous retry loop."""

        if task.status is TaskStatus.NEEDS_HUMAN:
            raise RuntimeError(
                "Task still requires human approval"
            )

        if task.status is TaskStatus.WAITING_REVIEW:
            raise RuntimeError(
                "Task is WAITING_REVIEW: use resume_review(), not run_once()"
            )

        if task.is_terminal():
            raise RuntimeError(
                f"Task is already terminal: {task.status.value}"
            )

        if not test_targets:
            raise ValueError(
                "At least one deterministic test target is required"
            )

        if (
            task.owner is None
            or task.reviewer is None
            or task.implementer_model is None
            or task.reviewer_model is None
        ):
            raise RuntimeError(
                "Task routing is incomplete"
            )

        self.orchestrator.mark_running(
            task,
            TaskStage.IMPLEMENTING,
        )

        implementation_prompt = self.build_implementation_prompt(
            task=task,
            test_targets=test_targets,
        )

        git_before = self.git_guard.snapshot()

        if not task.baseline_commit:
            task.baseline_commit = getattr(git_before, "head", None) or ""

        implementation = self._invoke_implementer(
            task,
            implementation_prompt,
        )

        if not implementation.succeeded:
            details = self._provider_failure_detail(implementation)
            self._flag_provider_unavailable(task, task.owner, details)
            task.notes.append(
                "Implementation provider diagnostics: " + details
            )
            self.orchestrator.state.save(task)
            self.orchestrator.mark_blocked(
                task,
                "Implementation provider invocation failed.",
            )
            return task

        git_after = self.git_guard.snapshot()

        git_delta = self.git_guard.diff(
            git_before,
            git_after,
        )

        if git_delta.head_changed:
            self._fail_closed_on_head_movement(
                task,
                git_before=git_before,
                git_after=git_after,
                git_delta=git_delta,
                phase="implementation",
            )
            return task

        task.changed_files = list(
            git_delta.changed_files
        )

        if not git_delta.has_changes:
            said = self._redact_secrets(self._extract_result_text(implementation))
            task.notes.append(
                "Implementer's own final message (diagnostic, unverified): "
                + (" ".join(said.split())[:300] or "(empty)")
            )
            self.orchestrator.state.save(task)

            self.orchestrator.mark_blocked(
                task,
                "Implementation invocation completed but changed no files; "
                "no implementation was verified.",
            )
            return task

        if self._enforce_allowed_paths(task, git_delta.changed_files):
            return task

        postflight = self.postflight_guard.evaluate(
            task.changed_files
        )

        _log_postflight_decision(task, postflight, task.changed_files)

        if postflight.requires_human:
            for finding in postflight.findings:
                task.notes.append(
                    "Postflight safety finding: "
                    f"{finding.risk.value}: "
                    f"{finding.path}: "
                    f"{finding.reason}"
                )

            self.orchestrator.state.save(task)

            self.orchestrator.mark_needs_human(
                task,
                "Postflight safety review required after risky file changes.",
            )
            return task

        task.notes.append(
            f"Implementation completed by {task.owner.value}."
        )
        task.notes.append(
            f"Task changed {len(task.changed_files)} file(s)."
        )

        self.orchestrator.state.save(task)

        self.orchestrator.mark_running(
            task,
            TaskStage.TESTING,
        )

        test_result = self.runner.run_pytest(
            test_targets,
        )

        self._record_test(
            task,
            test_result,
        )

        if not test_result.passed:
            self.orchestrator.mark_blocked(
                task,
                "Targeted tests failed after implementation.",
            )
            return task

        if task.review_deferred:
            return self._defer_review(task)

        return self._finish_reviewed(
            task,
            test_targets=test_targets,
            run_ci_gate=run_ci_gate,
        )

    def _defer_review(self, task: DevTask) -> DevTask:
        """Stop after passing tests: the independent review is not affordable yet.

        POLICY.md sec. 10: never a PASS, never a self-review by the implementer's
        provider. Evidence (changed files, test results, notes) is already
        persisted and the worktree is preserved; `resume_review` finishes it.
        """

        self.orchestrator.mark_waiting_review(
            task,
            f"Targeted tests passed; the independent review by {task.reviewer.value} "
            f"({task.reviewer_model.model}) is DEFERRED because that provider is in "
            "quota EMERGENCY. Status WAITING_REVIEW is NOT a pass; the worktree is "
            "preserved and the review runs later via resume_review.",
        )

        return task

    def resume_review(
        self,
        task: DevTask,
        *,
        test_targets: list[str],
        run_ci_gate: bool = False,
    ) -> DevTask:
        """Run the deferred independent review for a WAITING_REVIEW task.

        Fails closed if the worktree no longer matches what was tested, re-runs
        the targeted tests, then continues exactly like a normal cycle
        (review -> bounded fix -> re-review -> verify -> PASS/BLOCKED).
        """

        if task.status is not TaskStatus.WAITING_REVIEW:
            raise RuntimeError(
                f"Task is {task.status.value}, not WAITING_REVIEW"
            )

        if not test_targets:
            raise ValueError(
                "At least one deterministic test target is required"
            )

        if (
            task.owner is None
            or task.reviewer is None
            or task.implementer_model is None
            or task.reviewer_model is None
        ):
            raise RuntimeError("Task routing is incomplete")

        def norm(paths: Any) -> set[str]:
            return {str(p).replace("\\", "/").strip() for p in paths if str(p).strip()}

        snapshot = self.git_guard.snapshot()
        current, expected = norm(snapshot.files), norm(task.changed_files)
        head = getattr(snapshot, "head", None) or ""

        if current != expected or (task.baseline_commit and head and head != task.baseline_commit):
            task.notes.append(
                "Worktree changed while waiting for review: "
                f"unexpected={sorted(current - expected)} missing={sorted(expected - current)} "
                f"head_moved={bool(task.baseline_commit and head and head != task.baseline_commit)}"
            )
            self.orchestrator.mark_blocked(
                task,
                "The worktree changed while the task waited for independent review; "
                "refusing to review or certify it (evidence preserved).",
            )
            return task

        task.review_deferred = False
        self.orchestrator.mark_running(task, TaskStage.TESTING)
        result = self.runner.run_pytest(test_targets)
        self._record_test(task, result)

        if not result.passed:
            self.orchestrator.mark_blocked(
                task,
                "Targeted tests failed when the deferred review resumed.",
            )
            return task

        return self._finish_reviewed(
            task,
            test_targets=test_targets,
            run_ci_gate=run_ci_gate,
        )

    def _finish_reviewed(
        self,
        task: DevTask,
        *,
        test_targets: list[str],
        run_ci_gate: bool,
    ) -> DevTask:
        review_passed = self._review_until_pass(
            task=task,
            test_targets=test_targets,
        )

        if not review_passed:
            return task

        if run_ci_gate:
            self.orchestrator.mark_running(
                task,
                TaskStage.CI_GATE,
            )

            ci_result = self.runner.run_ci_gate()

            self._record_test(
                task,
                ci_result,
            )

            if not ci_result.passed:
                self.orchestrator.mark_blocked(
                    task,
                    "Repository CI gate failed.",
                )
                return task

        self.orchestrator.mark_running(
            task,
            TaskStage.VERIFYING,
        )

        self.orchestrator.mark_pass(
            task,
            "Implementation, targeted tests and cross-provider review passed.",
        )

        return task

    def _review_until_pass(
        self,
        *,
        task: DevTask,
        test_targets: list[str],
    ) -> bool:
        """Review, fix, retest and re-review with bounded retries."""

        while True:
            self.orchestrator.mark_running(
                task,
                TaskStage.REVIEWING,
            )

            review_prompt = self.build_review_prompt(
                task=task,
                test_targets=test_targets,
                evidence=self.evidence_fn(task),
            )

            review = self._invoke_reviewer(
                task,
                review_prompt,
            )

            if not review.succeeded:
                details = self._provider_failure_detail(review)
                self._flag_provider_unavailable(task, task.reviewer, details)
                task.notes.append(
                    "Cross-provider review diagnostics: " + details
                )
                self.orchestrator.state.save(task)
                self.orchestrator.mark_blocked(
                    task,
                    "Cross-provider review invocation failed.",
                )
                return False

            review_text = self._extract_result_text(
                review
            )

            # Persist bounded, secret-redacted reviewer evidence to task
            # state BEFORE parsing it. If parsing later disagrees with
            # what a human expects (as happened for a prior live task
            # with 0 findings but a CHANGES_REQUIRED verdict), the raw
            # evidence is available for audit instead of being lost.
            task.reviewer_evidence.append(
                self._bounded_reviewer_evidence(review_text)
            )
            # Bound the number of retained evidence snapshots too, in
            # case retry limits are ever raised; this is a hard ceiling
            # independent of the review/fix retry budget.
            if len(task.reviewer_evidence) > self._MAX_REVIEWER_EVIDENCE_ENTRIES:
                task.reviewer_evidence = task.reviewer_evidence[
                    -self._MAX_REVIEWER_EVIDENCE_ENTRIES:
                ]

            self.orchestrator.state.save(task)

            # A fresh full-tree review supersedes unresolved findings
            # from the preceding review attempt.
            for previous in task.review_findings:
                if not previous.resolved:
                    previous.resolved = True

            verdict, findings = self.parse_structured_review(
                review_text
            )

            task.review_findings.extend(
                findings
            )

            blocking_findings = [
                finding
                for finding in findings
                if finding.severity in {
                    ReviewSeverity.ERROR,
                    ReviewSeverity.BLOCKER,
                }
            ]

            # Never allow an explicit blocking finding to coexist
            # with an accepted PASS verdict.
            effective_pass = (
                verdict == "PASS"
                and not blocking_findings
            )

            task.notes.append(
                "Reviewer produced "
                f"{len(findings)} structured finding(s)."
            )
            task.notes.append(
                f"Reviewer verdict: {verdict}."
            )

            if blocking_findings and verdict == "PASS":
                task.notes.append(
                    "Reviewer PASS overridden because ERROR/BLOCKER "
                    "findings were present."
                )

            self.orchestrator.state.save(task)

            if effective_pass:
                return True

            if not task.can_retry():
                self.orchestrator.mark_blocked(
                    task,
                    "Cross-provider reviewer requested changes "
                    "and the retry budget is exhausted.",
                )
                return False

            # Bounded escalation (section 6): a genuine BLOCKER-severity
            # finding is evidence the current implementer capability may
            # be insufficient. This is the ONLY automatic escalation
            # trigger wired here -- deliberately narrow, deterministic,
            # and bounded by task.max_escalations. It never fires for
            # malformed output, tooling bugs, sandbox issues, HEAD
            # movement, or approval requirements; those already fail
            # closed through their own subsystems above.
            has_blocker_finding = any(
                finding.severity is ReviewSeverity.BLOCKER
                for finding in findings
            )

            if has_blocker_finding and task.can_escalate():
                self._escalate_for_blocker(task)

            task.retry_count += 1

            self.orchestrator.mark_running(
                task,
                TaskStage.FIXING,
            )

            fix_prompt = self.build_fix_prompt(
                task=task,
                test_targets=test_targets,
                review_text=review_text,
            )

            git_before = self.git_guard.snapshot()

            fix_result = self._invoke_implementer(
                task,
                fix_prompt,
            )

            if not fix_result.succeeded:
                details = self._provider_failure_detail(fix_result)
                self._flag_provider_unavailable(task, task.owner, details)
                task.notes.append(
                    "Fix provider diagnostics: " + details
                )
                self.orchestrator.state.save(task)
                self.orchestrator.mark_blocked(
                    task,
                    "Implementation provider failed during fix attempt "
                    f"{task.retry_count}.",
                )
                return False

            git_after = self.git_guard.snapshot()

            git_delta = self.git_guard.diff(
                git_before,
                git_after,
            )

            if git_delta.head_changed:
                self._fail_closed_on_head_movement(
                    task,
                    git_before=git_before,
                    git_after=git_after,
                    git_delta=git_delta,
                    phase="fix attempt",
                )
                return False

            if not git_delta.has_changes:
                self.orchestrator.mark_blocked(
                    task,
                    "Reviewer requested changes but the implementer "
                    "changed no files.",
                )
                return False

            if self._enforce_allowed_paths(task, git_delta.changed_files):
                return False

            task.changed_files = sorted(
                set(task.changed_files)
                | set(git_delta.changed_files)
            )

            postflight = self.postflight_guard.evaluate(
                git_delta.changed_files
            )

            _log_postflight_decision(task, postflight, git_delta.changed_files)

            if postflight.requires_human:
                for finding in postflight.findings:
                    task.notes.append(
                        "Postflight safety finding during fix: "
                        f"{finding.risk.value}: "
                        f"{finding.path}: "
                        f"{finding.reason}"
                    )

                self.orchestrator.state.save(task)

                self.orchestrator.mark_needs_human(
                    task,
                    "Postflight safety review required after "
                    "risky fix changes.",
                )
                return False

            task.notes.append(
                f"Fix attempt {task.retry_count} completed "
                f"by {task.owner.value}."
            )

            self.orchestrator.state.save(task)

            self.orchestrator.mark_running(
                task,
                TaskStage.TESTING,
            )

            test_result = self.runner.run_pytest(
                test_targets,
            )

            self._record_test(
                task,
                test_result,
            )

            if not test_result.passed:
                self.orchestrator.mark_blocked(
                    task,
                    "Targeted tests failed after fix attempt "
                    f"{task.retry_count}.",
                )
                return False

            # Loop back to an independent cross-provider review.

    def _fail_closed_on_head_movement(
        self,
        task: DevTask,
        *,
        git_before: Any,
        git_after: Any,
        git_delta: GitDelta,
        phase: str,
    ) -> None:
        """Fail closed immediately on unexpected provider-caused HEAD movement.

        Unexpected HEAD movement during implementation or a fix attempt is
        a safety violation, not routine noise: the orchestrator, not the
        provider CLI, is supposed to own commit boundaries. This preserves
        the worktree/commit as audit evidence (no reset/clean/delete), and
        refuses to continue to tests/review/further fixes.
        """

        before_head = getattr(git_before, "head", None) or "<unknown>"
        after_head = getattr(git_after, "head", None) or "<unknown>"

        task.changed_files = sorted(
            set(task.changed_files) | set(git_delta.changed_files)
        )

        owner_text = task.owner.value if task.owner else "unknown"

        task.notes.append(
            "SAFETY VIOLATION: unexpected Git HEAD movement detected "
            f"during {phase} (owner={owner_text}). "
            f"HEAD before={before_head} after={after_head}. "
            "The worktree/commit is preserved as audit evidence and "
            "must not be reset, cleaned or deleted automatically. "
            "Committed/changed paths: "
            f"{', '.join(git_delta.changed_files) or '(none)'}."
        )

        self.orchestrator.state.save(task)

        self.orchestrator.mark_needs_human(
            task,
            "Unexpected Git HEAD movement during "
            f"{phase} is a safety violation; human review of the "
            "preserved worktree/commit is required before any further "
            "automated action.",
        )

    def _escalate_for_blocker(self, task: DevTask) -> None:
        """Bounded, deterministic escalation triggered by a BLOCKER finding.

        Bumps task.difficulty exactly one tier (bounded ladder, capped
        at CRITICAL -- see router.escalate_difficulty) and re-selects
        the IMPLEMENTER model only, for the upcoming bounded fix
        attempt. The reviewer model, retry budget, and 50/50 ownership
        are unaffected. Persisted and observable via task.notes /
        task.escalation_count.
        """

        previous_difficulty = task.difficulty

        escalated_difficulty = (
            self.orchestrator.router.escalate_difficulty(
                previous_difficulty
            )
        )

        if escalated_difficulty is previous_difficulty:
            # Already at the ceiling (CRITICAL): nothing to escalate to.
            return

        if task.owner is None:
            return

        task.escalation_count += 1
        task.difficulty = escalated_difficulty

        task.implementer_model = (
            self.orchestrator.router.choose_implementer(
                provider=task.owner,
                difficulty=escalated_difficulty,
            )
        )

        task.notes.append(
            "Escalated implementer difficulty "
            f"{previous_difficulty.value} -> "
            f"{escalated_difficulty.value} "
            f"(escalation {task.escalation_count}/"
            f"{task.max_escalations}) after a BLOCKER-severity "
            "reviewer finding; new implementer model: "
            f"{task.implementer_model.model}."
        )

        self.orchestrator.state.save(task)

    PROVIDER_UNAVAILABLE_MARKER = "PROVIDER_UNAVAILABLE:"
    _MAX_EVIDENCE_CHARS = 12000

    def _flag_provider_unavailable(
        self,
        task: DevTask,
        provider: Provider | None,
        details: str,
    ) -> None:
        """Mark quota/rate-limit stops so callers pause instead of retrying.

        This is diagnostic only: a provider exhaustion must never be
        treated as a capability problem (no escalation) and independent
        review must never be silently replaced by the other provider.
        """

        if provider is not None and detect_provider_exhaustion(details):
            task.notes.append(f"{self.PROVIDER_UNAVAILABLE_MARKER}{provider.value}")

    @staticmethod
    def _path_allowed(path: str, patterns: list[str]) -> bool:
        norm = norm_repo_path(path)

        for raw in patterns:
            pattern = norm_repo_path(raw)

            if pattern.endswith("/**"):
                pattern = pattern[:-3] + "/"

            if pattern.endswith("/"):
                if norm.startswith(pattern):
                    return True
            elif any(ch in pattern for ch in "*?["):
                if fnmatch.fnmatch(norm, pattern):
                    return True
            elif norm == pattern:
                return True

        return False

    def _enforce_allowed_paths(self, task: DevTask, changed: tuple[str, ...] | list[str]) -> bool:
        """Fail closed if the implementer touched files outside allowed_paths.

        Returns True when the task was blocked. Ad-hoc tasks (no
        allowed_paths) are not restricted. The worktree is preserved.
        """

        if not task.allowed_paths:
            return False

        outside = sorted(
            f for f in changed if not self._path_allowed(f, task.allowed_paths)
        )

        if not outside:
            return False

        task.changed_files = sorted(set(task.changed_files) | set(changed))
        task.notes.append(
            "SCOPE VIOLATION: files changed outside allowed paths "
            f"{task.allowed_paths}: {outside}"
        )
        self.orchestrator.state.save(task)
        self.orchestrator.mark_blocked(
            task,
            "Implementer changed files outside the allowed mutation paths; "
            "worktree preserved for audit.",
        )
        return True

    @staticmethod
    def _implementer_line(task: DevTask) -> str:
        if task.owner is None:
            return ""

        model = getattr(task.implementer_model, "model", "?")
        files = ", ".join(task.changed_files[:12]) or "(none reported)"

        return (
            f"IMPLEMENTED BY: {task.owner.value} ({model}); you are the independent "
            f"cross-provider reviewer.\nACTUAL CHANGED FILES: {files}\n\n"
        )

    @staticmethod
    def _previous_findings_block(task: DevTask) -> str:
        previous = [f for f in task.review_findings if f.resolved][-6:]

        if not previous:
            return ""

        lines = [
            f"- {getattr(f.severity, 'value', f.severity)} "
            f"{f.file or '?'}:{f.line if f.line is not None else '?'} {f.summary[:200]}"
            for f in previous
        ]

        return (
            "PREVIOUS STRUCTURED FINDINGS (already sent to the implementer; verify each "
            "was genuinely fixed and look for anything new):\n" + "\n".join(lines) + "\n\n"
        )

    @staticmethod
    def _spec_block(task: DevTask) -> str:
        parts: list[str] = []

        if task.objective:
            parts.append(f"OBJECTIVE:\n{task.objective}\n")
        if task.allowed_paths:
            parts.append("ALLOWED MUTATION PATHS (touch nothing else):\n" + "\n".join(f"- {p}" for p in task.allowed_paths) + "\n")
        if task.forbidden_scope:
            parts.append("FORBIDDEN SCOPE:\n" + "\n".join(f"- {p}" for p in task.forbidden_scope) + "\n")
        if task.acceptance_criteria:
            parts.append("ACCEPTANCE CRITERIA:\n" + "\n".join(f"- {p}" for p in task.acceptance_criteria) + "\n")
        if task.stop_conditions:
            parts.append("STOP AND REPORT (do not push through) IF:\n" + "\n".join(f"- {p}" for p in task.stop_conditions) + "\n")

        return ("\n".join(parts) + "\n") if parts else ""

    def _git_text(self, *args: str) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.repo_root), *args],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", shell=False, check=False, timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return proc.stdout if proc.returncode == 0 else ""

    def _collect_review_evidence(self, task: DevTask) -> str:
        """Bounded, redacted evidence for the independent reviewer.

        Accepted baseline commit, the actual diff of the reported changed
        files, and the raw targeted-test result. Never the implementer's
        own claims of success.
        """

        lines = [f"ACCEPTED BASELINE COMMIT: {task.baseline_commit or '(unknown)'}"]
        budget = self._MAX_EVIDENCE_CHARS
        diff_parts: list[str] = []
        files = task.changed_files[:20]
        # Each changed file gets its own share so one huge diff cannot
        # crowd every other file out of the reviewer's evidence.
        per_file = max(1500, budget // max(1, len(files)))

        for name in files:
            diff = self._git_text("diff", "HEAD", "--no-color", "--", name)

            if not diff:
                path = self.repo_root / name
                tracked = bool(self._git_text("ls-files", "--", name).strip())

                if path.is_file() and not tracked:
                    try:
                        body = path.read_text(encoding="utf-8", errors="replace")[:4000]
                    except OSError:
                        body = "(unreadable)"
                    diff = f"NEW FILE {name}:\n{body}"

            if diff:
                if len(diff) > per_file:
                    diff = diff[:per_file] + f"\n[...diff for {name} truncated...]"
                diff_parts.append(diff)

        joined = "\n".join(diff_parts) or "(no diff available)"
        diff_text = self._redact_secrets(joined)[: budget + 1500]
        lines.append("DIFF OF CHANGED FILES (vs the baseline):\n" + diff_text)

        if task.tests:
            last = task.tests[-1]
            tail = self._redact_secrets((last.stdout or "") + (last.stderr or ""))[-1500:]
            lines.append(
                f"TARGETED TEST RESULT: command={last.command!r} "
                f"exit_code={last.exit_code} passed={last.passed}\n"
                f"RAW TEST OUTPUT (tail):\n{tail}"
            )

        return "\n\n".join(lines)

    @staticmethod
    def _provider_failure_detail(result: Any) -> str:
        """Return bounded provider failure diagnostics."""
        try:
            payload = json.loads(str(getattr(result, "stdout", "") or ""))
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict) and (
            payload.get("is_error")
            or str(payload.get("subtype", "")).startswith("error")
            or payload.get("type") == "error"
        ):
            # Ignore unrelated startup stderr when the provider supplied an
            # explicit structured failure; never persist raw credential text.
            details = {key: payload[key] for key in
                       ("type", "subtype", "is_error", "result", "errors", "error") if key in payload}
            return ExecutionCycle._redact_secrets(json.dumps(details, ensure_ascii=False))[-4000:]
        for attribute in ("stderr", "stdout", "final_message"):
            value = str(
                getattr(result, attribute, "") or ""
            ).strip()
            if value:
                return ExecutionCycle._redact_secrets(value)[-4000:]
        return "No provider diagnostics returned."

    # Bounded audit-evidence persistence (issue 3). Caps prevent
    # unbounded task-state growth; redaction avoids dumping obvious
    # secret-shaped strings from provider output into persisted state.
    _MAX_REVIEWER_EVIDENCE_CHARS = 4000
    _MAX_REVIEWER_EVIDENCE_ENTRIES = 10

    _SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
        re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{16,}", re.IGNORECASE),
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
            r"-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    )

    @classmethod
    def _redact_secrets(cls, text: str) -> str:
        redacted = text
        for pattern in cls._SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted

    @classmethod
    def _bounded_reviewer_evidence(cls, text: str) -> str:
        """Bounded, secret-redacted normalized reviewer text for audit."""

        redacted = cls._redact_secrets(text)

        limit = cls._MAX_REVIEWER_EVIDENCE_CHARS

        if len(redacted) <= limit:
            return redacted

        half = limit // 2

        return (
            redacted[:half]
            + "\n...[reviewer evidence truncated for bounded "
            "audit storage]...\n"
            + redacted[-half:]
        )

    @staticmethod
    def build_fix_prompt(
        *,
        task: DevTask,
        test_targets: list[str],
        review_text: str,
    ) -> str:
        tests = "\n".join(
            f"- {target}"
            for target in test_targets
        )

        return (
            "You are the original implementation owner fixing one "
            "bounded VECTOR development task after independent review.\n\n"
            f"TASK:\n{task.description}\n\n"
            f"{ExecutionCycle._spec_block(task)}"
            "REQUIRED TEST TARGETS:\n"
            f"{tests}\n\n"
            "INDEPENDENT REVIEW:\n"
            f"{review_text}\n\n"
            "Rules:\n"
            "- Follow AGENTS.md, CLAUDE.md and project rules.\n"
            "- Inspect the current implementation before editing.\n"
            "- Address the review findings with the smallest safe change.\n"
            "- Do not perform destructive operations.\n"
            "- Do not change dependencies, architecture, security policy, "
            "database schema, production configuration, credentials, or "
            "protected Git branches unless separately approved.\n"
            "- Do not commit, push or merge.\n"
            "- Do not undo unrelated valid work.\n"
            "- Leave the working tree ready for deterministic tests and "
            "another independent review.\n"
        )

    @staticmethod
    def build_implementation_prompt(
        *,
        task: DevTask,
        test_targets: list[str],
    ) -> str:
        tests = "\n".join(
            f"- {target}"
            for target in test_targets
        )

        return (
            "You are the implementation owner for one bounded VECTOR "
            "development task.\n\n"
            f"TASK:\n{task.description}\n\n"
            f"{ExecutionCycle._spec_block(task)}"
            "REQUIRED TEST TARGETS:\n"
            f"{tests}\n\n"
            "Rules:\n"
            "- Follow AGENTS.md, CLAUDE.md and project rules.\n"
            "- Inspect existing implementation before editing.\n"
            "- Make the smallest safe change that solves the task.\n"
            "- Do not perform destructive operations.\n"
            "- Do not change dependencies, architecture, security policy, "
            "database schema, production configuration, credentials, or "
            "protected Git branches unless separately approved.\n"
            "- Do not commit, push or merge.\n"
            "- Do not claim success merely because code was written.\n"
            "- Leave the working tree ready for deterministic tests and "
            "cross-provider review.\n"
        )

    @staticmethod
    def build_review_prompt(
        *,
        task: DevTask,
        test_targets: list[str],
        evidence: str = "",
    ) -> str:
        tests = "\n".join(
            f"- {target}"
            for target in test_targets
        )

        return (
            "Perform an independent READ-ONLY review of the current working "
            "tree for this VECTOR development task.\n\n"
            "INDEPENDENCE: you are a separate reviewer from a different "
            "provider than the implementer. Do not defer to, assume or "
            "trust the implementer's own assessment. Verify against the "
            "code and the evidence below, report real defects even when "
            "tests pass, do not soften findings to be agreeable, and "
            "return PASS only if the specification and acceptance "
            "criteria are actually met.\n\n"
            f"TASK:\n{task.description}\n\n"
            f"{ExecutionCycle._implementer_line(task)}"
            f"{ExecutionCycle._spec_block(task)}"
            f"{ExecutionCycle._previous_findings_block(task)}"
            "TEST TARGETS ALREADY RUN BY THE CONTROLLER:\n"
            f"{tests}\n\n"
            + (f"CONTROLLER EVIDENCE (raw, bounded):\n{evidence}\n\n" if evidence else "")
            + "Review correctness, regressions, security, repository rules, "
            "scope control and whether the implementation actually satisfies "
            "the task.\n\n"
            "Do not edit files. Do not commit, push or merge.\n\n"
            "MANDATORY OUTPUT CONTRACT: an automated parser reads your "
            "final response and FAILS CLOSED -- treats your review as "
            "CHANGES_REQUIRED -- if this contract is not met exactly. "
            "Positive prose alone (e.g. \"no actionable defects found\") "
            "is NEVER sufficient on its own; the machine-readable verdict "
            "below is what actually counts.\n\n"
            "If this call constrains your final response to a JSON "
            "schema, respond with EXACTLY that JSON object and nothing "
            "else -- no prose before or after it:\n"
            '{"verdict": "PASS" | "CHANGES_REQUIRED", '
            '"findings": [{"severity": "INFO" | "WARNING" | "ERROR" | '
            '"BLOCKER", "file": string or null, "line": integer or '
            'null, "summary": string}]}\n'
            "Use an empty findings array when there are no findings.\n\n"
            "If your final response is NOT constrained to that JSON "
            "schema for this call, respond in plain text using EXACTLY "
            "this fallback protocol instead:\n"
            "Report each concrete finding on its own line using exactly:\n"
            "FINDING|SEVERITY|FILE|LINE|SUMMARY\n"
            "where SEVERITY is INFO, WARNING, ERROR, or BLOCKER.\n"
            "Use an empty FILE or LINE when not applicable.\n"
            "SUMMARY must remain on one line and must not contain |.\n"
            "If there are no findings, emit no FINDING lines.\n"
            "Then end your response with exactly one line, and no other "
            "text of any kind after it:\n"
            "VERDICT: PASS\n"
            "or\n"
            "VERDICT: CHANGES_REQUIRED\n\n"
            "In the fallback (non-JSON) case, that VERDICT line is "
            "MANDATORY: omitting it, wrapping it in extra commentary, or "
            "ending your response without it as the very last line will "
            "be parsed as CHANGES_REQUIRED regardless of how positive "
            "the rest of your review was.\n"
        )

    def _invoke_implementer(
        self,
        task: DevTask,
        prompt: str,
    ) -> Any:
        choice = task.implementer_model

        if choice is None or task.owner is None:
            raise RuntimeError(
                "Implementer routing is missing"
            )

        task.provider_calls += 1

        if task.owner is Provider.CODEX:
            return self.codex.run_implementation(
                prompt=prompt,
                model=choice.model,
            )

        return self.claude.run_implementation(
            prompt=prompt,
            model=choice.model,
            effort=choice.effort or "medium",
        )

    def _invoke_reviewer(
        self,
        task: DevTask,
        prompt: str,
    ) -> Any:
        choice = task.reviewer_model

        if choice is None or task.reviewer is None:
            raise RuntimeError(
                "Reviewer routing is missing"
            )

        task.provider_calls += 1

        if task.reviewer is Provider.CODEX:
            return self.codex.run_read_only(
                prompt=prompt,
                model=choice.model,
                output_schema=self._REVIEW_JSON_SCHEMA,
            )

        return self.claude.run_read_only(
            prompt=prompt,
            model=choice.model,
            effort=choice.effort or "medium",
            json_schema=self._REVIEW_JSON_SCHEMA,
        )

    @classmethod
    def parse_structured_review(
        cls,
        text: str,
    ) -> tuple[str, list[ReviewFinding]]:
        """Parse reviewer output, preferring strict JSON-schema output.

        When the provider CLI's structured-output/schema enforcement
        (Codex --output-schema / Claude --json-schema) actually
        produced a JSON object matching our
        {"verdict": ..., "findings": [...]} contract, use it directly
        -- there is no formatting ambiguity left to resolve, and a
        reviewer literally cannot omit the verdict field since it is a
        required enum in the schema.

        Otherwise fall back to the legacy FINDING/VERDICT line
        protocol (parse_review_findings / parse_review_verdict), which
        remains fail-closed on its own. This keeps the system safe
        whether or not the installed CLI actually enforces the
        requested schema for a given call.
        """

        json_result = cls._parse_structured_review_json(text)

        if json_result is not None:
            return json_result

        return (
            cls.parse_review_verdict(text),
            cls.parse_review_findings(text),
        )

    @classmethod
    def _parse_structured_review_json(
        cls,
        text: str,
    ) -> tuple[str, list[ReviewFinding]] | None:
        """Strict JSON-mode parse; returns None if not our JSON contract.

        Returning None (rather than failing closed here) is
        deliberate: it means "this wasn't a JSON-schema response at
        all", so the caller falls back to the text-line protocol
        instead of treating unrelated JSON as a malformed review.
        """

        stripped = text.strip()

        if not stripped:
            return None

        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None

        raw_verdict = payload.get("verdict")

        if not isinstance(raw_verdict, str):
            return None

        verdict = raw_verdict.strip().upper()

        if verdict not in {"PASS", "CHANGES_REQUIRED"}:
            return None

        raw_findings = payload.get("findings", [])

        if raw_findings is None:
            raw_findings = []

        if not isinstance(raw_findings, list):
            return verdict, [
                ReviewFinding(
                    severity=ReviewSeverity.BLOCKER,
                    summary=(
                        "Malformed structured reviewer output (JSON): "
                        "'findings' was not a list."
                    ),
                )
            ]

        severity_map = {
            "INFO": ReviewSeverity.INFO,
            "WARNING": ReviewSeverity.WARNING,
            "ERROR": ReviewSeverity.ERROR,
            "BLOCKER": ReviewSeverity.BLOCKER,
        }

        findings: list[ReviewFinding] = []

        for item in raw_findings:
            if not isinstance(item, dict):
                findings.append(
                    ReviewFinding(
                        severity=ReviewSeverity.BLOCKER,
                        summary=(
                            "Malformed structured reviewer finding "
                            f"(JSON): {item!r}"
                        ),
                    )
                )
                continue

            severity_text = item.get("severity")
            summary_text = item.get("summary")

            severity = (
                severity_map.get(severity_text.strip().upper())
                if isinstance(severity_text, str)
                else None
            )

            if (
                severity is None
                or not isinstance(summary_text, str)
                or not summary_text.strip()
            ):
                findings.append(
                    ReviewFinding(
                        severity=ReviewSeverity.BLOCKER,
                        summary=(
                            "Invalid structured reviewer finding "
                            f"(JSON): {item!r}"
                        ),
                    )
                )
                continue

            file_text = item.get("file")

            file_value = (
                file_text.strip()
                if isinstance(file_text, str) and file_text.strip()
                else None
            )

            raw_line = item.get("line")
            line_number = None

            if (
                isinstance(raw_line, int)
                and not isinstance(raw_line, bool)
                and raw_line > 0
            ):
                line_number = raw_line
            elif raw_line not in (None, ""):
                findings.append(
                    ReviewFinding(
                        severity=ReviewSeverity.BLOCKER,
                        summary=(
                            "Invalid structured reviewer line number "
                            f"(JSON): {item!r}"
                        ),
                    )
                )
                continue

            findings.append(
                ReviewFinding(
                    severity=severity,
                    summary=summary_text.strip(),
                    file=file_value,
                    line=line_number,
                )
            )

        return verdict, findings

    @staticmethod
    def parse_review_findings(
        text: str,
    ) -> list[ReviewFinding]:
        """Parse deterministic reviewer finding lines.

        Malformed FINDING lines fail closed as blocker findings.
        """

        findings: list[ReviewFinding] = []

        severity_map = {
            "INFO": ReviewSeverity.INFO,
            "WARNING": ReviewSeverity.WARNING,
            "ERROR": ReviewSeverity.ERROR,
            "BLOCKER": ReviewSeverity.BLOCKER,
        }

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line.upper().startswith("FINDING|"):
                continue

            parts = line.split("|", 4)

            if len(parts) != 5:
                findings.append(
                    ReviewFinding(
                        severity=ReviewSeverity.BLOCKER,
                        summary=(
                            "Malformed structured reviewer finding: "
                            f"{line}"
                        ),
                    )
                )
                continue

            _, severity_text, file_text, line_text, summary = parts

            severity = severity_map.get(
                severity_text.strip().upper()
            )

            if severity is None or not summary.strip():
                findings.append(
                    ReviewFinding(
                        severity=ReviewSeverity.BLOCKER,
                        summary=(
                            "Invalid structured reviewer finding: "
                            f"{line}"
                        ),
                    )
                )
                continue

            line_number = None

            if line_text.strip():
                try:
                    parsed_line = int(
                        line_text.strip()
                    )

                    if parsed_line > 0:
                        line_number = parsed_line
                    else:
                        raise ValueError
                except ValueError:
                    findings.append(
                        ReviewFinding(
                            severity=ReviewSeverity.BLOCKER,
                            summary=(
                                "Invalid reviewer line number: "
                                f"{line}"
                            ),
                        )
                    )
                    continue

            findings.append(
                ReviewFinding(
                    severity=severity,
                    summary=summary.strip(),
                    file=file_text.strip() or None,
                    line=line_number,
                )
            )

        return findings

    # Matches exactly one structured verdict line, tolerating only:
    #   - surrounding Markdown emphasis (*, _, `, #, > and whitespace)
    #   - the canonical two tokens (PASS / CHANGES_REQUIRED)
    #   - harmless terminal punctuation/emphasis after the token
    # This is a full-line anchored match (^...$), never a substring
    # search, so text like "NOT_A_VERDICT: PASS" or a verdict buried
    # inside a prose sentence cannot be mistaken for a real verdict.
    _VERDICT_LINE_RE = re.compile(
        r"^[\*_`~#>\s]*VERDICT\s*:\s*(PASS|CHANGES_REQUIRED)"
        r"[\*_`~#>\s.!]*$",
        re.IGNORECASE,
    )

    @classmethod
    def parse_review_verdict(
        cls,
        text: str,
    ) -> str:
        """Deterministically parse exactly one unambiguous structured verdict.

        Fails closed to CHANGES_REQUIRED unless the reviewer text contains
        exactly one line that unambiguously states a verdict (tolerating
        only harmless Markdown emphasis, whitespace and terminal
        punctuation). A missing, duplicate, conflicting or otherwise
        ambiguous verdict all resolve to CHANGES_REQUIRED. The verdict
        line does not need to be the final line -- any uniquely
        identifiable structured verdict anywhere in the text is honored.
        """

        matches: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            match = cls._VERDICT_LINE_RE.match(line)

            if match is None:
                continue

            matches.append(match.group(1).upper())

        if len(matches) != 1:
            return "CHANGES_REQUIRED"

        return matches[0]

    @staticmethod
    def _extract_result_text(
        result: Any,
    ) -> str:
        """Normalize Codex text output and Claude JSON output."""

        final_message = getattr(
            result,
            "final_message",
            "",
        )

        if final_message:
            return str(final_message)

        stdout = str(
            getattr(result, "stdout", "")
        ).strip()

        if not stdout:
            return ""

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return stdout

        if isinstance(payload, dict):
            value = payload.get("result")

            if isinstance(value, str):
                return value

        return stdout

    @staticmethod
    def _record_test(
        task: DevTask,
        result: CommandResult,
    ) -> None:
        command_text = subprocess_command_text(
            result.command,
        )

        task.commands_executed.append(command_text)

        task.tests.append(
            TestResult(
                command=command_text,
                exit_code=(
                    result.exit_code
                    if result.exit_code is not None
                    else -1
                ),
                passed=result.passed,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        )


def subprocess_command_text(
    command: list[str],
) -> str:
    """Render deterministic command evidence without shell execution."""

    return " ".join(
        str(part)
        for part in command
    )


class _FakeProviderResult:
    def __init__(
        self,
        *,
        succeeded: bool = True,
        text: str = "",
        claude_json: bool = False,
    ) -> None:
        self.succeeded = succeeded

        if claude_json:
            self.stdout = json.dumps(
                {"result": text}
            )
            self.final_message = ""
        else:
            self.stdout = ""
            self.final_message = text

        self.stderr = ""


class _FakeCodex:
    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        return _FakeProviderResult(
            text="Implementation complete."
        )

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        return _FakeProviderResult(
            text="Review complete.\nVERDICT: PASS"
        )


class _FakeClaude:
    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort

        return _FakeProviderResult(
            text="Implementation complete.",
            claude_json=True,
        )

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort

        return _FakeProviderResult(
            text="Review complete.\nVERDICT: PASS",
            claude_json=True,
        )


class _RetryFakeClaude(_FakeClaude):
    """Reject the first review, then pass the re-review."""

    def __init__(self) -> None:
        self.review_count = 0

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort

        self.review_count += 1

        if self.review_count == 1:
            return _FakeProviderResult(
                text=(
                    "A deterministic issue remains.\n"
                    "FINDING|ERROR|core/example.py|12|"
                    "Parser must handle the reviewed edge case.\n"
                    "VERDICT: CHANGES_REQUIRED"
                ),
                claude_json=True,
            )

        return _FakeProviderResult(
            text=(
                "The requested correction is now present.\n"
                "VERDICT: PASS"
            ),
            claude_json=True,
        )


class _FakeGitGuard:
    def __init__(self) -> None:
        self.snapshot_count = 0

    def snapshot(self) -> object:
        self.snapshot_count += 1
        return object()

    @staticmethod
    def diff(
        before: object,
        after: object,
    ) -> GitDelta:
        assert before is not after

        return GitDelta(
            changed_files=(
                "core/example.py",
                "tests/test_example.py",
            ),
            added_files=(),
            removed_files=(),
        )


class _FakeRiskyGitGuard(_FakeGitGuard):
    @staticmethod
    def diff(
        before: object,
        after: object,
    ) -> GitDelta:
        assert before is not after

        return GitDelta(
            changed_files=(
                "core/security/token_manager.py",
            ),
            added_files=(),
            removed_files=(),
        )


class _FakeRunner:
    def run_pytest(
        self,
        test_targets: list[str],
        *,
        quiet: bool = True,
    ) -> CommandResult:
        assert test_targets

        return CommandResult(
            command=[
                sys.executable,
                "-m",
                "pytest",
                *test_targets,
            ],
            exit_code=0,
            stdout="1 passed",
            stderr="",
        )

    def run_ci_gate(self) -> CommandResult:
        return CommandResult(
            command=[
                sys.executable,
                "tools/ci_gate.py",
            ],
            exit_code=0,
            stdout="CI passed",
            stderr="",
        )


class _AssertNeverRunner:
    """Fails loudly if the test/CI-gate stage is ever reached.

    Used to prove that a fail-closed guard (HEAD movement, provider
    failure, ...) really stops the cycle before testing, rather than
    merely happening to produce a passing result downstream.
    """

    def run_pytest(
        self,
        test_targets: list[str],
        *,
        quiet: bool = True,
    ) -> CommandResult:
        raise AssertionError(
            "Targeted tests must not run after a fail-closed guard."
        )

    def run_ci_gate(self) -> CommandResult:
        raise AssertionError(
            "CI gate must not run after a fail-closed guard."
        )


class _FakeFailingRunner:
    """Deterministically fails the targeted-test stage."""

    def run_pytest(
        self,
        test_targets: list[str],
        *,
        quiet: bool = True,
    ) -> CommandResult:
        assert test_targets

        return CommandResult(
            command=[
                sys.executable,
                "-m",
                "pytest",
                *test_targets,
            ],
            exit_code=1,
            stdout="1 failed",
            stderr="AssertionError: deterministic failure injection",
        )

    def run_ci_gate(self) -> CommandResult:
        raise AssertionError(
            "CI gate must not run after targeted tests failed."
        )


class _FakeFailingImplementerCodex:
    """Deterministically fails implementation provider invocation."""

    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        return _FakeProviderResult(
            succeeded=False,
            text="Implementer failed deterministically for testing.",
        )

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        raise AssertionError(
            "Review must not run after implementation provider failure."
        )


class _CrashingCodex:
    """Raises instead of returning a result, simulating a hard crash."""

    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        raise RuntimeError("Simulated provider crash")

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        raise AssertionError(
            "Review must not run after an implementer crash."
        )


class _CountingCodex(_FakeCodex):
    """Tracks how many times implementation/review were invoked."""

    def __init__(self) -> None:
        self.implementation_calls = 0
        self.review_calls = 0

    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        self.implementation_calls += 1
        return _FakeProviderResult(text="Implementation complete.")

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        self.review_calls += 1
        return _FakeProviderResult(
            text="Review complete.\nVERDICT: PASS"
        )


class _CountingClaude(_FakeClaude):
    """Tracks how many times implementation/review were invoked."""

    def __init__(self) -> None:
        self.implementation_calls = 0
        self.review_calls = 0

    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort
        self.implementation_calls += 1
        return _FakeProviderResult(
            text="Implementation complete.",
            claude_json=True,
        )

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort
        self.review_calls += 1
        return _FakeProviderResult(
            text="Review complete.\nVERDICT: PASS",
            claude_json=True,
        )


class _AlwaysRejectFakeClaude(_FakeClaude):
    """Always requests changes; used to exhaust the fix/review budget."""

    def __init__(self) -> None:
        self.review_count = 0

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort

        self.review_count += 1

        return _FakeProviderResult(
            text="Still not acceptable.\nVERDICT: CHANGES_REQUIRED",
            claude_json=True,
        )


class _OneShotRejectFakeClaude(_FakeClaude):
    """Requests changes without a blocking finding, for one round."""

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort

        return _FakeProviderResult(
            text="Needs a fix.\nVERDICT: CHANGES_REQUIRED",
            claude_json=True,
        )


class _EscalationTrackingCodex(_FakeCodex):
    """Records which model each implementation call actually used."""

    def __init__(self) -> None:
        self.implementation_models: list[str] = []

    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
    ) -> _FakeProviderResult:
        assert prompt
        self.implementation_models.append(model)
        return _FakeProviderResult(text="Implementation complete.")


class _BlockerThenPassFakeClaude(_FakeClaude):
    """One genuine BLOCKER-severity defect, then a clean re-review."""

    def __init__(self) -> None:
        self.review_count = 0

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort

        self.review_count += 1

        if self.review_count == 1:
            return _FakeProviderResult(
                text=(
                    "A serious defect was found.\n"
                    "FINDING|BLOCKER|core/example.py|9|"
                    "Genuine difficult defect requiring escalation.\n"
                    "VERDICT: CHANGES_REQUIRED"
                ),
                claude_json=True,
            )

        return _FakeProviderResult(
            text="Fix confirmed.\nVERDICT: PASS",
            claude_json=True,
        )


class _AlwaysBlockerFakeClaude(_FakeClaude):
    """Every round returns a genuine BLOCKER-severity defect."""

    def __init__(self) -> None:
        self.review_count = 0

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort

        self.review_count += 1

        return _FakeProviderResult(
            text=(
                "Still broken.\n"
                "FINDING|BLOCKER|core/example.py|9|"
                "Still a genuine defect.\n"
                "VERDICT: CHANGES_REQUIRED"
            ),
            claude_json=True,
        )


class _MalformedFakeClaude(_FakeClaude):
    """Returns a malformed finding and no parseable verdict line."""

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort

        return _FakeProviderResult(
            text=(
                "FINDING|NOT_A_SEVERITY|||broken\n"
                "No structured verdict line provided."
            ),
            claude_json=True,
        )


class _JsonPassFakeClaude(_FakeClaude):
    """Simulates a Claude reviewer whose --json-schema was honored."""

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        assert effort
        return _FakeProviderResult(
            text=json.dumps({"verdict": "PASS", "findings": []}),
            claude_json=True,
        )


class _JsonPassFakeCodex(_FakeCodex):
    """Simulates a Codex reviewer whose --output-schema was honored.

    This is the exact scenario that would have prevented the real
    live-run failure: even if Codex's natural-language commentary
    forgot a VERDICT line, schema-enforced decoding makes "verdict" a
    required field it literally cannot omit.
    """

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        output_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        assert prompt
        assert model
        return _FakeProviderResult(
            text=json.dumps({"verdict": "PASS", "findings": []})
        )


class _PromptCapturingClaude(_FakeClaude):
    """Records every review prompt it receives; always passes."""

    def __init__(self) -> None:
        self.review_prompts: list[str] = []

    def run_read_only(
        self,
        *,
        prompt: str,
        model: str,
        effort: str,
        json_schema: dict[str, Any] | None = None,
    ) -> _FakeProviderResult:
        self.review_prompts.append(prompt)
        return _FakeProviderResult(
            text=json.dumps({"verdict": "PASS", "findings": []}),
            claude_json=True,
        )


class _ExhaustedImplementerCodex(_FakeCodex):
    """Implementation fails with a real-looking usage-limit diagnostic."""

    def run_implementation(
        self,
        *,
        prompt: str,
        model: str,
    ) -> _FakeProviderResult:
        result = _FakeProviderResult(succeeded=False, text="")
        result.stderr = "ERROR: You've hit your usage limit. Try again later."
        return result


class _HeadedGitGuard(_FakeGitGuard):
    """Snapshots carry a HEAD so the accepted baseline can be recorded."""

    def snapshot(self) -> Any:
        return SimpleNamespace(head="deadbeefcafe")


class _ResumeGitGuard(_FakeGitGuard):
    """Snapshots expose the files/HEAD a resumed review re-verifies."""

    def __init__(self, files: list[str], head: str = "deadbeefcafe") -> None:
        super().__init__()
        self.files = files
        self.head = head

    def snapshot(self) -> Any:
        return SimpleNamespace(files=tuple(self.files), head=self.head)


class _NoReviewCodex(_FakeCodex):
    def run_read_only(self, *, prompt: str, model: str, output_schema: dict[str, Any] | None = None) -> Any:
        raise AssertionError("Codex must not be invoked while its review is deferred")


class _FakeHeadMovedGitGuard:
    """Every diff reports unexpected Git HEAD movement."""

    def __init__(self) -> None:
        self.snapshot_count = 0

    def snapshot(self) -> Any:
        self.snapshot_count += 1
        head = (
            "before-sha"
            if self.snapshot_count % 2 == 1
            else "after-sha"
        )
        return SimpleNamespace(head=head)

    @staticmethod
    def diff(
        before: Any,
        after: Any,
    ) -> GitDelta:
        assert before is not after

        return GitDelta(
            changed_files=("core/example.py",),
            added_files=("core/example.py",),
            removed_files=(),
            head_changed=True,
        )


class _FixPhaseHeadMovedGitGuard:
    """Normal implementation diff, then unexpected HEAD movement on fix."""

    def __init__(self) -> None:
        self.diff_calls = 0
        self.snapshot_count = 0

    def snapshot(self) -> Any:
        self.snapshot_count += 1
        return SimpleNamespace(head=f"sha-{self.snapshot_count}")

    def diff(
        self,
        before: Any,
        after: Any,
    ) -> GitDelta:
        assert before is not after

        self.diff_calls += 1

        if self.diff_calls == 1:
            return GitDelta(
                changed_files=("core/example.py",),
                added_files=("core/example.py",),
                removed_files=(),
                head_changed=False,
            )

        return GitDelta(
            changed_files=("core/example.py",),
            added_files=(),
            removed_files=(),
            head_changed=True,
        )


def _assert_openai_strict_json_schema(
    schema: dict[str, Any],
    *,
    path: str = "$",
) -> None:
    """Recursively assert OpenAI-strict-mode JSON Schema compliance.

    Every object node must set additionalProperties: false and list
    EVERY property key in "required" (nullable typing expresses
    optionality instead). This is the exact rule Codex's real API
    enforces; violating it produces an immediate HTTP 400
    invalid_json_schema error before any review ever runs -- exactly
    the failure observed on the first schema-enforced live attempt.
    This test lets that class of bug be caught locally, offline,
    forever, without spending a provider call to rediscover it.
    """

    if schema.get("type") == "object":
        properties = schema.get("properties", {})

        assert schema.get("additionalProperties") is False, (
            f"{path}: object schema must set "
            "additionalProperties: false"
        )

        required = schema.get("required", [])

        assert set(required) == set(properties), (
            f"{path}: every property must be listed in 'required' "
            "under strict mode (use a nullable type for optional "
            f"fields) -- properties={sorted(properties)} "
            f"required={sorted(required)}"
        )

        for key, subschema in properties.items():
            _assert_openai_strict_json_schema(
                subschema,
                path=f"{path}.{key}",
            )

    items = schema.get("items")

    if isinstance(items, dict):
        _assert_openai_strict_json_schema(
            items,
            path=f"{path}[]",
        )


def _self_test() -> None:
    _assert_openai_strict_json_schema(
        ExecutionCycle._REVIEW_JSON_SCHEMA
    )

    repo_root = Path(__file__).resolve().parents[2]

    state_root = (
        repo_root
        / "tools"
        / "vector_dev_orchestrator"
        / ".execution_cycle_test_state"
    )

    laya_log_path = state_root / "laya_decisions.jsonl"
    laya_log_path.parent.mkdir(parents=True, exist_ok=True)
    laya_log_path.unlink(missing_ok=True)
    os.environ["VECTOR_LAYA_LOG_PATH"] = str(laya_log_path)

    orchestrator = DevOrchestrator(
        repo_root=repo_root,
        state_root=state_root,
    )

    from router import Difficulty

    task = orchestrator.prepare_task(
        description="Fix deterministic parser behavior and add regression test.",
        difficulty=Difficulty.SERIOUS,
        previous_owner=None,
    )

    cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=_FakeClaude(),
        runner=_FakeRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    result = cycle.run_once(
        task,
        test_targets=[
            "tests/test_example.py",
        ],
        run_ci_gate=True,
    )

    assert result.status is TaskStatus.PASS
    assert result.stage is TaskStage.COMPLETE
    assert len(result.tests) == 2
    assert all(test.passed for test in result.tests)

    assert result.changed_files == [
        "core/example.py",
        "tests/test_example.py",
    ]

    completion_rows = [
        row for row in read_decisions()
        if row["schema"] == "completion_review_required"
        and row["state"] == task.description
    ]
    assert len(completion_rows) == 1
    assert completion_rows[0]["choice"] is False
    assert completion_rows[0]["meta"]["changed_files"] == [
        "core/example.py",
        "tests/test_example.py",
    ]
    assert completion_rows[0]["meta"]["risk"] == "low"

    # Issue 3: bounded reviewer evidence was persisted before parsing.
    assert result.reviewer_evidence == [
        "Review complete.\nVERDICT: PASS"
    ]

    assert (
        cycle.parse_review_verdict(
            "Looks correct.\nVERDICT: PASS"
        )
        == "PASS"
    )

    assert (
        cycle.parse_review_verdict(
            "Looks suspicious."
        )
        == "CHANGES_REQUIRED"
    )

    # Issue 2: deterministic structured verdict parser regression matrix.
    assert cycle.parse_review_verdict("VERDICT: PASS") == "PASS"
    assert cycle.parse_review_verdict("  VERDICT: PASS  ") == "PASS"
    assert cycle.parse_review_verdict("**VERDICT: PASS**") == "PASS"
    assert cycle.parse_review_verdict("*VERDICT: PASS*") == "PASS"
    assert cycle.parse_review_verdict("`VERDICT: PASS`") == "PASS"
    assert cycle.parse_review_verdict("### VERDICT: PASS") == "PASS"
    assert cycle.parse_review_verdict("VERDICT: PASS.") == "PASS"
    assert cycle.parse_review_verdict("VERDICT: PASS!") == "PASS"
    assert cycle.parse_review_verdict("verdict: pass") == "PASS"

    # Verdict need not be the final line if uniquely identifiable.
    assert (
        cycle.parse_review_verdict(
            "VERDICT: PASS\n\nAdditional non-verdict commentary below."
        )
        == "PASS"
    )

    # Missing verdict.
    assert (
        cycle.parse_review_verdict("No structured verdict here.")
        == "CHANGES_REQUIRED"
    )
    assert cycle.parse_review_verdict("") == "CHANGES_REQUIRED"

    # Explicit CHANGES_REQUIRED.
    assert (
        cycle.parse_review_verdict("VERDICT: CHANGES_REQUIRED")
        == "CHANGES_REQUIRED"
    )

    # Duplicate verdicts (even identical) fail closed.
    assert (
        cycle.parse_review_verdict(
            "VERDICT: PASS\nVERDICT: PASS"
        )
        == "CHANGES_REQUIRED"
    )

    # Conflicting verdicts fail closed.
    assert (
        cycle.parse_review_verdict(
            "VERDICT: PASS\nVERDICT: CHANGES_REQUIRED"
        )
        == "CHANGES_REQUIRED"
    )

    # Ambiguous/embedded text must not be matched via unsafe substring
    # matching -- only a uniquely identifiable structured line counts.
    assert (
        cycle.parse_review_verdict("NOT_A_VERDICT: PASS")
        == "CHANGES_REQUIRED"
    )
    assert (
        cycle.parse_review_verdict(
            "I believe the VERDICT: PASS is warranted here."
        )
        == "CHANGES_REQUIRED"
    )

    # Structured JSON-schema review output (fix for the omitted-
    # VERDICT-line failure mode observed on the first live run):
    # parse_structured_review prefers a strict JSON contract match and
    # falls back to the legacy line protocol otherwise.
    json_pass_verdict, json_pass_findings = (
        ExecutionCycle.parse_structured_review(
            json.dumps({"verdict": "PASS", "findings": []})
        )
    )
    assert json_pass_verdict == "PASS"
    assert json_pass_findings == []

    (
        json_reject_verdict,
        json_reject_findings,
    ) = ExecutionCycle.parse_structured_review(
        json.dumps(
            {
                "verdict": "CHANGES_REQUIRED",
                "findings": [
                    {
                        "severity": "ERROR",
                        "file": "core/example.py",
                        "line": 12,
                        "summary": "Needs a fix.",
                    }
                ],
            }
        )
    )
    assert json_reject_verdict == "CHANGES_REQUIRED"
    assert len(json_reject_findings) == 1
    assert json_reject_findings[0].severity is ReviewSeverity.ERROR
    assert json_reject_findings[0].file == "core/example.py"
    assert json_reject_findings[0].line == 12
    assert json_reject_findings[0].summary == "Needs a fix."

    # Case-insensitive verdict token and a null file/line are accepted.
    (
        json_lower_verdict,
        json_lower_findings,
    ) = ExecutionCycle.parse_structured_review(
        json.dumps(
            {
                "verdict": "pass",
                "findings": [
                    {
                        "severity": "info",
                        "file": None,
                        "line": None,
                        "summary": "Looks fine.",
                    }
                ],
            }
        )
    )
    assert json_lower_verdict == "PASS"
    assert len(json_lower_findings) == 1
    assert json_lower_findings[0].severity is ReviewSeverity.INFO
    assert json_lower_findings[0].file is None
    assert json_lower_findings[0].line is None

    # A malformed JSON finding item still fails closed as BLOCKER,
    # exactly like a malformed FINDING line does in text mode.
    (
        malformed_json_verdict,
        malformed_json_findings,
    ) = ExecutionCycle.parse_structured_review(
        json.dumps(
            {
                "verdict": "PASS",
                "findings": [{"file": "x.py"}],
            }
        )
    )
    assert malformed_json_verdict == "PASS"
    assert len(malformed_json_findings) == 1
    assert (
        malformed_json_findings[0].severity is ReviewSeverity.BLOCKER
    )

    # 'findings' present but not a list also fails closed as BLOCKER.
    (
        bad_shape_verdict,
        bad_shape_findings,
    ) = ExecutionCycle.parse_structured_review(
        json.dumps({"verdict": "PASS", "findings": "not-a-list"})
    )
    assert bad_shape_verdict == "PASS"
    assert len(bad_shape_findings) == 1
    assert bad_shape_findings[0].severity is ReviewSeverity.BLOCKER

    # JSON without our "verdict" contract is not mistaken for a
    # structured review -- falls back to the text protocol, which
    # fails closed on a missing verdict.
    (
        other_json_verdict,
        other_json_findings,
    ) = ExecutionCycle.parse_structured_review(
        json.dumps({"some_other_field": "value"})
    )
    assert other_json_verdict == "CHANGES_REQUIRED"
    assert other_json_findings == []

    # Reproduces the EXACT real-world failure from the first live run:
    # substantively positive prose with no parseable verdict of any
    # kind (JSON or text) must still fail closed to CHANGES_REQUIRED.
    real_world_prose = (
        "Review complete. No actionable defects found.\n\n"
        "- Change is limited to adding assertions.\n"
        "- Direct runtime validation passed.\n"
        "- `git diff --check` passed."
    )
    (
        real_world_verdict,
        real_world_findings,
    ) = ExecutionCycle.parse_structured_review(real_world_prose)
    assert real_world_verdict == "CHANGES_REQUIRED"
    assert real_world_findings == []

    # Legacy text protocol still works unchanged when JSON isn't used
    # at all (regression safety -- this is the fallback path).
    (
        legacy_verdict,
        legacy_findings,
    ) = ExecutionCycle.parse_structured_review(
        "Looks correct.\nVERDICT: PASS"
    )
    assert legacy_verdict == "PASS"
    assert legacy_findings == []

    # Bounded, secret-redacted reviewer evidence (issue 3).
    huge_secret_text = (
        "Bearer sk-abcdefghijklmnopqrstuvwxyz0123456789\n"
        + ("Filler review commentary line.\n" * 500)
        + "VERDICT: PASS"
    )

    bounded_evidence = ExecutionCycle._bounded_reviewer_evidence(
        huge_secret_text
    )

    assert "[REDACTED]" in bounded_evidence
    assert (
        "sk-abcdefghijklmnopqrstuvwxyz0123456789"
        not in bounded_evidence
    )
    assert (
        len(bounded_evidence)
        <= ExecutionCycle._MAX_REVIEWER_EVIDENCE_CHARS + 100
    )
    assert "truncated for bounded audit storage" in bounded_evidence

    parsed_findings = cycle.parse_review_findings(
        (
            "FINDING|ERROR|core/parser.py|27|"
            "Incorrect parser state transition.\n"
            "VERDICT: CHANGES_REQUIRED"
        )
    )

    assert len(parsed_findings) == 1
    assert parsed_findings[0].severity is ReviewSeverity.ERROR
    assert parsed_findings[0].file == "core/parser.py"
    assert parsed_findings[0].line == 27
    assert (
        parsed_findings[0].summary
        == "Incorrect parser state transition."
    )

    malformed_findings = cycle.parse_review_findings(
        "FINDING|NOT_A_SEVERITY|||broken"
    )

    assert len(malformed_findings) == 1
    assert (
        malformed_findings[0].severity
        is ReviewSeverity.BLOCKER
    )

    claude_result = _FakeProviderResult(
        text="Reviewed.\nVERDICT: PASS",
        claude_json=True,
    )

    extracted = cycle._extract_result_text(
        claude_result
    )

    assert extracted.endswith(
        "VERDICT: PASS"
    )

    # Reviewer rejection -> implementer fix -> tests -> re-review PASS.
    retry_task = orchestrator.prepare_task(
        description=(
            "Fix deterministic parser behavior after independent review."
        ),
        difficulty=Difficulty.SERIOUS,
        previous_owner=Provider.CLAUDE,
    )

    retry_reviewer = _RetryFakeClaude()

    retry_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=retry_reviewer,
        runner=_FakeRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    retry_result = retry_cycle.run_once(
        retry_task,
        test_targets=[
            "tests/test_example.py",
        ],
        run_ci_gate=False,
    )

    assert retry_result.status is TaskStatus.PASS
    assert retry_result.stage is TaskStage.COMPLETE

    # One initial implementation test + one post-fix test.
    assert len(retry_result.tests) == 2
    assert all(test.passed for test in retry_result.tests)

    # Exactly one bounded fix attempt was needed.
    assert retry_result.retry_count == 1

    # Independent reviewer saw the implementation twice.
    assert retry_reviewer.review_count == 2

    # Structured finding from the rejected review was persisted.
    assert len(retry_result.review_findings) == 1

    finding = retry_result.review_findings[0]

    assert finding.severity is ReviewSeverity.ERROR
    assert finding.file == "core/example.py"
    assert finding.line == 12
    assert (
        finding.summary
        == "Parser must handle the reviewed edge case."
    )

    # The subsequent full-tree re-review superseded that finding.
    assert finding.resolved is True

    assert any(
        "Reviewer verdict: CHANGES_REQUIRED." in note
        for note in retry_result.notes
    )

    assert any(
        "Fix attempt 1 completed" in note
        for note in retry_result.notes
    )

    assert any(
        "Reviewer verdict: PASS." in note
        for note in retry_result.notes
    )

    # Issue 3: one bounded evidence snapshot persisted per review round.
    assert len(retry_result.reviewer_evidence) == 2
    assert "CHANGES_REQUIRED" in retry_result.reviewer_evidence[0]
    assert "VERDICT: PASS" in retry_result.reviewer_evidence[1]

    risky_task = orchestrator.prepare_task(
        description="Make a harmless parser cleanup.",
        difficulty=Difficulty.ROUTINE,
        previous_owner=task.owner,
    )

    risky_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=_FakeClaude(),
        runner=_FakeRunner(),
        git_guard=_FakeRiskyGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    risky_result = risky_cycle.run_once(
        risky_task,
        test_targets=[
            "tests/test_example.py",
        ],
        run_ci_gate=False,
    )

    assert risky_result.status is TaskStatus.NEEDS_HUMAN

    assert risky_result.changed_files == [
        "core/security/token_manager.py",
    ]

    assert risky_result.tests == []

    assert any(
        "Postflight safety finding:" in note
        for note in risky_result.notes
    )

    # --- Structured-output/schema enforcement, both ownership
    #     directions (fix for the omitted-VERDICT-line live failure) --

    # Claude implements -> Codex reviews via schema-enforced JSON.
    claude_owns_task = orchestrator.prepare_task(
        description=(
            "Fix deterministic parser cleanup with Codex reviewing "
            "via structured JSON schema output."
        ),
        difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CODEX,
    )

    assert claude_owns_task.owner is Provider.CLAUDE
    assert claude_owns_task.reviewer is Provider.CODEX

    claude_owns_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_JsonPassFakeCodex(),
        claude=_FakeClaude(),
        runner=_FakeRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    claude_owns_result = claude_owns_cycle.run_once(
        claude_owns_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert claude_owns_result.status is TaskStatus.PASS
    assert claude_owns_result.stage is TaskStage.COMPLETE
    assert claude_owns_result.review_findings == []
    assert claude_owns_result.reviewer_evidence == [
        json.dumps({"verdict": "PASS", "findings": []})
    ]

    # Codex implements -> Claude reviews via schema-enforced JSON.
    codex_owns_task = orchestrator.prepare_task(
        description=(
            "Fix deterministic parser cleanup with Claude reviewing "
            "via structured JSON schema output."
        ),
        difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CLAUDE,
    )

    assert codex_owns_task.owner is Provider.CODEX
    assert codex_owns_task.reviewer is Provider.CLAUDE

    codex_owns_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=_JsonPassFakeClaude(),
        runner=_FakeRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    codex_owns_result = codex_owns_cycle.run_once(
        codex_owns_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert codex_owns_result.status is TaskStatus.PASS
    assert codex_owns_result.stage is TaskStage.COMPLETE
    assert codex_owns_result.review_findings == []
    assert codex_owns_result.reviewer_evidence == [
        json.dumps({"verdict": "PASS", "findings": []})
    ]

    # --- Bounded escalation (section 6) --------------------------------

    # A genuine BLOCKER-severity finding escalates the implementer
    # difficulty exactly one tier for the bounded fix attempt, then a
    # clean re-review passes. Never triggered by malformed output,
    # tooling bugs, HEAD movement or approval gates (those are covered
    # separately and produce no escalation).
    escalation_task = orchestrator.prepare_task(
        description="Implement the ordinary feature as described.",
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )
    assert escalation_task.owner is Provider.CODEX
    assert escalation_task.difficulty is Difficulty.ROUTINE
    assert escalation_task.implementer_model is not None
    assert escalation_task.implementer_model.model == "gpt-5.6-terra"

    tracking_codex = _EscalationTrackingCodex()
    blocker_then_pass_claude = _BlockerThenPassFakeClaude()

    escalation_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=tracking_codex,
        claude=blocker_then_pass_claude,
        runner=_FakeRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    escalation_result = escalation_cycle.run_once(
        escalation_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert escalation_result.status is TaskStatus.PASS
    assert escalation_result.escalation_count == 1
    assert escalation_result.difficulty is Difficulty.SERIOUS
    assert tracking_codex.implementation_models == [
        "gpt-5.6-terra",  # initial implementation, original ROUTINE tier
        "gpt-5.6-sol",  # bounded fix attempt, escalated SERIOUS tier
    ]
    assert any(
        "Escalated implementer difficulty routine -> serious" in note
        for note in escalation_result.notes
    )

    # Escalation ceiling: even when BLOCKER findings keep recurring
    # across every bounded fix round, escalation fires AT MOST
    # max_escalations (default 1) times -- never an unbounded ladder
    # climb, and never an infinite loop (the existing retry budget
    # still terminates the cycle deterministically).
    ceiling_task = orchestrator.prepare_task(
        description="Implement the ordinary feature as described.",
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )
    ceiling_task.max_retries = 2
    orchestrator.state.save(ceiling_task)

    ceiling_codex = _EscalationTrackingCodex()
    always_blocker_claude = _AlwaysBlockerFakeClaude()

    ceiling_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=ceiling_codex,
        claude=always_blocker_claude,
        runner=_FakeRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    ceiling_result = ceiling_cycle.run_once(
        ceiling_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert ceiling_result.status is TaskStatus.BLOCKED
    assert ceiling_result.retry_count == 2
    # Bounded at max_escalations=1 despite three consecutive BLOCKER
    # rounds -- escalation never re-fires once the ceiling is reached.
    assert ceiling_result.escalation_count == 1
    assert ceiling_result.max_escalations == 1
    assert not ceiling_result.can_escalate()
    assert always_blocker_claude.review_count == 3
    assert ceiling_codex.implementation_models == [
        "gpt-5.6-terra",  # initial
        "gpt-5.6-sol",  # fix 1: escalated once
        "gpt-5.6-sol",  # fix 2: NOT escalated again (ceiling reached)
    ]

    # --- Failure-injection coverage (issue 6) -------------------------

    # 1. Unexpected provider-caused HEAD movement during IMPLEMENTATION
    #    must fail closed immediately: no tests, no review, no fix.
    head_moved_task = orchestrator.prepare_task(
        description="Attempt a harmless parser cleanup.",
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )

    counting_codex_for_head_move = _CountingCodex()
    counting_claude_for_head_move = _CountingClaude()

    head_moved_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=counting_codex_for_head_move,
        claude=counting_claude_for_head_move,
        runner=_AssertNeverRunner(),
        git_guard=_FakeHeadMovedGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    head_moved_result = head_moved_cycle.run_once(
        head_moved_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=True,
    )

    assert head_moved_result.status is TaskStatus.NEEDS_HUMAN
    assert head_moved_result.stage is TaskStage.WAITING_APPROVAL
    assert head_moved_result.tests == []
    assert head_moved_result.changed_files == ["core/example.py"]

    assert any(
        "SAFETY VIOLATION" in note and "implementation" in note
        for note in head_moved_result.notes
    )
    assert any(
        "HEAD before=before-sha after=after-sha" in note
        for note in head_moved_result.notes
    )

    assert (
        counting_codex_for_head_move.review_calls
        + counting_claude_for_head_move.review_calls
        == 0
    )
    assert (
        counting_codex_for_head_move.implementation_calls
        + counting_claude_for_head_move.implementation_calls
        == 1
    )

    # 2. Unexpected provider-caused HEAD movement during a FIX ATTEMPT
    #    must also fail closed immediately, without a post-fix retest.
    fix_head_moved_task = orchestrator.prepare_task(
        description=(
            "Attempt a harmless parser cleanup requiring one fix round."
        ),
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )

    fix_head_moved_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=_OneShotRejectFakeClaude(),
        runner=_FakeRunner(),
        git_guard=_FixPhaseHeadMovedGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    fix_head_moved_result = fix_head_moved_cycle.run_once(
        fix_head_moved_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert fix_head_moved_result.status is TaskStatus.NEEDS_HUMAN
    assert fix_head_moved_result.stage is TaskStage.WAITING_APPROVAL

    assert any(
        "SAFETY VIOLATION" in note and "fix attempt" in note
        for note in fix_head_moved_result.notes
    )

    # Initial implementation + one targeted test run happened; the
    # post-fix retest must never have occurred.
    assert len(fix_head_moved_result.tests) == 1

    # 3. Implementation provider invocation failure.
    provider_failure_task = orchestrator.prepare_task(
        description=(
            "Attempt a harmless parser cleanup with a failing implementer."
        ),
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )

    assert provider_failure_task.owner is Provider.CODEX

    provider_failure_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeFailingImplementerCodex(),
        claude=_FakeClaude(),
        runner=_AssertNeverRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    provider_failure_result = provider_failure_cycle.run_once(
        provider_failure_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert provider_failure_result.status is TaskStatus.BLOCKED
    assert provider_failure_result.stage is TaskStage.COMPLETE
    assert provider_failure_result.tests == []
    assert any(
        "Implementation provider diagnostics:" in note
        for note in provider_failure_result.notes
    )
    assert any(
        "Implementation provider invocation failed." in note
        for note in provider_failure_result.notes
    )

    # 4. Targeted test failure after a successful implementation.
    test_failure_task = orchestrator.prepare_task(
        description=(
            "Attempt a harmless parser cleanup with failing targeted tests."
        ),
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )

    test_failure_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=_FakeClaude(),
        runner=_FakeFailingRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    test_failure_result = test_failure_cycle.run_once(
        test_failure_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert test_failure_result.status is TaskStatus.BLOCKED
    assert len(test_failure_result.tests) == 1
    assert not test_failure_result.tests[0].passed
    assert any(
        "Targeted tests failed after implementation." in note
        for note in test_failure_result.notes
    )

    # 5. Reviewer rejection with the fix/review retry budget exhausted;
    #    proves the loop is bounded, never infinite.
    exhaustion_task = orchestrator.prepare_task(
        description=(
            "Attempt a harmless parser cleanup that the reviewer "
            "always rejects."
        ),
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )
    exhaustion_task.max_retries = 1
    orchestrator.state.save(exhaustion_task)

    counting_fix_codex = _CountingCodex()
    always_reject_claude = _AlwaysRejectFakeClaude()

    exhaustion_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=counting_fix_codex,
        claude=always_reject_claude,
        runner=_FakeRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    exhaustion_result = exhaustion_cycle.run_once(
        exhaustion_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert exhaustion_result.status is TaskStatus.BLOCKED
    assert exhaustion_result.retry_count == 1
    assert always_reject_claude.review_count == 2
    assert counting_fix_codex.implementation_calls == 2
    assert any(
        "retry budget is exhausted" in note
        for note in exhaustion_result.notes
    )
    assert len(exhaustion_result.reviewer_evidence) == 2

    # 6. Malformed reviewer output remains fail closed: a malformed
    #    finding parses as BLOCKER and a missing verdict line parses as
    #    CHANGES_REQUIRED.
    malformed_task = orchestrator.prepare_task(
        description=(
            "Attempt a harmless parser cleanup with malformed "
            "reviewer output."
        ),
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )
    malformed_task.max_retries = 0
    orchestrator.state.save(malformed_task)

    malformed_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=_MalformedFakeClaude(),
        runner=_FakeRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    malformed_result = malformed_cycle.run_once(
        malformed_task,
        test_targets=["tests/test_example.py"],
        run_ci_gate=False,
    )

    assert malformed_result.status is TaskStatus.BLOCKED
    assert len(malformed_result.review_findings) == 1
    assert (
        malformed_result.review_findings[0].severity
        is ReviewSeverity.BLOCKER
    )
    assert any(
        "Reviewer verdict: CHANGES_REQUIRED." in note
        for note in malformed_result.notes
    )

    # 7. Crash/exception handling: a hard provider crash must propagate
    #    rather than being silently swallowed into a false PASS, and the
    #    task must be left non-terminal (RUNNING) rather than continuing
    #    unsafely. TaskQueue.recover_after_restart (see task_queue.py's
    #    own self-test) is what routes an interrupted RUNNING task to
    #    NEEDS_HUMAN on the next restart instead of silently replaying it.
    crash_task = orchestrator.prepare_task(
        description=(
            "Attempt a harmless parser cleanup with a crashing provider."
        ),
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )

    crash_cycle = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_CrashingCodex(),
        claude=_FakeClaude(),
        runner=_AssertNeverRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    )

    try:
        crash_cycle.run_once(
            crash_task,
            test_targets=["tests/test_example.py"],
            run_ci_gate=False,
        )
    except RuntimeError as exc:
        assert "Simulated provider crash" in str(exc)
    else:
        raise AssertionError(
            "A crashing provider must propagate, never be swallowed "
            "into a false PASS/continuation."
        )

    assert crash_task.status is TaskStatus.RUNNING
    assert not crash_task.is_terminal()

    # No stage in this module ever calls git commit/push/merge -- every
    # CommandRunner/GitGuard call above is either a fake or, in the
    # non-fake `_self_test` modules, read-only status/diff/rev-parse.
    # Combined with the assertions above (no PASS on any failure path,
    # no auto-continuation past a fail-closed guard), this satisfies
    # "no failure may cause commit/push/merge or unsafe continuation".

    # --- Supervisor-era safety additions --------------------------------
    from models import TaskSpec

    # allowed-path pattern matching
    assert ExecutionCycle._path_allowed("core/a.py", ["core/"])
    assert ExecutionCycle._path_allowed("core/sub/a.py", ["core/**"])
    assert ExecutionCycle._path_allowed("tests/test_a.py", ["tests/test_*.py"])
    assert ExecutionCycle._path_allowed("x/y.py", ["x/y.py"])
    assert not ExecutionCycle._path_allowed("core2/a.py", ["core/"])
    assert not ExecutionCycle._path_allowed("other.py", ["core/", "tests/test_*.py"])
    # dotted directories are not confused with their undotted look-alikes
    assert ExecutionCycle._path_allowed(".github/w.yml", [".github/"])
    assert not ExecutionCycle._path_allowed(".github/w.yml", ["github/"])
    assert not ExecutionCycle._path_allowed("../escape.py", ["escape.py"])

    # A change outside allowed_paths fails closed BEFORE any test/review.
    scope_task = orchestrator.prepare_task(
        description="Attempt a harmless parser cleanup with a strict scope.",
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
        spec=TaskSpec(allowed_paths=("tests/",), test_targets=("tests/test_example.py",)),
    )
    scope_result = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=_FakeClaude(),
        runner=_AssertNeverRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    ).run_once(scope_task, test_targets=["tests/test_example.py"])
    assert scope_result.status is TaskStatus.BLOCKED
    assert scope_result.tests == []
    assert any("SCOPE VIOLATION" in n and "core/example.py" in n for n in scope_result.notes)
    assert scope_result.allowed_paths == ["tests/"]

    # Independence + evidence: the reviewer gets the spec, accepted baseline,
    # raw test output and an explicit instruction NOT to defer.
    spec_task = orchestrator.prepare_task(
        description="Attempt a harmless parser cleanup with a full spec.",
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
        spec=TaskSpec(
            objective="Tidy the parser helper without changing behaviour.",
            allowed_paths=("core/", "tests/"),
            forbidden_scope=("public API renames",),
            acceptance_criteria=("existing parser tests still pass",),
            test_targets=("tests/test_example.py",),
        ),
    )
    capturing = _PromptCapturingClaude()
    spec_result = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_FakeCodex(),
        claude=capturing,
        runner=_FakeRunner(),
        git_guard=_HeadedGitGuard(),
        postflight_guard=PostflightGuard(),
        evidence_fn=lambda t: (
            f"ACCEPTED BASELINE COMMIT: {t.baseline_commit}\n"
            "RAW TEST OUTPUT (tail):\n1 passed"
        ),
    ).run_once(spec_task, test_targets=["tests/test_example.py"])
    assert spec_result.status is TaskStatus.PASS
    assert spec_result.baseline_commit == "deadbeefcafe"
    assert spec_result.provider_calls == 2, "one implementer + one reviewer call actually happened"
    prompt = capturing.review_prompts[0]
    for needle in (
        "INDEPENDENCE", "Do not defer to", "ACCEPTED BASELINE COMMIT: deadbeefcafe",
        "OBJECTIVE:", "ACCEPTANCE CRITERIA:", "existing parser tests still pass",
        "FORBIDDEN SCOPE:", "ALLOWED MUTATION PATHS", "1 passed",
    ):
        assert needle in prompt, needle
    assert "do not soften findings" in prompt.lower()
    assert "confirm the implementer" not in prompt.lower()

    # Real evidence collector: diff + new file, bounded and secret-redacted.
    import shutil as _shutil
    import subprocess as _sp
    import tempfile as _tf

    ev_root = Path(_tf.mkdtemp(prefix="vector_evidence_test_"))
    try:
        def _g(*a: str) -> None:
            _sp.run(["git", "-C", str(ev_root), *a], check=True, capture_output=True)

        _g("init", "-q")
        _g("config", "user.email", "e@example.invalid")
        _g("config", "user.name", "E")
        (ev_root / "a.py").write_text("x = 1\n", encoding="utf-8")
        _g("add", "a.py")
        _g("commit", "-q", "-m", "base")
        (ev_root / "a.py").write_text(
            "x = 2\nKEY = 'sk-abcdefghijklmnopqrstuvwxyz0123456789'\n" + "y = 0\n" * 6000,
            encoding="utf-8",
        )
        (ev_root / "new.py").write_text("brand_new = True\n", encoding="utf-8")
        ev_task = DevTask(description="evidence")
        ev_task.baseline_commit = "abc123"
        ev_task.changed_files = ["a.py", "new.py"]
        ev_task.tests.append(TestResult(
            command="pytest", exit_code=1, passed=False,
            stdout="FAILED test_x\nBearer abcdefghijklmnopqrstuvwxyz012345", stderr="",
        ))
        evidence = ExecutionCycle(
            ev_root, orchestrator=orchestrator, codex=_FakeCodex(), claude=_FakeClaude(),
            runner=_FakeRunner(), git_guard=_FakeGitGuard(), postflight_guard=PostflightGuard(),
        )._collect_review_evidence(ev_task)
        assert "ACCEPTED BASELINE COMMIT: abc123" in evidence
        assert "-x = 1" in evidence and "+x = 2" in evidence
        assert "NEW FILE new.py" in evidence and "brand_new = True" in evidence
        assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in evidence
        assert "Bearer abcdefghijklmnopqrstuvwxyz012345" not in evidence
        assert "[REDACTED]" in evidence
        assert "exit_code=1 passed=False" in evidence and "FAILED test_x" in evidence
        assert len(evidence) < ExecutionCycle._MAX_EVIDENCE_CHARS + 6000, len(evidence)
    finally:
        _shutil.rmtree(ev_root, ignore_errors=True)

    # A quota/rate-limit stop is flagged (not treated as a capability issue).
    exhausted_task = orchestrator.prepare_task(
        description="Attempt a harmless parser cleanup during a usage limit.",
        difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )
    assert exhausted_task.owner is Provider.CODEX
    exhausted_result = ExecutionCycle(
        repo_root,
        orchestrator=orchestrator,
        codex=_ExhaustedImplementerCodex(),
        claude=_FakeClaude(),
        runner=_AssertNeverRunner(),
        git_guard=_FakeGitGuard(),
        postflight_guard=PostflightGuard(),
    ).run_once(exhausted_task, test_targets=["tests/test_example.py"])
    assert exhausted_result.status is TaskStatus.BLOCKED
    assert "PROVIDER_UNAVAILABLE:codex" in exhausted_result.notes
    assert exhausted_result.provider_calls == 1, "reviewer was never reached, so it is not counted"
    assert exhausted_result.escalation_count == 0

    # --- POLICY.md sec. 10: reviewer provider in EMERGENCY -> WAITING_REVIEW, never PASS ----
    from models import QuotaBand

    edited = ["core/example.py", "tests/test_example.py"]
    emergency = {Provider.CODEX: QuotaBand.EMERGENCY, Provider.CLAUDE: QuotaBand.NORMAL}

    def deferred_cycle(codex: Any, guard: Any, runner: Any | None = None) -> ExecutionCycle:
        return ExecutionCycle(
            repo_root, orchestrator=orchestrator, codex=codex, claude=_FakeClaude(),
            runner=runner or _FakeRunner(), git_guard=guard, postflight_guard=PostflightGuard(),
        )

    first = orchestrator.prepare_task(
        description="Attempt a harmless parser cleanup under a Codex emergency.",
        difficulty=Difficulty.ROUTINE, previous_owner=Provider.CODEX, quota_bands=emergency,
    )
    assert first.owner is Provider.CLAUDE and first.reviewer is Provider.CODEX and first.review_deferred
    waiting = deferred_cycle(_NoReviewCodex(), _ResumeGitGuard(edited)).run_once(
        first, test_targets=["tests/test_example.py"]
    )
    assert waiting.status is TaskStatus.WAITING_REVIEW and not waiting.is_terminal()
    assert waiting.provider_calls == 1, "only the implementer ran; Codex was never invoked"
    assert waiting.reviewer_evidence == [] and waiting.tests[-1].passed
    assert waiting.changed_files == edited
    assert any("DEFERRED" in n and "NOT a pass" in n for n in waiting.notes)
    assert orchestrator.load_task(waiting.task_id).status is TaskStatus.WAITING_REVIEW, "persisted"
    assert PostflightGuard is not None and orchestrator.load_task(waiting.task_id).review_deferred

    try:
        deferred_cycle(_NoReviewCodex(), _ResumeGitGuard(edited)).run_once(waiting, test_targets=["tests/test_example.py"])
    except RuntimeError as exc:
        assert "WAITING_REVIEW" in str(exc)
    else:
        raise AssertionError("run_once must refuse a task that is waiting for review")

    try:
        deferred_cycle(_FakeCodex(), _ResumeGitGuard(edited)).resume_review(
            orchestrator.prepare_task(description="Not waiting for anything.", difficulty=Difficulty.ROUTINE),
            test_targets=["tests/test_example.py"],
        )
    except RuntimeError as exc:
        assert "not WAITING_REVIEW" in str(exc)
    else:
        raise AssertionError("resume_review must refuse a task that is not waiting")

    # The reviewer is available again: the review runs, the tests re-run, then PASS.
    resumed = deferred_cycle(_FakeCodex(), _ResumeGitGuard(edited)).resume_review(
        orchestrator.load_task(waiting.task_id), test_targets=["tests/test_example.py"]
    )
    assert resumed.status is TaskStatus.PASS and resumed.review_deferred is False
    assert resumed.provider_calls == 2 and len(resumed.reviewer_evidence) == 1
    assert len(resumed.tests) == 2, "targeted tests were re-run on resume"

    # Fail closed: the worktree changed (or HEAD moved) while waiting -> no review, no PASS.
    for label, guard in (
        ("stray file", _ResumeGitGuard(edited + ["core/sneaky.py"])),
        ("missing file", _ResumeGitGuard(edited[:1])),
        ("head moved", _ResumeGitGuard(edited, head="0123456789ab")),
    ):
        pending = deferred_cycle(_NoReviewCodex(), _ResumeGitGuard(edited)).run_once(
            orchestrator.prepare_task(
                description=f"Attempt a harmless parser cleanup ({label}).",
                difficulty=Difficulty.ROUTINE, previous_owner=Provider.CODEX, quota_bands=emergency,
            ),
            test_targets=["tests/test_example.py"],
        )
        assert pending.status is TaskStatus.WAITING_REVIEW
        stopped = deferred_cycle(_NoReviewCodex(), guard).resume_review(
            pending, test_targets=["tests/test_example.py"]
        )
        assert stopped.status is TaskStatus.BLOCKED, label
        assert any("changed while" in n for n in stopped.notes), label
        assert stopped.provider_calls == 1 and stopped.reviewer_evidence == [], label

    # Tests that no longer pass block the resumed review too (Codex not invoked).
    failing_pending = deferred_cycle(_NoReviewCodex(), _ResumeGitGuard(edited)).run_once(
        orchestrator.prepare_task(
            description="Attempt a harmless parser cleanup (tests break).",
            difficulty=Difficulty.ROUTINE, previous_owner=Provider.CODEX, quota_bands=emergency,
        ),
        test_targets=["tests/test_example.py"],
    )
    broken = deferred_cycle(_NoReviewCodex(), _ResumeGitGuard(edited), _FakeFailingRunner()).resume_review(
        failing_pending, test_targets=["tests/test_example.py"]
    )
    assert broken.status is TaskStatus.BLOCKED and "deferred review resumed" in broken.notes[-1]

    # Both providers healthy: no deferral, normal single-pass cycle, unchanged.
    normal = orchestrator.prepare_task(
        description="Attempt a harmless parser cleanup with healthy quotas.",
        difficulty=Difficulty.ROUTINE, previous_owner=Provider.CODEX,
        quota_bands={Provider.CODEX: QuotaBand.NORMAL, Provider.CLAUDE: QuotaBand.NORMAL},
    )
    assert not normal.review_deferred and not normal.ownership_note

    # Re-review prompts carry the implementer identity, changed files and previous structured findings.
    prompt_task = orchestrator.prepare_task(
        description="Attempt a harmless parser cleanup with prior findings.",
        difficulty=Difficulty.ROUTINE, previous_owner=Provider.CODEX,
    )
    prompt_task.changed_files = edited
    prompt_task.review_findings.append(
        ReviewFinding(ReviewSeverity.ERROR, "off-by-one in the loop bound", "core/example.py", 12, resolved=True)
    )
    review_text = ExecutionCycle.build_review_prompt(task=prompt_task, test_targets=["tests/test_example.py"])
    assert f"IMPLEMENTED BY: {prompt_task.owner.value}" in review_text
    assert "ACTUAL CHANGED FILES: core/example.py, tests/test_example.py" in review_text
    assert "PREVIOUS STRUCTURED FINDINGS" in review_text and "off-by-one in the loop bound" in review_text
    assert "core/example.py:12" in review_text

    # Laya decision logging also captures postflight_guard's own
    # requires_human=True verdict (the deterministic ground-truth label;
    # no Laya prediction exists yet in this pass). Exercised directly
    # against _log_postflight_decision rather than hunting for a natural
    # risky-file scenario among the many ExecutionCycle runs above.
    risky_task = DevTask(description="Bump the pinned dependency version.")
    risky_postflight = PostflightGuard().evaluate(["requirements.txt"])
    assert risky_postflight.requires_human
    _log_postflight_decision(risky_task, risky_postflight, ["requirements.txt"])

    risky_completion_rows = [
        row for row in read_decisions()
        if row["schema"] == "completion_review_required"
        and row["state"] == risky_task.description
    ]
    assert len(risky_completion_rows) == 1
    assert risky_completion_rows[0]["choice"] is True
    assert risky_completion_rows[0]["meta"]["risk"] == "high"
    assert (
        risky_completion_rows[0]["meta"]["findings"][0]["path"]
        == "requirements.txt"
    )

    os.environ.pop("VECTOR_LAYA_LOG_PATH", None)
    laya_log_path.unlink(missing_ok=True)

    for task_id in orchestrator.state.list_task_ids():
        path = (
            state_root
            / "tasks"
            / f"{task_id}.json"
        )

        if path.exists():
            path.unlink()

    tasks_dir = state_root / "tasks"

    if tasks_dir.exists():
        tasks_dir.rmdir()

    if state_root.exists():
        import shutil
        shutil.rmtree(state_root)


if __name__ == "__main__":
    _self_test()





