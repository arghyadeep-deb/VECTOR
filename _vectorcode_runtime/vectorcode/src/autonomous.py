"""VectorAutonomous — VectorCode VC-4 Mode B. TaskQueue-based autonomous agent."""

from loguru import logger
from vectorcode.src.session import VectorCodeSession
from hooks.workers import TaskQueue, Priority


class VectorAutonomous:
    """Mode B: submits GSD tasks as HIGH-priority TaskQueue items and returns immediately."""

    def __init__(self, project_dir=None) -> None:
        from pathlib import Path
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.session = VectorCodeSession.get()
        self._tq = TaskQueue.get()
        logger.info("[VECTOR][auto] VectorAutonomous initialised")

    def submit(self, task: str) -> str:
        """Enqueue task as HIGH priority. Returns task_id immediately."""
        from gsd_loop import GSDLoop

        project_dir = self.project_dir

        def _run_gsd():
            from agent_task import run_agent_task
            loop = GSDLoop(mode="auto", executor=lambda prompt: run_agent_task(prompt, project_dir))
            return loop.run(task)

        task_id = self._tq.submit(_run_gsd, priority=Priority.HIGH, name=task[:40])
        self.session.task_id = task_id
        logger.info(f"[VECTOR][auto] submitted task_id={task_id}: {task[:60]}")
        return task_id


if __name__ == "__main__":
    va = VectorAutonomous()
    assert va.session.mode in ("auto", "repl", "hybrid")
    tid = va.submit("write a hello world function")
    assert tid is not None
    print(f"autonomous.py OK — task_id={tid}")


