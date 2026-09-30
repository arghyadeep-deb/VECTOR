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

from core.training.post_training.sft_trainer import run_sft
from core.training.post_training.dpo_trainer import run_dpo


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


async def job_nightly_selfcheck(*, _ctx: dict | None = None) -> dict:
    """Nightly 04:00 — self-repair check: full syntax sweep + smoke test.

    1. compileall over core/ + districts/ (catches mass-edit breakage the
       moment it lands instead of weeks later).
    2. `python run_vector.py smoke` in a subprocess (spine still boots?).
    On failure: HIGH-priority nudge (spoken when owner present) naming the
    first broken file + the last commit hash, and an episodic record. No
    auto-revert — the owner decides; reverting autonomously risks losing work.
    """
    import subprocess
    import sys as _sys
    from pathlib import Path as _Path

    repo = _Path(__file__).resolve().parent.parent.parent
    problems: list[str] = []

    try:
        # These three subprocesses can take minutes; run inline they froze the whole event loop (the API, the HUD and the
        # autonomous loop share it) for the duration -- found by the 2026-09-27 static scan of async handlers.
        r = await asyncio.to_thread(
            subprocess.run,
            [_sys.executable, "-m", "compileall", "-q", "core", "districts", "scripts"],
            capture_output=True, text=True, timeout=600, cwd=repo,
        )
        if r.returncode != 0:
            first = next((ln for ln in (r.stderr + r.stdout).splitlines()
                          if "Error compiling" in ln or "Sorry" in ln), "syntax error")
            problems.append(f"compileall failed: {first[:160]}")
    except Exception as e:
        problems.append(f"compileall crashed: {e}")

    try:
        r = await asyncio.to_thread(
            subprocess.run,
            [_sys.executable, "run_vector.py", "smoke"],
            capture_output=True, text=True, timeout=300, cwd=repo,
        )
        if r.returncode != 0:
            problems.append(f"smoke test failed (rc={r.returncode}): "
                            f"{(r.stderr or r.stdout)[-160:]}")
    except Exception as e:
        problems.append(f"smoke test crashed: {e}")

    last_commit = ""
    try:
        last_commit = (await asyncio.to_thread(
            subprocess.run, ["git", "log", "-1", "--format=%h %s"], capture_output=True,
            text=True, timeout=10, cwd=repo)).stdout.strip()[:90]
    except Exception as e:
        logger.warning("[VECTOR][selfcheck] git log lookup failed: {}", e)

    if problems:
        try:
            from core.loop.nudge_engine import nudge_engine
            nudge_engine.push(
                f"Self-check FAILED: {problems[0]} — last commit: {last_commit}. "
                f"Consider `git revert` or fixing before the loop misbehaves.",
                source="nightly_selfcheck", need="repair", priority=0.95,
            )
        except Exception as _n_err:
            logger.warning(f"[VECTOR][selfcheck] nudge failed: {_n_err}")
        try:
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store(
                event_type="selfcheck_failure",
                content="; ".join(problems) + f" | last_commit={last_commit}",
                tags=["selfcheck", "repair"], source="nightly_selfcheck",
            )
        except Exception as e:
            logger.warning("[VECTOR][selfcheck] episodic store of failure record failed: {}", e)
        logger.error("[VECTOR][selfcheck] FAILED: {}", problems)
        return {"status": "failed", "problems": problems, "last_commit": last_commit}

    logger.info("[VECTOR][selfcheck] clean — syntax + smoke OK")
    return {"status": "ok", "last_commit": last_commit}


async def job_venture_pipeline(*, _ctx: dict | None = None) -> dict:
    """Weekly (Mon 07:00) — side-hustle discovery pipeline.

    Mines Reddit+HN problems (30d), clusters + ranks demand, validates the top
    software-solvable ideas through the startups district, drafts marketing
    scripts, writes data/venture/venture_report_*.md, and pushes a high-priority
    nudge (spoken by the realtime voice layer when the owner is present).
    Publishing and building remain owner-approved actions.
    """
    try:
        from districts.news_trends.venture_pipeline import VenturePipeline
        return await VenturePipeline().execute()
    except Exception as e:
        logger.warning(f"[VECTOR][cron] venture_pipeline failed: {e}")
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


async def job_oauth_refresh(*, _ctx: dict | None = None) -> dict:
    """Every 30 min — proactively refresh OAuth tokens expiring within the hour (Google etc.)."""
    try:
        from core.engine.oauth.flows import OAuthFlowManager
        refreshed = await asyncio.to_thread(OAuthFlowManager().refresh_expiring_tokens, 60)
        if refreshed:
            logger.info("[VECTOR][cron] oauth_refresh: refreshed {}", refreshed)
        return {"status": "ok", "refreshed": refreshed}
    except Exception as e:
        logger.warning("[VECTOR][cron] oauth_refresh failed: {}", e)
        return {"status": "error", "error": str(e)}


