"""Benchmark task base class and result dataclass.

Every cognitive benchmark task implements BenchmarkTask.run() and returns
a TaskResult with full metrics — not just pass/fail.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger


@dataclass
class TaskResult:
    """Result of a single cognitive benchmark task.

    Records not just pass/fail but full operational metrics:
    latency, LLM calls, tokens consumed, human interventions, recovery attempts.
    """
    task_id: str                              # "T01", "T02", etc.
    category: str                             # "long_term_memory", "context_retention", etc.
    initial_state: str = ""                   # Description of starting conditions
    required_capability: str = ""             # What cognitive ability is being tested
    expected_behavior: str = ""               # What should happen
    actual_behavior: str = ""                 # What actually happened
    success: bool = False                     # Pass/fail
    human_intervention_count: int = 0         # How many times human had to step in
    incorrect_actions: int = 0                # Wrong actions taken
    recovery_attempts: int = 0                # How many times system tried to recover
    latency_ms: float = 0.0                   # Wall-clock time for the task
    llm_calls: int = 0                        # Number of LLM API calls made
    tokens_consumed: int = 0                  # Total tokens (input + output)
    final_outcome: str = ""                   # Summary of end state
    details: dict[str, Any] = field(default_factory=dict)  # Category-specific data

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BenchmarkTask(ABC):
    """Base class for all cognitive benchmark tasks.

    Subclasses implement run() which receives an IsolatedState context
    and returns a TaskResult.
    """

    task_id: str = ""
    category: str = ""
    required_capability: str = ""
    expected_behavior: str = ""

    @abstractmethod
    def run(self, state: Any) -> TaskResult:
        """Execute the benchmark task.

        Args:
            state: IsolatedState with isolated DB, plan store, etc.

        Returns:
            TaskResult with full metrics
        """
        ...

    def _make_result(self, **overrides) -> TaskResult:
        """Create a TaskResult pre-filled with task metadata."""
        return TaskResult(
            task_id=self.task_id,
            category=self.category,
            required_capability=self.required_capability,
            expected_behavior=self.expected_behavior,
            **overrides,
        )

    def _success(self, actual: str, outcome: str, **kw) -> TaskResult:
        return self._make_result(
            actual_behavior=actual,
            final_outcome=outcome,
            success=True,
            **kw,
        )

    def _failure(self, actual: str, outcome: str, **kw) -> TaskResult:
        return self._make_result(
            actual_behavior=actual,
            final_outcome=outcome,
            success=False,
            **kw,
        )
