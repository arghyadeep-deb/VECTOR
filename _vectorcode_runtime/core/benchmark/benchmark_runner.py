"""Benchmark runner — orchestrates all 14 cognitive benchmark tasks.

Loads task modules, runs them in isolated state, collects results,
generates report.
"""
from __future__ import annotations

import importlib
import time
from typing import Any

from loguru import logger

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult
from core.benchmark.isolation import IsolatedState
from core.benchmark.report import BenchmarkReport


# All 14 benchmark task modules
_TASK_MODULES = [
    "core.benchmark.tasks.t01_long_term_memory",
    "core.benchmark.tasks.t02_context_retention",
    "core.benchmark.tasks.t03_goal_persistence",
    "core.benchmark.tasks.t04_multi_step_planning",
    "core.benchmark.tasks.t05_replanning",
    "core.benchmark.tasks.t06_proactive_cognition",
    "core.benchmark.tasks.t07_epistemic_uncertainty",
    "core.benchmark.tasks.t08_owner_correction_learning",
    "core.benchmark.tasks.t09_tool_execution",
    "core.benchmark.tasks.t10_tool_failure_recovery",
    "core.benchmark.tasks.t11_permission_safety",
    "core.benchmark.tasks.t12_provider_fallback",
    "core.benchmark.tasks.t13_autonomous_task_completion",
    "core.benchmark.tasks.t14_cross_session_continuity",
]


class BenchmarkRunner:
    """Orchestrates cognitive benchmark execution."""

    def __init__(self, categories: list[str] | None = None):
        """Initialize runner with optional category filter.

        Args:
            categories: If provided, only run tasks whose category matches.
                       Category names use underscores: "long_term_memory", "planning", etc.
        """
        self._category_filter = categories
        self.tasks = self._load_tasks()
        self.results: list[TaskResult] = []

    def _load_tasks(self) -> list[BenchmarkTask]:
        """Import and instantiate all task classes."""
        tasks = []
        for module_path in _TASK_MODULES:
            try:
                mod = importlib.import_module(module_path)
                # Find the BenchmarkTask subclass in the module
                task_cls = getattr(mod, "TASK_CLASS", None)
                if task_cls is None:
                    # Try to find any BenchmarkTask subclass
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if (isinstance(attr, type)
                                and issubclass(attr, BenchmarkTask)
                                and attr is not BenchmarkTask):
                            task_cls = attr
                            break

                if task_cls is not None:
                    task = task_cls()
                    # Apply category filter
                    if self._category_filter:
                        cat = task.category.lower().replace(" ", "_")
                        if cat not in [c.lower().replace(" ", "_") for c in self._category_filter]:
                            continue
                    tasks.append(task)
                else:
                    logger.warning("[VECTOR][bench] no TASK_CLASS in {}", module_path)
            except Exception as e:
                logger.warning("[VECTOR][bench] failed to load {}: {}", module_path, e)

        return tasks

    def run(self) -> BenchmarkReport:
        """Run all loaded tasks in isolated state and return report."""
        # Results describe one run, not the lifetime of a reusable runner.
        self.results = []
        logger.info(
            "[VECTOR][bench] starting benchmark with {} tasks",
            len(self.tasks),
        )

        with IsolatedState() as state:
            for task in self.tasks:
                t0 = time.monotonic()
                try:
                    result = task.run(state)
                    result.latency_ms = (time.monotonic() - t0) * 1000
                except Exception as e:
                    # Task crashed — record as failure with error details
                    result = TaskResult(
                        task_id=getattr(task, "task_id", "UNKNOWN"),
                        category=getattr(task, "category", "unknown"),
                        required_capability=getattr(task, "required_capability", ""),
                        expected_behavior=getattr(task, "expected_behavior", ""),
                        actual_behavior=f"TASK CRASHED: {e}",
                        success=False,
                        latency_ms=(time.monotonic() - t0) * 1000,
                        final_outcome=f"Exception: {type(e).__name__}: {e}",
                    )
                    logger.error(
                        "[VECTOR][bench] task {} crashed: {}",
                        result.task_id, e,
                    )

                self.results.append(result)
                status = "✅" if result.success else "❌"
                logger.info(
                    "[VECTOR][bench] {} {} — {} ({:.0f}ms)",
                    status, result.task_id, result.category.replace("_", " "),
                    result.latency_ms,
                )

        report = BenchmarkReport(self.results)
        logger.info(
            "[VECTOR][bench] complete — {}/{} passed ({:.0%})",
            report.summary["passed"],
            report.summary["total_tasks"],
            report.summary["pass_rate"],
        )
        return report

    @staticmethod
    def list_categories() -> list[str]:
        """Return all available task categories."""
        categories = []
        for module_path in _TASK_MODULES:
            try:
                mod = importlib.import_module(module_path)
                task_cls = getattr(mod, "TASK_CLASS", None)
                if task_cls:
                    categories.append(task_cls.category)
            except Exception:
                pass
        return categories
