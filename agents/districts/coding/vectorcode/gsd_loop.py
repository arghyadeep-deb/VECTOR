"""GSDLoop — VectorCode VC-3. discuss→plan→execute→verify workflow."""
import sys
import tempfile
from enum import Enum
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from loguru import logger
from agents.districts.coding.vectorcode.memory.pattern_store import PatternStore


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

    def __init__(self, mode: str = "auto") -> None:
        self.mode = mode
        self.current_phase = GSDPhase.DISCUSS
        self.verify_retries = 0
        from agents.districts.coding.vectorcode.memory.pattern_store import PatternStore
        self._patterns = PatternStore()

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
        trace = []

        if self.should_skip_discuss(task):
            logger.info(f"[VECTOR][gsd] pattern hit — skipping DISCUSS for: {task[:60]}")
            self.advance()  # skip to PLAN

        while self.current_phase != GSDPhase.VERIFY or self.verify_retries < self.MAX_VERIFY_RETRIES:
            trace.append(self.current_phase.value)
            if self.current_phase == GSDPhase.VERIFY:
                self.verify_retries += 1
                break
            self.advance()

        return {"task": task, "trace": trace, "mode": self.mode}


if __name__ == "__main__":
    loop = GSDLoop(mode="auto")
    assert loop.MAX_VERIFY_RETRIES == 3
    assert loop.current_phase == GSDPhase.DISCUSS
    loop.advance()
    assert loop.current_phase == GSDPhase.PLAN
    loop.reset()
    assert loop.current_phase == GSDPhase.DISCUSS
    print("gsd_loop.py OK")
