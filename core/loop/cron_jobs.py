"""VECTOR Cron Jobs — daily & weekly tasks registered with the durable scheduler.

The scheduler_loop() in core/loop/autonomous_loop.py picks these up.
Each job is independent and gracefully no-ops if its absorbed module is missing.

Registered jobs:
  • daily 03:00 — eval harness benchmark across all WARM_POOL models
  • daily 06:00 — biometrics aggregator pull
  • daily 22:30 — daily reviewer + journal writer
  • weekly Sun 02:00 — DSPy skill optimization from session traces
  • weekly Sun 23:00 — growth analyst weekly report

Usage from autonomous_loop:
    from core.loop.cron_jobs import register_default_jobs
    register_default_jobs(scheduler_instance)
"""
from __future__ import annotations

import asyncio
import datetime
from typing import Any, Callable

from loguru import logger


# ── Job implementations ──────────────────────────────────────────────────────


async def job_subconscious_loop(*, _ctx: dict | None = None) -> dict:
    """Every 30 min — SubconsciousLoop situation assessment and escalation check."""
    try:
        from districts.chief_of_staff.subconscious_loop import SubconsciousLoop
        result = await SubconsciousLoop().run_once()
        logger.info(
            f"[VECTOR][cron] subconscious_loop: decision={result.get('decision', '?')}"
        )
        return {"status": "ok", **result}
    except Exception as e:
        logger.warning(f"[VECTOR][cron] subconscious_loop failed: {e}")
        return {"status": "failed", "reason": str(e)}


async def job_audit_verify(*, _ctx: dict | None = None) -> dict:
    """Daily 3:05 AM audit chain verification (Phase 1E)."""
    try:
        from core.audit.merkle_chain import get_audit_chain
        chain = get_audit_chain()
        result = chain.verify()
        if not result.valid:
            logger.warning(
                f"[VECTOR][cron] AUDIT CHAIN BROKEN at seq={result.broken_at}: {result.reason}"
            )
            try:
                from core.event_bus.bus import get_event_bus
                from core.event_bus.types import Event, EventType
                bus = await get_event_bus()
                await bus.publish(Event(
                    event_type=EventType.SECURITY_ALERT,
                    data={"reason": "audit_chain_broken", "broken_at": result.broken_at,
                          "detail": result.reason},
                    source="cron.audit_verify",
                ))
            except Exception as _ev_err:
                logger.debug(f"[VECTOR][cron] audit alert publish failed: {_ev_err}")
            return {"status": "broken", "broken_at": result.broken_at, "reason": result.reason}
        logger.info(f"[VECTOR][cron] audit chain OK — {result.total_entries} entries")
        return {"status": "ok", "chain_length": result.total_entries}
    except Exception as e:
        logger.warning(f"[VECTOR][cron] audit verify failed: {e}")
        return {"status": "error", "reason": str(e)}


async def job_daily_eval(*, _ctx: dict | None = None) -> dict:
    """Daily benchmark: run the eval harness against the WARM_POOL models."""
    try:
        from vectorcode.src.evals import core as evals_core  # type: ignore
    except Exception as e:
        logger.debug(f"[VECTOR][cron] eval harness unavailable: {e}")
        return {"status": "skipped", "reason": str(e)}

    try:
        # Try common entry points
        for fn_name in ("run_default_suite", "run_suite", "run_all", "main"):
            fn = getattr(evals_core, fn_name, None)
            if callable(fn):
                result = fn()
                if asyncio.iscoroutine(result):
                    result = await result
                return {"status": "ok", "result": str(result)[:500]}
        return {"status": "skipped", "reason": "no entry point found"}
    except Exception as e:
        logger.warning(f"[VECTOR][cron] daily eval failed: {e}")
        return {"status": "failed", "reason": str(e)}


async def job_biometrics_pull(*, _ctx: dict | None = None) -> dict:
    """Daily biometrics pull from Apple Health / Oura / Strava."""
    try:
        from districts.health.biometrics_aggregator import BiometricsAggregator
        agent = BiometricsAggregator()
        return await agent.run({})
    except Exception as e:
        logger.warning(f"[VECTOR][cron] biometrics pull failed: {e}")
        return {"status": "failed", "reason": str(e)}