async def job_cloud_heartbeat(*, _ctx: dict | None = None) -> dict:
    """Every 5 min — push a status heartbeat to the cloud brain (no-op unless a brain URL is configured)."""
    try:
        from core.config import CONFIG
        from core.cloud.heartbeat import CloudBrainHeartbeat
        cloud = CONFIG.get("cloud", {}) or {}
        hb = CloudBrainHeartbeat(brain_url=cloud.get("brain_url", ""), api_key=cloud.get("api_key", ""))
        if not hb.is_enabled():
            return {"status": "disabled"}
        return {"status": "ok" if await hb.send() else "failed"}
    except Exception as e:
        logger.warning("[VECTOR][cron] cloud_heartbeat failed: {}", e)
        return {"status": "error", "error": str(e)}


async def job_content_plan(*, _ctx: dict | None = None) -> dict:
    """Daily 08:30 — plan one script -> schedule_post content plan (published later, owner-approved)."""
    try:
        from districts.content.content_planner import plan_daily_content
        result = await plan_daily_content()
        logger.info("[VECTOR][cron] content_plan: {}", result.get("status"))
        return result
    except Exception as e:
        logger.warning("[VECTOR][cron] content_plan failed: {}", e)
        return {"status": "error", "error": str(e)}


async def job_agent_gym(*, _ctx: dict | None = None) -> dict:
    """Every 30 min -- drill up to two idle agents that have a verifiable drill (core/city/work_board.py). A no-op unless VECTOR_GYM
    is on (default off); it moves no HP and waits while the owner is coding."""
    try:
        from core.city.work_board import get_board
        report = await get_board().run_cycle(max_agents=2)
        if report.get("ran"):
            logger.info("[VECTOR][cron] agent_gym: {}", [(r["agent"], r["drill"], r["passed"]) for r in report["ran"]])
        return {"status": "ok", **report}
    except Exception as e:
        logger.warning("[VECTOR][cron] agent_gym failed: {}", e)
        return {"status": "error", "error": str(e)}


async def job_content_scheduler(*, _ctx: dict | None = None) -> dict:
    """Daily at 9AM — publish all pending scheduled posts."""
    try:
        from districts.content.content_scheduler import ContentScheduler
        scheduler = ContentScheduler()
        result = await scheduler.run_pending()
        logger.info("[VECTOR][cron] content_scheduler: published={}", result.get("published", 0))
        return result
    except Exception as e:
        logger.warning("[VECTOR][cron] content_scheduler failed: {}", e)
        return {"published": 0, "error": str(e)}


