"""GSDLoop — VectorCode VC-3. discuss→plan→execute→verify workflow."""
import tempfile
from enum import Enum

from loguru import logger
from memory.pattern_store import PatternStore


class GSDPhase(Enum):
    DISCUSS = "discuss"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"


_PHASE_ORDER = [GSDPhase.DISCUSS, GSDPhase.PLAN, GSDPhase.EXECUTE, GSDPhase.VERIFY]


class GSDLoop:
    """
    Discuss→Plan→Execute→Verify loop for VectorCode task execution.

    Pattern cache consulted before DISCUSS phase — high-reward hits skip directly to PLAN.
    Max 3 verify retries before escalating to queen decomposition.
    """
    MAX_VERIFY_RETRIES = 3

    def __init__(self, mode: str = "auto", executor=None) -> None:
        # executor: callable(prompt: str) -> str that runs one prompt through a real agent.
        self.mode = mode
        self.executor = executor
        self.current_phase = GSDPhase.DISCUSS
        self.verify_retries = 0
        _tmp = tempfile.mkdtemp(prefix="gsd_patterns_")
        self._patterns = PatternStore(index_path=_tmp)

    def should_skip_discuss(self, task: str) -> bool:
        """Return True if a high-reward pattern exists for this task."""
        hit = self._patterns.recall(task)
        return hit is not None

    def advance(self) -> None:
        """Move to the next phase in sequence."""
        idx = _PHASE_ORDER.index(self.current_phase)
        if idx < len(_PHASE_ORDER) - 1:
            self.current_phase = _PHASE_ORDER[idx + 1]
            logger.debug(f"[VECTOR][gsd] → {self.current_phase.value}")

    def reset(self) -> None:
        """Return to DISCUSS phase and clear retry counter."""
        self.current_phase = GSDPhase.DISCUSS
        self.verify_retries = 0
        logger.debug("[VECTOR][gsd] reset to DISCUSS")

    def run(self, task: str) -> dict:
        """
        Execute one full GSD cycle for a task.
        Returns a result dict with phase trace and outcome.
        """
        self.reset()
        if self.executor is None:
            # This used to return a trace of phase NAMES with no work done, which looked like success.
            return {"task": task, "trace": [], "mode": self.mode, "status": "not_executed",
                    "reason": "no executor configured -- nothing was run", "output": ""}

        trace: list[str] = []
        outputs: dict[str, str] = {}
        try:
            trace.append(GSDPhase.PLAN.value)
            outputs["plan"] = self.executor(
                "PLAN ONLY. Do not change anything yet. Inspect what you need with your tools, then give a short "
                f"numbered plan for this task:\n{task}")

            passed, verdict = False, ""
            for attempt in range(self.MAX_VERIFY_RETRIES):
                trace.append(GSDPhase.EXECUTE.value)
                outputs["execute"] = self.executor(
                    f"Carry out this task using your tools.\nTask: {task}\nPlan:\n{outputs['plan']}"
                    + (f"\nThe previous attempt failed verification: {verdict}" if verdict else ""))
                trace.append(GSDPhase.VERIFY.value)
                self.verify_retries = attempt + 1
                verdict = self.executor(
                    "VERIFY. Check the work is really done by looking at files / running commands with your tools "
                    "(do not trust the previous answer). Reply with the single word PASS or FAIL on the first line, "
                    f"then a one-line reason.\nTask: {task}\nClaimed result:\n{outputs['execute']}")
                outputs["verify"] = verdict
                if verdict.strip().upper().startswith("PASS"):
                    passed = True
                    break
        except Exception as exc:
            return {"task": task, "trace": trace, "mode": self.mode, "status": "error",
                    "reason": str(exc), "output": outputs.get("execute", "")}

        return {"task": task, "trace": trace, "mode": self.mode,
                "status": "passed" if passed else "failed", "output": outputs.get("execute", ""),
                "verification": outputs.get("verify", ""), "phases": outputs}


if __name__ == "__main__":
    loop = GSDLoop(mode="auto")
    assert loop.MAX_VERIFY_RETRIES == 3
    assert loop.current_phase == GSDPhase.DISCUSS
    loop.advance()
    assert loop.current_phase == GSDPhase.PLAN
    loop.reset()
    assert loop.current_phase == GSDPhase.DISCUSS
    print("gsd_loop.py OK")