async def job_daily_review(*, _ctx: dict | None = None) -> dict:
    """End-of-day daily reviewer + journal writer."""
    out: dict = {"daily_reviewer": "skipped", "journal_writer": "skipped"}
    try:
        from districts.reflection.daily_reviewer import DailyReviewer
        agent = DailyReviewer()
        r = await agent.run({})
        out["daily_reviewer"] = r.get("status", "ok") if isinstance(r, dict) else "ok"
    except Exception as e:
        logger.warning(f"[VECTOR][cron] daily_reviewer failed: {e}")
        out["daily_reviewer"] = f"error: {e}"
    try:
        from districts.reflection.journal_writer import JournalWriter
        agent = JournalWriter()
        r = await agent.run({})
        out["journal_writer"] = r.get("status", "ok") if isinstance(r, dict) else "ok"
    except Exception as e:
        logger.warning(f"[VECTOR][cron] journal_writer failed: {e}")
        out["journal_writer"] = f"error: {e}"
    return out


async def job_weekly_dspy_optimize(*, _ctx: dict | None = None) -> dict:
    """Weekly DSPy skill optimization using session traces.

    Uses vectorcode.src.learning.optimize for the actual algorithm. Gracefully
    no-ops when DSPy isn't installed.
    """
    try:
        from vectorcode.src.learning import learning_orchestrator  # type: ignore
    except Exception as e:
        logger.debug(f"[VECTOR][cron] learning module unavailable: {e}")
        return {"status": "skipped", "reason": str(e)}

    try:
        # Try common entry points exposed by the orchestrator module
        for fn_name in ("run_weekly_optimization", "optimize_skills_weekly",
                        "run_optimize", "optimize_skills"):
            fn = getattr(learning_orchestrator, fn_name, None)
            if callable(fn):
                result = fn()
                if asyncio.iscoroutine(result):
                    result = await result
                return {"status": "ok", "result": str(result)[:500]}
        # Try class-based entry
        for cls_name in ("LearningOrchestrator", "Orchestrator"):
            cls = getattr(learning_orchestrator, cls_name, None)
            if callable(cls):
                instance = cls()
                fn = getattr(instance, "run_weekly", None) or getattr(instance, "optimize", None)
                if callable(fn):
                    result = fn()
                    if asyncio.iscoroutine(result):
                        result = await result
                    return {"status": "ok", "result": str(result)[:500]}
        return {"status": "skipped", "reason": "no entry point found"}
    except Exception as e:
        logger.warning(f"[VECTOR][cron] DSPy optimization failed: {e}")
        return {"status": "failed", "reason": str(e)}


_MORNING_DIGEST_WORKFLOW: dict = {
    "name": "morning_digest",
    "description": "Synthesize daily briefing from configured data sources",
    "tasks": [
        {
            "id": "digest",
            "fn": None,
            "params": {},
            "timeout_seconds": 120.0,
        },
    ],
}


async def _run_morning_digest_fn(**kwargs: Any) -> dict:
    """Morning digest — unavailable (vc_districts module does not exist)."""
    return {"status": "skipped", "reason": "vc_districts module not available"}


async def job_trigger_workflow(*, _ctx: dict | None = None) -> dict:
    """Daily 08:00 — fire the morning_digest workflow via WorkflowRunner.

    Directly instantiates a WorkflowRunner and runs the inline workflow
    definition so this job is self-contained (no external workflow file needed).
    """
    try:
        from core.loop.workflow_runner import WorkflowRunner
        runner = WorkflowRunner()
        wf = dict(_MORNING_DIGEST_WORKFLOW)
        wf["tasks"] = [
            dict(t, fn=_run_morning_digest_fn) if t["fn"] is None else t
            for t in wf["tasks"]
        ]
        result = await runner.run(wf)
        return {
            "status": result.overall_status,
            "name": result.name,
            "duration_seconds": result.duration_seconds,
            "tasks": {tid: {"status": r.status} for tid, r in result.task_results.items()},
        }
    except Exception as e:
        logger.warning(f"[VECTOR][cron] workflow trigger failed: {e}")
        return {"status": "failed", "reason": str(e)}


async def job_weekly_growth_report(*, _ctx: dict | None = None) -> dict:
    """Weekly growth analyst report (Sunday)."""
    try:
        from districts.reflection.growth_analyst import GrowthAnalyst
        agent = GrowthAnalyst()
        return await agent.run({})
    except Exception as e:
        logger.warning(f"[VECTOR][cron] growth_analyst failed: {e}")
        return {"status": "failed", "reason": str(e)}


# ── Registration ─────────────────────────────────────────────────────────────


