"""Persistent task state storage for the VECTOR development orchestrator."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from models import (
    ApprovalRequirement,
    DevTask,
    Difficulty,
    ModelChoice,
    Provider,
    QuotaBand,
    ReviewFinding,
    ReviewSeverity,
    RiskLevel,
    TaskCategory,
    TaskStage,
    TaskStatus,
    TestResult,
)
from text_signals import safe_state_id


class StateStore:
    """Persist DevTask state safely as JSON files."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.tasks_dir = self.root / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{safe_state_id(task_id, field='task_id')}.json"

    def save(self, task: DevTask) -> Path:
        path = self._task_path(task.task_id)
        payload = task.to_dict()

        fd, temp_name = tempfile.mkstemp(
            prefix=f"{task.task_id}.",
            suffix=".tmp",
            dir=self.tasks_dir,
            text=True,
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())

            Path(temp_name).replace(path)
        except Exception:
            try:
                Path(temp_name).unlink(missing_ok=True)
            finally:
                raise

        return path

    def load(self, task_id: str) -> DevTask:
        path = self._task_path(task_id)

        if not path.exists():
            raise FileNotFoundError(f"Task state not found: {task_id}")

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Task state is corrupted and will not be overwritten: {path}"
            ) from exc

        return self._from_dict(payload)

    def list_task_ids(self) -> list[str]:
        return sorted(path.stem for path in self.tasks_dir.glob("*.json"))

    def _from_dict(self, data: dict[str, Any]) -> DevTask:
        task = DevTask(
            description=data["description"],
            task_id=data["task_id"],
            status=TaskStatus(data["status"]),
            stage=TaskStage(data["stage"]),
            risk=RiskLevel(data["risk"]),
            owner=Provider(data["owner"]) if data.get("owner") else None,
            reviewer=Provider(data["reviewer"]) if data.get("reviewer") else None,
            implementer_model=self._model_choice(data.get("implementer_model")),
            reviewer_model=self._model_choice(data.get("reviewer_model")),
            difficulty=Difficulty(
                data.get("difficulty", Difficulty.ROUTINE.value)
            ),
            task_category=TaskCategory(
                data.get("task_category", TaskCategory.IMPLEMENTATION.value)
            ),
            quota_band_at_routing=QuotaBand(
                data.get("quota_band_at_routing", QuotaBand.UNKNOWN.value)
            ),
            retry_count=int(data.get("retry_count", 0)),
            max_retries=int(data.get("max_retries", 2)),
            escalation_count=int(data.get("escalation_count", 0)),
            max_escalations=int(data.get("max_escalations", 1)),
            requested_difficulty=str(data.get("requested_difficulty", "")),
            inferred_difficulty=str(data.get("inferred_difficulty", "")),
            difficulty_reason=str(data.get("difficulty_reason", "")),
            objective=str(data.get("objective", "")),
            allowed_paths=list(data.get("allowed_paths", [])),
            forbidden_scope=list(data.get("forbidden_scope", [])),
            acceptance_criteria=list(data.get("acceptance_criteria", [])),
            stop_conditions=list(data.get("stop_conditions", [])),
            program_id=data.get("program_id"),
            package_id=data.get("package_id"),
            baseline_commit=str(data.get("baseline_commit", "")),
            provider_calls=int(data.get("provider_calls", 0)),
            review_deferred=bool(data.get("review_deferred", False)),
            ownership_note=str(data.get("ownership_note", "")),
            changed_files=list(data.get("changed_files", [])),
            commands_executed=list(data.get("commands_executed", [])),
            tests=[
                TestResult(**item)
                for item in data.get("tests", [])
            ],
            review_findings=[
                ReviewFinding(
                    severity=ReviewSeverity(item["severity"]),
                    summary=item["summary"],
                    file=item.get("file"),
                    line=item.get("line"),
                    resolved=bool(item.get("resolved", False)),
                )
                for item in data.get("review_findings", [])
            ],
            reviewer_evidence=list(data.get("reviewer_evidence", [])),
            approvals=[
                ApprovalRequirement(**item)
                for item in data.get("approvals", [])
            ],
            notes=list(data.get("notes", [])),
        )

        return task

    @staticmethod
    def _model_choice(data: dict[str, Any] | None) -> ModelChoice | None:
        if not data:
            return None

        return ModelChoice(
            provider=Provider(data["provider"]),
            model=data["model"],
            effort=data.get("effort"),
            reason=data.get("reason", ""),
        )


