"""VectorAutonomous — VectorCode VC-4 Mode B. TaskQueue-based autonomous agent."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent))  # vectorcode package

from loguru import logger
from session import VectorCodeSession
from hooks.workers import TaskQueue, Priority


class VectorAutonomous:
    """Mode B: submits GSD tasks as HIGH-priority TaskQueue items and returns immediately."""

    def __init__(self) -> None:
        self.session = VectorCodeSession.get()
        self._tq = TaskQueue.get()
        logger.info("[VECTOR][auto] VectorAutonomous initialised")

    def submit(self, task: str) -> str:
        """Enqueue task as HIGH priority. Returns task_id immediately."""
        from gsd_loop import GSDLoop

        def _run_gsd():
            loop = GSDLoop(mode="auto")
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