def register_default_jobs(scheduler: Any) -> int:
    """Register all default jobs against the durable scheduler.

    Tries the most common scheduler API surfaces (schedule_daily, schedule_weekly,
    add_job with cron expression, etc.). Returns the count successfully registered.
    """
    if scheduler is None:
        logger.warning("[VECTOR][cron] scheduler is None — no jobs registered")
        return 0

    jobs: list[tuple[str, str, str, Callable]] = [
        # (job_id,                cadence,  cron,       fn)
        ("daily-eval-harness",    "daily",  "0 3 * * *", job_daily_eval),
        ("daily-audit-verify",    "daily",  "5 3 * * *", job_audit_verify),  # Phase 1E
        ("daily-biometrics-pull", "daily",  "0 6 * * *", job_biometrics_pull),
        ("daily-review-journal",  "daily",  "30 22 * * *", job_daily_review),
        ("daily-workflow-trigger","daily",  "0 8 * * *", job_trigger_workflow),
        ("weekly-benchmark-suite","weekly", "0 1 * * 0", job_benchmark_suite),
        ("weekly-recipe-sync",    "weekly", "30 1 * * 0", job_recipe_sync),
        ("weekly-dspy-optimize",  "weekly", "0 2 * * 0", job_weekly_dspy_optimize),
        ("weekly-growth-report",  "weekly", "0 23 * * 0", job_weekly_growth_report),
    ]

    registered = 0
    for job_id, cadence, cron_expr, fn in jobs:
        if _try_register(scheduler, job_id, cadence, cron_expr, fn):
            registered += 1
            logger.info(f"[VECTOR][cron] registered {job_id} ({cadence}, {cron_expr})")
        else:
            logger.warning(f"[VECTOR][cron] could not register {job_id} — scheduler API mismatch")

    return registered


def _try_register(
    scheduler: Any,
    job_id: str,
    cadence: str,
    cron_expr: str,
    fn: Callable,
) -> bool:
    """Try multiple scheduler APIs in priority order."""
    # 1) schedule_daily/schedule_weekly convenience methods
    if cadence == "daily":
        for name in ("schedule_daily", "add_daily", "daily"):
            api = getattr(scheduler, name, None)
            if callable(api):
                try:
                    parts = cron_expr.split()
                    minute, hour = int(parts[0]), int(parts[1])
                    api(job_id=job_id, hour=hour, minute=minute, fn=fn)
                    return True
                except Exception:
                    continue
    if cadence == "weekly":
        for name in ("schedule_weekly", "add_weekly", "weekly"):
            api = getattr(scheduler, name, None)
            if callable(api):
                try:
                    parts = cron_expr.split()
                    minute, hour, _, _, dow = parts[:5]
                    api(job_id=job_id, dow=int(dow), hour=int(hour), minute=int(minute), fn=fn)
                    return True
                except Exception:
                    continue

    # 2) Generic add_job(cron) interface
    for name in ("add_job", "schedule", "register", "add"):
        api = getattr(scheduler, name, None)
        if callable(api):
            try:
                api(job_id=job_id, cron=cron_expr, fn=fn)
                return True
            except TypeError:
                # try positional fallback
                try:
                    api(job_id, cron_expr, fn)
                    return True
                except Exception:
                    continue
            except Exception:
                continue
    return False


async def job_benchmark_suite(*, _ctx: dict | None = None) -> dict:
    """Weekly benchmark run — exercises the absorbed ``bench`` module.

    Delegates to ``BenchmarkSuite.run_all()`` which benchmarks all registered
    engines (latency, throughput, energy).  Gracefully no-ops if bench is
    unavailable or has no registered suites.
    """
    try:
        from vectorcode.src.bench import ensure_registered, BenchmarkSuite
        ensure_registered()
        suite = BenchmarkSuite()
        results = suite.run_all()
        return {
            "status": "ok",
            "benchmarks": len(results),
            "summary": str(results)[:500],
        }
    except Exception as e:
        logger.debug(f"[VECTOR][cron] benchmark suite unavailable: {e}")
        return {"status": "skipped", "reason": str(e)}


async def job_recipe_sync(*, _ctx: dict | None = None) -> dict:
    """Weekly — discover and log available recipes from the absorbed module."""
    try:
        from vectorcode.src.recipes import discover_recipes, Recipe
        recipes = discover_recipes()
        if recipes:
            logger.info(f"[VECTOR][cron] {len(recipes)} recipes available")
        else:
            logger.info("[VECTOR][cron] no recipes discovered (expected if none defined)")
        return {"status": "ok", "count": len(recipes) if recipes else 0}
    except Exception as e:
        logger.debug(f"[VECTOR][cron] recipe discovery unavailable: {e}")
        return {"status": "skipped", "reason": str(e)}


__all__ = [
    "register_default_jobs",
    "job_daily_eval",
    "job_biometrics_pull",
    "job_daily_review",
    "job_weekly_dspy_optimize",
    "job_weekly_growth_report",
    "job_trigger_workflow",
    "job_benchmark_suite",
    "job_recipe_sync",
    "_MORNING_DIGEST_WORKFLOW",
    "_run_morning_digest_fn",
]