def _self_test() -> None:
    root = Path(__file__).resolve().parent / ".state_test"
    store = StateStore(root)

    task = DevTask(description="Persist VECTOR orchestrator state")
    task.owner = Provider.CODEX
    task.reviewer = Provider.CLAUDE
    task.implementer_model = ModelChoice(
        provider=Provider.CODEX,
        model="gpt-5.6-sol",
        effort="medium",
        reason="Self-test",
    )
    task.tests.append(
        TestResult(
            command="python example.py",
            exit_code=0,
            passed=True,
            stdout="ok",
        )
    )
    task.review_findings.append(
        ReviewFinding(
            severity=ReviewSeverity.INFO,
            summary="Persistence self-test finding",
        )
    )
    task.reviewer_evidence.append(
        "Bounded normalized reviewer evidence for audit."
    )
    task.difficulty = Difficulty.SERIOUS
    task.task_category = TaskCategory.DEBUGGING
    task.quota_band_at_routing = QuotaBand.CONSERVE
    task.escalation_count = 1
    task.max_escalations = 2
    task.requested_difficulty = "scout"
    task.inferred_difficulty = "hard"
    task.difficulty_reason = "security floor"
    task.allowed_paths = ["core/x.py"]
    task.program_id = "prog1"
    task.package_id = "pkg1"
    task.baseline_commit = "abc123"
    task.provider_calls = 3
    task.review_deferred = True
    task.ownership_note = "claude-first"
    task.status = TaskStatus.WAITING_REVIEW

    path = store.save(task)
    assert path.exists()

    restored = store.load(task.task_id)

    assert restored.task_id == task.task_id
    assert restored.owner is Provider.CODEX
    assert restored.reviewer is Provider.CLAUDE
    assert restored.implementer_model is not None
    assert restored.implementer_model.model == "gpt-5.6-sol"
    assert restored.tests[0].passed
    assert restored.review_findings[0].severity is ReviewSeverity.INFO
    assert restored.reviewer_evidence == [
        "Bounded normalized reviewer evidence for audit."
    ]
    assert restored.difficulty is Difficulty.SERIOUS
    assert restored.task_category is TaskCategory.DEBUGGING
    assert restored.quota_band_at_routing is QuotaBand.CONSERVE
    assert restored.escalation_count == 1
    assert restored.max_escalations == 2
    assert restored.requested_difficulty == "scout"
    assert restored.inferred_difficulty == "hard"
    assert restored.difficulty_reason == "security floor"
    assert restored.allowed_paths == ["core/x.py"]
    assert restored.program_id == "prog1" and restored.package_id == "pkg1"
    assert restored.baseline_commit == "abc123"
    assert restored.provider_calls == 3
    assert restored.review_deferred is True and restored.ownership_note == "claude-first"
    assert restored.status is TaskStatus.WAITING_REVIEW and not restored.is_terminal()

    path.unlink(missing_ok=True)

    # Backward compatibility: a task JSON persisted BEFORE task-aware
    # routing existed (missing difficulty/task_category/
    # quota_band_at_routing/escalation_count/max_escalations) must
    # still load, defaulting those fields safely rather than crashing.
    legacy_payload = {
        "description": "Legacy pre-routing-upgrade task.",
        "task_id": "legacy0000000000000000000000000",
        "status": "pass",
        "stage": "complete",
        "risk": "low",
        "owner": "codex",
        "reviewer": "claude",
        "retry_count": 0,
        "max_retries": 2,
        "changed_files": [],
        "commands_executed": [],
        "tests": [],
        "review_findings": [],
        "approvals": [],
        "notes": [],
    }

    legacy_path = store._task_path(legacy_payload["task_id"])
    legacy_path.write_text(
        json.dumps(legacy_payload),
        encoding="utf-8",
    )

    legacy_task = store.load(legacy_payload["task_id"])

    assert legacy_task.difficulty is Difficulty.ROUTINE
    assert legacy_task.task_category is TaskCategory.IMPLEMENTATION
    assert legacy_task.quota_band_at_routing is QuotaBand.UNKNOWN
    assert legacy_task.escalation_count == 0
    assert legacy_task.max_escalations == 1

    legacy_path.unlink(missing_ok=True)

    try:
        root.rmdir()
    except OSError:
        pass


if __name__ == "__main__":
    _self_test()
