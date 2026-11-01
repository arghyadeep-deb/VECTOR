"""Persistent restart-safe task queue for the VECTOR dev orchestrator."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from models import DevTask, TaskStatus
from orchestrator import DevOrchestrator


class TaskQueue:
    """Persistent FIFO queue backed by controller task state."""

    def __init__(
        self,
        orchestrator: DevOrchestrator,
    ) -> None:
        self.orchestrator = orchestrator
        self.root = orchestrator.state_root
        self.path = self.root / "queue.json"

    def _read_ids(self) -> list[str]:
        if not self.path.exists():
            return []

        try:
            payload = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise RuntimeError(
                "Persistent task queue is corrupted"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(
                "Persistent task queue payload is invalid"
            )

        task_ids = payload.get(
            "task_ids",
            [],
        )

        if not isinstance(task_ids, list):
            raise RuntimeError(
                "Persistent task queue task_ids is invalid"
            )

        normalized: list[str] = []

        for value in task_ids:
            if not isinstance(value, str):
                raise RuntimeError(
                    "Persistent task queue contains invalid task id"
                )

            task_id = value.strip()

            if not task_id:
                raise RuntimeError(
                    "Persistent task queue contains empty task id"
                )

            if task_id not in normalized:
                normalized.append(task_id)

        return normalized

    def _write_ids(
        self,
        task_ids: list[str],
    ) -> None:
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "task_ids": task_ids,
        }

        fd, temp_name = tempfile.mkstemp(
            prefix="queue.",
            suffix=".tmp",
            dir=self.root,
            text=True,
        )

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    payload,
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            Path(temp_name).replace(
                self.path
            )

        except Exception:
            Path(temp_name).unlink(
                missing_ok=True
            )
            raise

    def enqueue(
        self,
        task: DevTask,
    ) -> None:
        if task.is_terminal():
            raise RuntimeError(
                "Terminal task cannot be enqueued"
            )

        if task.status is TaskStatus.NEEDS_HUMAN:
            raise RuntimeError(
                "Task requiring human approval cannot be enqueued"
            )

        task_ids = self._read_ids()

        if task.task_id not in task_ids:
            task_ids.append(
                task.task_id
            )
            self._write_ids(
                task_ids
            )

    def remove(
        self,
        task_id: str,
    ) -> None:
        task_ids = self._read_ids()

        filtered = [
            value
            for value in task_ids
            if value != task_id
        ]

        if filtered != task_ids:
            self._write_ids(
                filtered
            )

    def pending(self) -> list[DevTask]:
        """Return active queued tasks in FIFO order."""

        task_ids = self._read_ids()
        retained: list[str] = []
        tasks: list[DevTask] = []

        for task_id in task_ids:
            try:
                task = self.orchestrator.load_task(
                    task_id
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "Queue references missing task state: "
                    f"{task_id}"
                ) from exc

            if task.is_terminal():
                continue

            if task.status is TaskStatus.NEEDS_HUMAN:
                continue

            retained.append(
                task_id
            )
            tasks.append(
                task
            )

        if retained != task_ids:
            self._write_ids(
                retained
            )

        return tasks

    def peek(self) -> DevTask | None:
        tasks = self.pending()

        if not tasks:
            return None

        return tasks[0]

    def recover_after_restart(
        self,
    ) -> list[DevTask]:
        """Recover queue state without replaying uncertain execution.

        Tasks that were RUNNING when the controller stopped are moved
        to NEEDS_HUMAN rather than automatically rerunning model work.
        """

        task_ids = self._read_ids()
        retained: list[str] = []
        recovered: list[DevTask] = []

        for task_id in task_ids:
            try:
                task = self.orchestrator.load_task(
                    task_id
                )
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "Queue references missing task state: "
                    f"{task_id}"
                ) from exc

            if task.is_terminal():
                continue

            if task.status is TaskStatus.RUNNING:
                self.orchestrator.mark_needs_human(
                    task,
                    (
                        "Controller restarted while task was RUNNING; "
                        "automatic replay refused because execution "
                        "completion is uncertain."
                    ),
                )
                continue

            if task.status is TaskStatus.NEEDS_HUMAN:
                continue

            retained.append(
                task_id
            )
            recovered.append(
                task
            )

        self._write_ids(
            retained
        )

        return recovered


def _self_test() -> None:
    import shutil
    import tempfile

    from models import Provider, TaskStage
    from router import Difficulty

    repo_root = Path(__file__).resolve().parents[2]

    temp_root = Path(
        tempfile.mkdtemp(
            prefix="vector_queue_test_"
        )
    )

    try:
        orchestrator = DevOrchestrator(
            repo_root=repo_root,
            state_root=temp_root,
        )

        queue = TaskQueue(
            orchestrator
        )

        first = orchestrator.prepare_task(
            description=(
                "Make harmless deterministic parser cleanup."
            ),
            difficulty=Difficulty.ROUTINE,
        )

        second = orchestrator.prepare_task(
            description=(
                "Add harmless deterministic parser regression test."
            ),
            difficulty=Difficulty.ROUTINE,
        )

        assert first.owner is Provider.CODEX
        assert second.owner is Provider.CLAUDE

        queue.enqueue(
            first
        )
        queue.enqueue(
            second
        )

        # Duplicate enqueue must not duplicate queue position.
        queue.enqueue(
            first
        )

        pending = queue.pending()

        assert [
            task.task_id
            for task in pending
        ] == [
            first.task_id,
            second.task_id,
        ]

        assert queue.peek() is not None
        assert (
            queue.peek().task_id
            == first.task_id
        )

        # Simulate controller interruption during first task.
        orchestrator.mark_running(
            first,
            TaskStage.IMPLEMENTING,
        )

        restarted = DevOrchestrator(
            repo_root=repo_root,
            state_root=temp_root,
        )

        restarted_queue = TaskQueue(
            restarted
        )

        recovered = (
            restarted_queue.recover_after_restart()
        )

        # Interrupted RUNNING task must not be replayed.
        recovered_first = restarted.load_task(
            first.task_id
        )

        assert (
            recovered_first.status
            is TaskStatus.NEEDS_HUMAN
        )

        assert any(
            "automatic replay refused" in note
            for note in recovered_first.notes
        )

        # Second untouched task remains ready.
        assert len(recovered) == 1
        assert (
            recovered[0].task_id
            == second.task_id
        )

        assert (
            restarted_queue.peek().task_id
            == second.task_id
        )

        # Terminal tasks are removed automatically.
        restarted.mark_pass(
            recovered[0],
            "Queue recovery self-test complete.",
        )

        assert restarted_queue.pending() == []

        # Queue itself must survive another controller restart.
        restarted_again = DevOrchestrator(
            repo_root=repo_root,
            state_root=temp_root,
        )

        empty_queue = TaskQueue(
            restarted_again
        )

        assert (
            empty_queue.recover_after_restart()
            == []
        )

    finally:
        shutil.rmtree(
            temp_root,
            ignore_errors=True,
        )


if __name__ == "__main__":
    _self_test()
