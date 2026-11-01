# Ported from GitHub/VectorCode_vectorcode/repo/run_agent.py (IterationBudget class)
"""Thread-safe iteration counter for an agent."""
import threading


class IterationBudget:
    """Thread-safe iteration counter.

    Parent agents default to max_total=90.
    Subagents get an independent budget (default 50).
    execute_code turns can be refunded via refund().
    """

    def __init__(self, max_total: int = 90):
        self.max_total = max_total
        self._used = 0
        self._lock = threading.Lock()

    def consume(self) -> bool:
        """Try to consume one iteration. Returns True if allowed."""
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        """Give back one iteration (e.g. for execute_code turns)."""
        with self._lock:
            if self._used > 0:
                self._used -= 1

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.max_total - self._used)

    def __repr__(self) -> str:
        return f"IterationBudget(used={self._used}/{self.max_total})"