async def job_post_training_run(*, _ctx: dict | None = None) -> dict:
    """Weekly Sat 04:00 — SFT+DPO LoRA training on VECTOR's own reasoning_chains
    + counterfactual rejections. Gated off by default (CONFIG["training"]["post_training_enabled"]).
    """
    from core.config import CONFIG
    cfg = CONFIG["training"]

    if not cfg.get("post_training_enabled", False):
        return {"status": "disabled"}

    try:
        base_model = cfg.get("post_training_base_model", "vector-coder")
        min_reward = cfg.get("post_training_min_chain_reward", 0.7)
        min_examples = cfg.get("post_training_min_examples", 50)

        sft_result = run_sft(
            adapter_name="vector-post-sft",
            base_model=base_model,
            min_reward=min_reward,
            min_examples=min_examples,
        )
        dpo_result = run_dpo(adapter_name="vector-post-dpo", base_model=base_model)

        try:
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store(
                event_type="post_training_run",
                content=f"sft={sft_result.get('status')} dpo={dpo_result.get('status')}",
                tags=["training", "post_training"],
                source="cron_jobs",
            )
        except Exception as exc:
            logger.warning("[VECTOR][cron] post_training_run episodic write failed: {}", exc)

        logger.info(
            "[VECTOR][cron] post_training_run: sft={} dpo={}",
            sft_result.get("status"), dpo_result.get("status"),
        )
        return {"status": "ok", "sft": sft_result, "dpo": dpo_result}
    except Exception as e:
        logger.warning("[VECTOR][cron] post_training_run failed: {}", e)
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
        ("content-plan",          "daily",  "30 8 * * *", job_content_plan),
        ("content-scheduler",     "daily",  "0 9 * * *", job_content_scheduler),
        ("daily-review-journal",  "daily",  "30 22 * * *", job_daily_review),
        ("daily-workflow-trigger","daily",  "0 8 * * *", job_trigger_workflow),
        ("weekly-benchmark-suite","weekly", "0 1 * * 0", job_benchmark_suite),
        ("weekly-recipe-sync",    "weekly", "30 1 * * 0", job_recipe_sync),
        ("weekly-dspy-optimize",  "weekly", "0 2 * * 0", job_weekly_dspy_optimize),
        ("weekly-growth-report",  "weekly", "0 23 * * 0", job_weekly_growth_report),
        ("weekly-venture-pipeline","weekly", "0 7 * * 1", job_venture_pipeline),
        ("weekly-post-training",  "weekly", "0 4 * * 6", job_post_training_run),
        ("nightly-selfcheck",     "daily",  "0 4 * * *", job_nightly_selfcheck),
        # SubconsciousLoop — every 30 min (uses interval, registered separately below)
    ]

    registered = 0
    for job_id, cadence, cron_expr, fn in jobs:
        if _try_register(scheduler, job_id, cadence, cron_expr, fn):
            registered += 1
            logger.info(f"[VECTOR][cron] registered {job_id} ({cadence}, {cron_expr})")
        else:
            logger.warning(f"[VECTOR][cron] could not register {job_id} — scheduler API mismatch")

    # SubconsciousLoop — interval-based (every 30 min), not a cron expression
    if _try_register_interval(scheduler, "subconscious-loop", 30, job_subconscious_loop):
        registered += 1
        logger.info("[VECTOR][cron] registered subconscious-loop (interval, 30min)")
    else:
        logger.warning("[VECTOR][cron] could not register subconscious-loop — scheduler API mismatch")

    for job_id, minutes, fn in (
        ("oauth-refresh", 30, job_oauth_refresh),
        ("cloud-heartbeat", 5, job_cloud_heartbeat),
        ("agent-gym", 30, job_agent_gym),
    ):
        if _try_register_interval(scheduler, job_id, minutes, fn):
            registered += 1
            logger.info("[VECTOR][cron] registered {} (interval, {}min)", job_id, minutes)
        else:
            logger.warning("[VECTOR][cron] could not register {} — scheduler API mismatch", job_id)

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

    # 2) APScheduler: add_job(func, trigger=CronTrigger, id=, replace_existing=).
    # APScheduler's add_job has no cron= or fn= kwarg (TypeError) and its
    # positional 2nd-arg form expects a trigger TYPE NAME ('cron'/'interval'),
    # not a crontab string (LookupError) — neither generic attempt below
    # works against it, so it needs its own real adapter, tried first since
    # this is the actual scheduler in production (Task 1.6).
    add_job = getattr(scheduler, "add_job", None)
    if callable(add_job):
        try:
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger.from_crontab(cron_expr)
            add_job(fn, trigger=trigger, id=job_id, replace_existing=True)
            return True
        except ImportError:
            pass  # apscheduler not installed — fall through to generic guesses
        except Exception as e:
            logger.debug(f"[VECTOR][cron] APScheduler add_job failed for {job_id}: {e}")

    # 3) Generic add_job(cron) interface — other scheduler implementations
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


def _try_register_interval(
    scheduler: Any,
    job_id: str,
    minutes: int,
    fn: Callable,
) -> bool:
    """Register a job with an interval trigger (every N minutes).

    Supports APScheduler's add_job(trigger='interval') and simple interval APIs.
    Falls back to cron expression every N minutes for other schedulers.
    """
    # 1) APScheduler-style: add_job(fn, 'interval', minutes=N, id=job_id)
    for name in ("add_job", "schedule", "register", "add"):
        api = getattr(scheduler, name, None)
        if callable(api):
            try:
                api(fn, "interval", minutes=minutes, id=job_id, replace_existing=True)
                return True
            except TypeError:
                # try without replace_existing (older APScheduler)
                try:
                    api(fn, "interval", minutes=minutes, id=job_id)
                    return True
                except Exception as e:
                    logger.debug("[VECTOR][cron] {} without replace_existing failed: {}", name, e)
            except Exception as e:
                # scheduler may use a different API; try next
                logger.debug("[VECTOR][cron] {} scheduling attempt failed: {}", name, e)

    # 2) Convenience method: schedule_interval(job_id, minutes, fn)
    for name in ("schedule_interval", "add_interval", "interval"):
        api = getattr(scheduler, name, None)
        if callable(api):
            try:
                api(job_id=job_id, minutes=minutes, fn=fn)
                return True
            except Exception:
                continue

    # 3) Fall back to cron (every 30 min = "*/30 * * * *")
    cron_expr = f"*/{minutes} * * * *"
    return _try_register(scheduler, job_id, "interval", cron_expr, fn)


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
    "job_content_scheduler",
    "job_content_plan",
    "job_oauth_refresh",
    "job_cloud_heartbeat",
    "job_agent_gym",
    "job_weekly_dspy_optimize",
    "job_weekly_growth_report",
    "job_venture_pipeline",
    "job_nightly_selfcheck",
    "job_trigger_workflow",
    "job_benchmark_suite",
    "job_recipe_sync",
    "job_subconscious_loop",
    "_MORNING_DIGEST_WORKFLOW",
    "_run_morning_digest_fn",
]