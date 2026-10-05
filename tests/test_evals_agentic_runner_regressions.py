"""Regression tests for agentic evaluation orchestration."""

import asyncio

from loguru import logger as loguru_logger

from vectorcode.src.evals.core.agentic_runner import AgenticRunner, LOGGER
from vectorcode.src.evals.core.types import EvalRecord


class _Dataset:
    def iter_records(self):
        return iter(
            [
                EvalRecord(
                    record_id="one",
                    problem="question",
                    reference="",
                    category="agentic",
                )
            ]
        )


class _Agent:
    def __call__(self, prompt: str) -> str:
        return f"answer to {prompt}"


def test_repeated_runs_do_not_accumulate_stale_traces() -> None:
    runner = AgenticRunner(_Agent(), _Dataset())

    first = asyncio.run(runner.run())
    second = asyncio.run(runner.run())

    assert len(first) == 1
    assert len(second) == 1
    assert runner.traces == second


def test_agentic_runner_uses_loguru() -> None:
    assert LOGGER is loguru_logger


if __name__ == "__main__":
    test_repeated_runs_do_not_accumulate_stale_traces()
    test_agentic_runner_uses_loguru()
