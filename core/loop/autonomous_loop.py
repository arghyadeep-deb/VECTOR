import sys
import asyncio
import datetime
import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from loguru import logger

if TYPE_CHECKING:
    from core.loop.decision_engine import Candidate
from core.config import CONFIG
from core.event_bus.types import Event, EventType
from core.event_bus.worker_pool import WorkerPool
from core.resilience.graceful_degradation import GracefulDegradation, ServiceTier
from core.resilience.hot_failover import HotFailover


def _scan_incoming(text: str, context: str = "") -> bool:
    """Scan incoming text for prompt injection. Returns True if clean."""
    try:
        from core.security.prompt_injection import scan_text
        result = scan_text(text, context)
        if not result.clean:
            logger.warning("[VECTOR][autonomous_loop] prompt injection blocked in {}: {}", context, result)
            return False
    except Exception as e:
        logger.warning("[VECTOR][autonomous_loop] prompt_injection scan failed ({}): {}", context, e)
    return True


def _get_loop_guard():
    """Get or create a LoopGuardState for the current task."""
    try:
        from core.loop.loop_guard import LoopGuardState
        return LoopGuardState(task_id="autonomous_loop")
    except Exception:
        return None


def _capture_loop_error(exc: Exception, context: str, district: str = "") -> None:
    """Send loop errors to Sentry + log via loguru. Never raises."""
    try:
        from core.engine.telemetry.sentry_bridge import init_sentry
        s = init_sentry()
        s.capture_exception(exc, context={
            "loop_context": context,
            "district": district,
            "component": "autonomous_loop",
        })
    except Exception:
        logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
    logger.error("[VECTOR][{}] {}: {}", context, type(exc).__name__, exc)


def _record_job_run(event) -> None:
    """APScheduler EVENT_JOB_EXECUTED/EVENT_JOB_ERROR listener — ground-truth
    "did this scheduled job actually fire" log, independent of whether the
    job itself writes anything to episodic memory.

    Without this, most of the ~12 cron jobs (subconscious_loop, biometrics,
    daily_review, dspy, etc.) write nowhere observable on a HEALTHY run —
    several only write an episodic row on FAILURE (e.g.
    job_nightly_selfcheck's "selfcheck_failure"). A 24h soak with no
    independent firing record can't tell "cron is still dead" from "cron
    fired but only logs failures" — this closes that gap permanently, not
    just for one soak window.
    """
    try:
        from core.memory.episodic import EpisodicMemory
        status = "error" if event.exception else "ok"
        content = f"job {event.job_id} {status}"
        if event.exception:
            content += f": {event.exception}"
        EpisodicMemory().store(
            event_type="scheduler_job_run",
            content=content,
            tags=["scheduler_job_run", event.job_id, status],
            source=event.job_id,
        )
    except Exception as e:
        logger.warning("[VECTOR][autonomous_loop] _record_job_run failed for {}: {}",
                        getattr(event, "job_id", "?"), e)


# ── Task 89B: event fan-out cooldown / dedup ────────────────────────────────
# Prevents AutonomousLoop._fanout_handler from re-firing the same downstream
# dispatch over and over inside a tight event cycle (e.g. the marketing <->
# data_analytics <-> strategy/content/marketing loop through ANALYTICS_READY,
# and the content <-> qa loop through CONTENT_REVIEWED). This is dedup on top
# of the existing EVENT_TRIGGER_MAP structure only — it does not change which
# edges exist, only how often each one is allowed to fire.
#
# Edge identity = (source_event_type, target_district, target_task_type) — a
# plain 3-tuple, matching the (district, task_type, params_template) shape
# get_downstream_tasks() already returns, plus the event that triggered it.
#
# Cooldown state is a bare in-process module-level dict (mirrors the existing
# module-level helpers in this file, e.g. _cron_last_run-style bookkeeping
# used elsewhere in the loop) — no persistence, no DB table. A process
# restart naturally clears it, which is the correct, desired behavior: a
# freshly started loop should not inherit stale cooldowns from a prior run.
_FANOUT_EDGE_COOLDOWN_SEC: float = CONFIG.get("fanout_edge_cooldown_sec", 120.0)
_fanout_edge_last_fired: dict[tuple[str, str, str], float] = {}


def _fanout_edge_should_fire(edge: tuple[str, str, str]) -> bool:
    """Decide whether a fan-out edge may dispatch right now, and if so,
    atomically start its cooldown.

    The timestamp is recorded the moment the edge is ACCEPTED — i.e. BEFORE
    governor.dispatch() is called, not after any result is known. Success,
    failure, and no-agent-available outcomes all consume the cooldown
    identically; none of them get to bypass or shorten it. Returns False
    (and logs at DEBUG — this is expected, frequent traffic shaping, not an
    error) if the edge is still inside its cooldown window.
    """
    now = time.monotonic()
    last_fired = _fanout_edge_last_fired.get(edge)
    if last_fired is not None and (now - last_fired) < _FANOUT_EDGE_COOLDOWN_SEC:
        logger.debug(
            "[VECTOR][event_fanout] edge {} still cooling down ({:.1f}s remaining) — dropping dispatch",
            edge, _FANOUT_EDGE_COOLDOWN_SEC - (now - last_fired),
        )
        return False
    _fanout_edge_last_fired[edge] = now
    return True


class AutonomousLoop:
    """
    RULE 2 — THE LOOP NEVER STOPS.
    run_forever() never returns. Every coroutine catches ALL exceptions and restarts.
    Loop: observe(0.5s) → think(event-driven) → act(permission-gated) → reflect(2AM) → sync(48h)
    """

    def __init__(self):
        self._running = False
        self._start_time: datetime.datetime | None = None
        self._tick_count = 0
        self._context_engine = None
        self._goal_system = None
        self._decision_engine = None
        self._last_presence: str = "unknown"   # tracks prior presence for change detection
        self._active_task_count: int = 0        # incremented/decremented by act_loop subtasks
        self._governor = None
        self._memory = None
        self._ambient = None
        self._policy = None
        self._red_team = None
        self._hypothesis_engine = None
        self._gateway = None
        self._cron_last_run: dict[str, datetime.datetime] = {}
        self._pending_voice: dict | None = None
        self._degradation = GracefulDegradation()
        self._failover = HotFailover(is_primary=True)
        self._tier_before = self._degradation.current_tier
        self._event_bus = None
        self._worker_pool = None
        # R8 (Task 93/overnight pipeline): the action_type _act_on() most
        # recently attempted -- consumed by _detect_and_store_correction() so
        # a correction lesson's `situation` field actually reflects the real
        # action being corrected, instead of the constant fallback
        # "conversation" every real production correction previously got
        # (this attribute was read via getattr(..., 'conversation') but never
        # ASSIGNED anywhere before R8 -- see R8_CORRECTION_LEARNING_REPORT.md
        # §"root cause").
        self._current_action_type: str | None = None
        logger.info("[VECTOR][autonomous_loop] initialized")

    async def _get_event_bus(self):
        if self._event_bus is None:
            from core.event_bus.bus import get_event_bus
            self._event_bus = await get_event_bus()
            # Only create a WorkerPool if run_forever hasn't already created one
            if self._worker_pool is None:
                from core.event_bus.worker_pool import WorkerPool
                self._worker_pool = WorkerPool(max_workers=10, name="event_bus")
        return self._event_bus

    def _tracked_task(self, coro, name: str = "") -> asyncio.Task:
        """Create an asyncio.Task that logs unhandled exceptions instead of
        silently swallowing them. The task handle is stored in _background_tasks
        (pruned on completion) so it's not garbage-collected mid-execution."""
        task = asyncio.create_task(coro, name=f"tracked_{name}")
        if not hasattr(self, "_background_tasks"):
            self._background_tasks: set[asyncio.Task] = set()
        self._background_tasks.add(task)

        def _on_done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            if not t.cancelled() and t.exception():
                logger.warning("[VECTOR][autonomous_loop] background task {!r} failed: {}",
                               name, t.exception())

        task.add_done_callback(_on_done)
        return task

    async def _fanout_handler(self, event) -> None:
        """Fan-out event to subscribed agents with gather + timeout, then trigger downstream tasks."""
        try:
            from core.city.agent_registry import get_registry
            from core.event_bus.wiring import get_downstream_tasks
            registry = get_registry()
            et = event.event_type.value if event.event_type else ""
            # Event-driven think wake: voice input never waits for the 10s poll
            if et == "voice_input":
                self._tracked_task(self.wake_think(), "wake_think")
            targets = [
                agent for agent in registry.get_all_agents()
                if et in agent.subscribed_events
            ]
            if targets:
                coros = [
                    self._dispatch_event_to_agent(agent, event)
                    for agent in targets
                ]
                results = await asyncio.gather(*coros, return_exceptions=True)
                for agent, result in zip(targets, results):
                    if isinstance(result, asyncio.TimeoutError):
                        logger.warning("[VECTOR][event_fanout] {} timeout on {}", agent.name, et)
                    elif isinstance(result, Exception):
                        logger.warning("[VECTOR][event_fanout] {} failed on {}: {}", agent.name, et, result)
            if event.event_type:
                governor = self._get_governor()
                for district, task_type, params_template in get_downstream_tasks(event.event_type):
                    edge = (et, district, task_type)
                    if not _fanout_edge_should_fire(edge):
                        continue
                    params = {k: (v.format(event_type=et, event_data=str(getattr(event, 'data', {})))) for k, v in params_template.items()}
                    task = {"type": task_type, "district": district, "params": params, "source_event": et}
                    self._tracked_task(governor.dispatch(task), f"dispatch_{district}_{task_type}")
        except Exception as e:
            logger.debug("[VECTOR][autonomous_loop] fan-out handler error: {}", e)

    async def _dispatch_event_to_agent(self, agent, event) -> None:
        """Dispatch a single event to a single agent with timeout."""
        event_data = event.__dict__ if hasattr(event, '__dict__') else {"event_type": event.event_type.value if event.event_type else ""}
        try:
            await asyncio.wait_for(
                agent.handle_event(event_data),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            raise
        except Exception:
            raise

    def _get_context(self):
        if self._context_engine is None:
            from core.loop.context_engine import ContextEngine
            self._context_engine = ContextEngine()
        return self._context_engine

    def _get_goals(self):
        if self._goal_system is None:
            from core.brain.goal_system import GoalSystem
            self._goal_system = GoalSystem()
        return self._goal_system

    def _get_decision(self):
        if self._decision_engine is None:
            from core.loop.decision_engine import DecisionEngine
            self._decision_engine = DecisionEngine()
        return self._decision_engine

    def _get_governor(self):
        if self._governor is None:
            from core.city.governor import Governor
            self._governor = Governor()
        return self._governor

    def _get_gateway(self):
        if self._gateway is None:
            from core.loop.permission_gateway import PermissionGateway
            self._gateway = PermissionGateway()
        return self._gateway

    def _get_policy(self):
        if self._policy is None:
            from core.memory.policy import PolicyMemory
            self._policy = PolicyMemory()
        return self._policy

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def _get_red_team(self):
        if self._red_team is None:
            try:
                from core.brain.red_team_agent import RedTeamAgent
                self._red_team = RedTeamAgent()
            except Exception as e:
                logger.debug(f"[VECTOR][act] RedTeamAgent unavailable: {e}")
        return self._red_team

    def _get_hypothesis_engine(self):
        if self._hypothesis_engine is None:
            try:
                from core.brain.hypothesis_engine import HypothesisEngine
                self._hypothesis_engine = HypothesisEngine()
            except Exception as e:
                logger.debug(f"[VECTOR][hypothesis] HypothesisEngine unavailable: {e}")
        return self._hypothesis_engine

    def _get_guidance(self):
        """Lazy-loads the VECTOR guidance system (threat detection + coherence + authority)."""
        if getattr(self, "_guidance", None) is None:
            try:
                from vectorcode.src.guidance import create_guidance_system
                self._guidance = create_guidance_system()
                logger.info("[VECTOR][guidance] guidance system online")
            except Exception as e:
                logger.warning(f"[VECTOR][guidance] ThreatDetector/guidance unavailable — self-defense layer DISABLED: {e}")
                self._guidance = None
        return self._guidance

    def _get_continue_gate(self):
        """ContinueGate: step-level budget + coherence enforcer for the autonomous loop."""
        if getattr(self, "_continue_gate", None) is None:
            try:
                from vectorcode.src.guidance import ContinueGate
                self._continue_gate = ContinueGate()
            except Exception as e:
                logger.warning(f"[VECTOR][guidance] ContinueGate unavailable: {e}")
                self._continue_gate = None
        return self._continue_gate

    def _continue_gate_coherence(self) -> float:
        """The coherence input ContinueGate is documented to take: CoherenceScheduler's score for the think loop.

        2026-09-26 fix. This used to pass `decision.winner.total_score` -- the 5-factor RANKING score -- as the
        "coherence", while ContinueGate stops anything below 0.4 and _think_tick() only requires 0.3 to act. Every winner
        scoring 0.30-0.40 was therefore picked, logged as "stop" and silently never run, tick after tick: 330 such drops
        (all `analyze_progress`) in the live log, and any plan step whose fallback scored 0.38 could never execute, so a
        multi-step plan could not terminate (V1 Stage 4's PARTIAL). A ranking score is not coherence.

        No events recorded for the loop means a neutral 1.0 (the scheduler's own no-evidence answer); if the guidance
        system is unavailable the gate's budget/rework checks still apply, so this fails neutral rather than blocking.
        """
        try:
            guidance = self._get_guidance()
            if guidance is not None:
                return float(guidance["coherence_scheduler"].compute_score("think_loop").overall)
        except Exception as _co_err:
            logger.debug("[VECTOR][continue_gate] coherence unavailable, using neutral: {}", _co_err)
        return 1.0

    def _scan_threats(self, text: str, context: str = "act") -> bool:
        """Run ThreatDetector over action description. Returns True if critical threat found."""
        gsys = self._get_guidance()
        if gsys is None:
            return False
        try:
            signals = gsys["threat_detector"].analyze_input(text, f"autonomous_loop:{context}")
            critical = [s for s in signals if s.severity >= 0.85]
            if critical:
                logger.warning(
                    f"[VECTOR][guidance] THREAT detected in {context}: "
                    + ", ".join(f"{s.category}({s.severity:.2f})" for s in critical)
                )
                return True
        except Exception as e:
            logger.debug(f"[VECTOR][guidance] threat scan error: {e}")
        return False

    def _record_external_rejection(self, action_type: str, params: dict, reason: str,
                                    decision_id: str = "", candidate_id: str = "") -> None:
        """Gap 4: feed genuine external rejections (ThreatDetector, RedTeam, council,
        Pushover owner approval) into CounterfactualMemory so should_avoid() learns
        from them — not just from its own auto-blocks.

        R7 (Task 92): decision_id/candidate_id are optional so any existing or
        future caller that doesn't have a real DecisionEngine decision behind it
        (this method predates R7) keeps working unchanged — CounterfactualMemory's
        `rejections.decision_id` column falls back to the old `action_type`
        behavior when no real decision_id is supplied, exactly as before R7.
        """
        try:
            from core.memory.counterfactual import CounterfactualMemory
            proposal = f"{action_type} {json.dumps(params, default=str)}"
            CounterfactualMemory().record_rejection(
                decision_id=decision_id or action_type, proposal=proposal, reason=reason[:200],
                context={"candidate_id": candidate_id} if candidate_id else None,
            )
        except Exception as e:
            logger.debug(f"[VECTOR][counterfactual] external rejection record skipped: {e}")

    # ─── Scheduler + Workflow integrations (VectorCode-absorbed) ─────────────

    def _get_scheduler(self):
        """Durable task scheduler — persistent state + retry semantics.

        Wraps core/scheduler/. Used by scheduler_loop() to fire scheduled
        tasks that must survive process restarts (vs the in-process timer
        loops which are lost on crash).
        """
        if getattr(self, "_scheduler", None) is None:
            try:
                from core.scheduler import TaskScheduler  # type: ignore
                from core.scheduler.store import SchedulerStore
                from core.runtime_paths import data_path
                store = SchedulerStore(data_path("scheduler.db"))
                self._scheduler = TaskScheduler(store=store)
                logger.info("[VECTOR][autonomous_loop] durable scheduler ready")
            except Exception as e:
                logger.warning(f"[VECTOR][autonomous_loop] scheduler unavailable: {e}")
                self._scheduler = None
        return self._scheduler

    def _get_callable_scheduler(self):
        """Real callable scheduler — APScheduler's AsyncIOScheduler.

        Task 1.6 of plans/wire-absorbed-repos-autonomy.md: _get_scheduler()
        (above) wraps core/scheduler/TaskScheduler, which is prompt/LLM-agent
        based (create_task -> _execute_task -> system.ask) and has no
        add_job/schedule/register/add — _try_register silently no-ops
        against it. That meant neither the ~12 pre-existing cron jobs nor
        the Hand Execution Engine ever actually fired. This is the real,
        callable-function scheduler register_default_jobs() and
        HandRunner().register_all() need; TaskScheduler is left untouched
        for its original prompt-task purpose.
        """
        if getattr(self, "_callable_scheduler", None) is None:
            try:
                from apscheduler.schedulers.asyncio import AsyncIOScheduler
                from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
                sched = AsyncIOScheduler()
                sched.add_listener(_record_job_run, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
                sched.start()
                self._callable_scheduler = sched
                logger.info("[VECTOR][autonomous_loop] callable scheduler (APScheduler) ready")
            except Exception as e:
                logger.warning(f"[VECTOR][autonomous_loop] callable scheduler unavailable: {e}")
                self._callable_scheduler = None
        return self._callable_scheduler

    def _get_workflow_runner(self):
        """DAG workflow runner. Districts can trigger multi-step workflows
        via runner.run(workflow_dict) — returns WorkflowResult.
        """
        if getattr(self, "_workflow_runner", None) is None:
            try:
                from core.loop.workflow_runner import WorkflowRunner  # type: ignore
                self._workflow_runner = WorkflowRunner()
                logger.info("[VECTOR][autonomous_loop] workflow runner ready")
            except Exception as e:
                logger.warning(f"[VECTOR][autonomous_loop] workflow runner unavailable: {e}")
                self._workflow_runner = None
        return self._workflow_runner

    async def scheduler_loop(self):
        """Fire durable scheduled tasks every 30s. Never crashes."""
        logger.info("[VECTOR][scheduler_loop] started — 30s tick")
        # Operator manager wire (absorbed OJ — alternative task scheduler)
        if getattr(self, "_operator_mgr", None) is not None:
            logger.info("[VECTOR][scheduler_loop] OperatorManager available")
        scheduler = self._get_scheduler()
        if scheduler is None:
            logger.info("[VECTOR][scheduler_loop] durable (prompt) scheduler unavailable — continuing with callable scheduler only")

        # Real callable scheduler (Task 1.6) — TaskScheduler above is
        # prompt/LLM-agent based and has no add_job/schedule/register/add,
        # so cron jobs and Hands must register against this one instead.
        callable_scheduler = self._get_callable_scheduler()
        if callable_scheduler is None:
            logger.warning("[VECTOR][scheduler_loop] callable scheduler unavailable — cron jobs and Hands will not fire")
        else:
            # Register default daily/weekly jobs on first init
            try:
                from core.loop.cron_jobs import register_default_jobs
                n = register_default_jobs(callable_scheduler)
                logger.info(f"[VECTOR][scheduler_loop] {n} default jobs registered")
            except Exception as exc:
                logger.warning(f"[VECTOR][scheduler_loop] cron registration failed: {exc}")

            # Hand Execution Engine — the 9 Hands in hands/registry.py were
            # orphaned dataclasses (0 refs outside hands/) until this call.
            try:
                from hands.runner import HandRunner
                n_hands = HandRunner().register_all(callable_scheduler)
                logger.info(f"[VECTOR][scheduler_loop] {n_hands} Hands registered")
            except Exception as exc:
                logger.warning(f"[VECTOR][scheduler_loop] hand registration failed: {exc}")

        if scheduler is None and callable_scheduler is None:
            logger.info("[VECTOR][scheduler_loop] no scheduler available — loop disabled")
            return

        while self._running:
            try:
                # Fire any tasks whose scheduled time has arrived
                fire_method = getattr(scheduler, "fire_due", None) or \
                              getattr(scheduler, "tick", None) or \
                              getattr(scheduler, "run_due", None)
                if callable(fire_method):
                    result = fire_method()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as e:
                _capture_loop_error(e, "scheduler_loop")
            # Also fire VECTOR-native cron jobs directly (TaskScheduler is
            # prompt-based; function-based jobs fire via this mechanism)
            try:
                await self._fire_vnative_cron_jobs()
            except Exception as e:
                logger.error(f"[VECTOR][scheduler_loop] native cron error: {e}")
            # Gap 4: drain retry queue — re-execute actions that previously failed
            try:
                from core.queue.retry_queue import RetryQueue
                from core.loop.permission_gateway import Action
                rq = RetryQueue.get()
                for item in rq.pop_due(limit=5):
                    try:
                        # F-10: retried actions previously skipped the act-layer's
                        # pre-filters (Counterfactual/ThreatDetector/RedTeam) because
                        # they call gw.execute() directly. Run the cheap pre-filters
                        # here so a retry can't bypass a counterfactual block or a
                        # known-threat action. The gateway itself still enforces the
                        # tier gate (the authoritative check); this is defense-in-depth.
                        import json as _json
                        _proposal = f"{item.action_type} {_json.dumps(item.params, default=str)}"
                        _skip = False
                        try:
                            from core.memory.counterfactual import CounterfactualMemory
                            _cf = CounterfactualMemory()
                            _should_avoid, _cf_score, _cf_reason = _cf.should_avoid(_proposal, threshold=0.7)
                            if _should_avoid and _cf_score > 0.7:
                                logger.warning(
                                    "[VECTOR][retry] {} dropped — counterfactual block (score={:.2f}): {}",
                                    item.action_type, _cf_score, _cf_reason[:80],
                                )
                                rq.requeue_or_dlq(item, f"counterfactual block: {_cf_reason[:120]}")
                                _skip = True
                        except Exception as _cf_err:
                            logger.debug("[VECTOR][retry] counterfactual pre-filter skipped: {}", _cf_err)
                        if _skip:
                            continue
                        # ThreatDetector scan on the action description
                        if self._scan_threats(_proposal, context="retry"):
                            logger.warning("[VECTOR][retry] {} dropped — ThreatDetector flagged it", item.action_type)
                            rq.requeue_or_dlq(item, "blocked by ThreatDetector on retry")
                            continue
                        gw = self._get_gateway()
                        action = Action(
                            action_type=item.action_type,
                            params=item.params,
                            proposed_by=item.proposed_by,
                        )
                        await gw.execute(action)
                        logger.info(f"[VECTOR][retry] replayed {item.action_type} (attempt {item.attempt})")
                    except Exception as retry_err:
                        rq.requeue_or_dlq(item, str(retry_err))
            except Exception as _rq_err:
                logger.debug(f"[VECTOR][scheduler_loop] retry drain error: {_rq_err}")
            # Phase 3E: Work-stealing — match queued tasks to available agents
            try:
                from core.loop.task_queue import TaskQueue
                tq = TaskQueue.get()
                queued_tasks = tq.list_queued()
                if len(queued_tasks) > 5:
                    from vectorcode.src.claims import ClaimService, Claimant
                    from core.city.agent_registry import get_registry
                    cs = ClaimService()
                    reg = get_registry()
                    alive = reg.list_alive()
                    if alive:
                        claimants = [
                            Claimant(
                                id=a.id, type="agent", name=a.name,
                                capabilities=[a.district],
                                specializations=[a.district],
                            )
                            for a in alive[:10]
                        ]
                        assigned = 0
                        for task in queued_tasks:
                            best = cs.auto_assign(
                                issue_id=task.id,
                                available_agents=claimants,
                                labels=[task.district] + task.tags,
                            )
                            if best:
                                try:
                                    cs.claim(
                                        issue_id=task.id, claimant=best,
                                        issue_title=task.name,
                                        labels=[task.district] + task.tags,
                                    )
                                    assigned += 1
                                except Exception:
                                    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
                        logger.info(
                            f"[VECTOR][claims] {len(queued_tasks)} queued → "
                            f"{assigned} claimed by {len(alive)} agents"
                        )
            except Exception as _cl_err:
                logger.debug(f"[VECTOR][scheduler_loop] work-stealing skipped: {_cl_err}")
            await asyncio.sleep(30.0)

    def _parse_cron_daily(self, expr: str) -> tuple[int, int] | None:
        """Parse ``M H * * *`` → (hour, minute). Returns None if not daily."""
        parts = expr.strip().split()
        if len(parts) == 5 and parts[2] == "*" and parts[3] == "*" \
                and parts[4] == "*":
            try:
                return int(parts[1]), int(parts[0])  # (hour, minute)
            except ValueError:
                return None
        return None

    @staticmethod
    def _cron_last_run_db(job_id: str) -> datetime.datetime | None:
        """Read the last fire time for a cron job from SQLite (survives restarts)."""
        try:
            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cron_dedup "
                "(job_id TEXT PRIMARY KEY, fired_at TEXT)"
            )
            conn.commit()
            row = conn.execute(
                "SELECT fired_at FROM cron_dedup WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row:
                return datetime.datetime.fromisoformat(row[0])
        except Exception as e:
            logger.debug("[VECTOR][cron] dedup read failed: {}", e)
        return None

    @staticmethod
    def _cron_mark_fired_db(job_id: str) -> None:
        """Record that a cron job fired now (persisted to SQLite)."""
        try:
            from core.memory.episodic import get_temp_cursor
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with get_temp_cursor() as cursor:
                cursor.execute(
                    "INSERT OR REPLACE INTO cron_dedup (job_id, fired_at) VALUES (?, ?)",
                    (job_id, now_iso),
                )
        except Exception as e:
            logger.debug("[VECTOR][cron] dedup write failed: {}", e)

    async def _fire_vnative_cron_jobs(self) -> None:
        """Check and fire VECTOR-native cron job entries at their scheduled times."""
        entries: list[tuple[str, str, Callable]] = []
        try:
            from core.loop.cron_jobs import job_trigger_workflow, job_benchmark_suite, job_recipe_sync
            entries += [
                ("daily-workflow-trigger",  "0 8 * * *",  job_trigger_workflow),
                ("weekly-benchmark-suite",  "0 1 * * 0",  job_benchmark_suite),
                ("weekly-recipe-sync",      "30 1 * * 0", job_recipe_sync),
            ]
        except ImportError as e:
            logger.debug("[VECTOR][cron] cron_jobs module unavailable: {}", e)
        try:
            from districts.content.video_pipeline import job_generate_daily_video
            entries.append(("daily-video-generation", "0 22 * * *", job_generate_daily_video))
        except ImportError as e:
            logger.debug("[VECTOR][cron] video_pipeline unavailable: {}", e)
        now = datetime.datetime.now(datetime.timezone.utc)
        for job_id, cron_expr, fn in entries:
            parsed = self._parse_cron_daily(cron_expr)
            if parsed is None:
                continue
            hour, minute = parsed
            if now.hour == hour and now.minute == minute:
                # Dedup: check SQLite for last fire time (survives restarts)
                last = self._cron_last_run_db(job_id)
                window_start = now.replace(second=0, microsecond=0)
                if last is None or last < window_start:
                    self._cron_mark_fired_db(job_id)
                    logger.info(f"[VECTOR][cron] firing {job_id}")
                    try:
                        result = fn()
                        if asyncio.iscoroutine(result):
                            result = await result
                        status = result.get('status', '?') if isinstance(result, dict) else str(result)[:40]
                        logger.info(f"[VECTOR][cron] {job_id} done: {status}")
                    except Exception as e:
                        logger.error(f"[VECTOR][cron] {job_id} failed: {e}")

    async def trigger_workflow(self, workflow: dict | str) -> dict:
        """Public entrypoint for districts to fire a DAG workflow.

        Accepts either a dict definition or a path to a YAML/JSON file.
        Returns a dict summary of the workflow result.
        """
        runner = self._get_workflow_runner()
        if runner is None:
            return {"status": "unavailable", "reason": "workflow runner not ready"}
        try:
            if isinstance(workflow, str):
                from core.loop.workflow_runner import load_workflow_file
                workflow = load_workflow_file(workflow)
            result = await runner.run(workflow)
            return {
                "status": result.overall_status,
                "name": result.name,
                "duration_seconds": result.duration_seconds,
                "tasks": {tid: {"status": r.status, "duration_seconds": r.duration_seconds}
                          for tid, r in result.task_results.items()},
            }
        except Exception as e:
            logger.error(f"[VECTOR][autonomous_loop] workflow failed: {e}")
            return {"status": "failed", "reason": str(e)}

    def _emit_crash_signal(self, exc: Exception) -> None:
        try:
            from districts.emergency.main import _emit
            self._tracked_task(
                _emit("system", "process_crash", True, "autonomous_loop", {"error": str(exc)[:200]}),
                "crash_signal",
            )
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

    # ─── Observe ──────────────────────────────────────────────────────────────

    async def observe_loop(self):
        """Observe world state every 0.5s. Never crashes."""
        interval = CONFIG["loop"]["observe_interval_sec"]
        logger.info(f"[VECTOR][observe] started — {interval}s interval")
        # NOTE (2026-07-11): LoopGuard (MAX_ITERATIONS=50) was ticked here and
        # false-fired every ~25s — it's a PER-TASK guard for bounded agent loops,
        # not the eternal observe loop (which is legitimately infinite and already
        # protected by the asyncio.timeout(15) per tick below). Removed.
        while self._running:
            try:
                async with asyncio.timeout(15):
                    await self._observe_tick()
                self._tick_count += 1
                try:
                    from core.loop import loop_state as _ls
                    _ls.update_runtime(tick_count=self._tick_count, running=self._running)
                except Exception as e:
                    logger.debug("[VECTOR][observe] loop_state update skipped: {}", e)
            except asyncio.TimeoutError:
                logger.warning("[VECTOR][observe] tick timed out (>15s) — skipping")
            except Exception as e:
                _capture_loop_error(e, "observe_loop")
                self._emit_crash_signal(e)
            await asyncio.sleep(interval)

    async def _observe_tick(self):
        if self._degradation.current_tier <= ServiceTier.EMERGENCY:
            return
        if self._ambient is None and self._degradation.current_tier >= ServiceTier.DEGRADED:
            from core.voice.ambient_listener import AmbientListener
            self._ambient = AmbientListener()
        result = None
        if self._ambient:
            result = await self._ambient.listen_tick()
        # FIX #8: Validate ambient listener output before it enters think→act pipeline
        if result is not None:
            if not isinstance(result, dict):
                logger.warning(f"[VECTOR][observe] Ambient returned non-dict: {type(result)} — discarding")
                return
            # Sanitize: ensure required fields exist and are correct types
            if "actionable" in result and not isinstance(result.get("actionable"), bool):
                result["actionable"] = False
            if "intent" in result and not isinstance(result.get("intent"), str):
                result["intent"] = ""
            if "confidence" in result:
                try:
                    result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
                except (TypeError, ValueError):
                    result["confidence"] = 0.0
            # Feed actionable voice results into the think→act pipeline
            if result.get("actionable"):
                self._pending_voice = result
                logger.debug("[VECTOR][observe] voice intent queued: {}", result.get("intent"))
                # User interaction detected — reset proactive care break timer
                try:
                    from core.avatar.proactive_care import get_proactive_care
                    get_proactive_care().record_break()
                except Exception:
                    logger.warning("[VECTOR] silent swallow")
                    pass

        # Avatar on_observe: pull health/fatigue signals + absorb voice sentiment
        if getattr(self, '_avatar', None) is not None:
            try:
                self._avatar.on_observe(result if isinstance(result, dict) else {})
            except Exception as _av_obs_err:
                logger.debug("[VECTOR][observe] avatar on_observe suppressed: {}", _av_obs_err)

    async def _publish_event(self, event_type: EventType, data: dict | None = None) -> None:
        if self._event_bus is None:
            return
        try:
            await self._event_bus.publish(Event(
                event_type=event_type,
                data=data or {},
                source="autonomous_loop",
            ))
        except Exception as exc:
            logger.debug("[VECTOR][autonomous_loop] event publish failed: {}", exc)
        # Phase 3A: also publish to VectorCode MessageBus as parallel channel
        try:
            from vectorcode.src.message_bus import MessageBus
            mb = MessageBus()
            mb.publish(
                channel=str(event_type.value if hasattr(event_type, 'value') else event_type),
                content=data or {},
                sender="autonomous_loop",
                qos=1,
            )
        except Exception as _mb_err:
            logger.debug("[VECTOR][autonomous_loop] vectorcode message_bus skipped: {}", _mb_err)

    # ─── Think ────────────────────────────────────────────────────────────────

    async def think_loop(self):
        """Event-driven reasoning — 10s evaluation cycle. Never crashes."""
        logger.info("[VECTOR][think] started — 10s evaluation cycle")
        while self._running:
            try:
                async with asyncio.timeout(60):
                    await self._think_tick()
                await asyncio.sleep(10)
            except asyncio.TimeoutError:
                logger.warning("[VECTOR][think] tick timed out (>60s) — skipping")
                await asyncio.sleep(5)
            except Exception as e:
                _capture_loop_error(e, "think_loop")
                await asyncio.sleep(5)

    async def _think_tick(self):
        """Evaluate goals → 4 candidates → decision → act. RULE 1: hydrate first."""
        from core.monitoring.perf_contracts import timed_ctx
        from core.loop.decision_engine import Candidate
        _perf_ctx = timed_ctx("think_tick")

        # Owner-coding backoff: while a vectorcode CLI session is live, skip
        # 2 of 3 think ticks. One GPU + OLLAMA_MAX_LOADED_MODELS=1 — VECTOR's
        # LLM calls would keep evicting the owner's coding model. Voice
        # intents still process every tick (checked below before any LLM use).
        try:
            if (CONFIG.get("sensing", {}).get("defer_llm_while_owner_codes", True)
                    and not getattr(self, "_pending_voice", None)):
                from core.sensing.stuck_detector import get_active_session
                if get_active_session() is not None:
                    self._owner_code_skip = getattr(self, "_owner_code_skip", 0) + 1
                    if self._owner_code_skip % 3:
                        logger.debug("[VECTOR][think] owner coding session live — tick deferred")
                        return
        except Exception as _oc_err:
            logger.debug("[VECTOR][think] owner-coding check skipped: {}", _oc_err)

        # Voice intent takes priority — act immediately, skip goal evaluation this tick
        pending = getattr(self, "_pending_voice", None)
        if pending:
            self._pending_voice = None
            # Rules engine bypass: answer simple queries without LLM
            _voice_text = pending.get("text", pending.get("params", {}).get("query", ""))
            if _voice_text:
                try:
                    from core.security.rules_engine import get_rules_engine
                    _re_engine = get_rules_engine()
                    _bypass_rule = _re_engine.match(_voice_text)
                    if _bypass_rule:
                        _bypass_resp = _re_engine.execute_rule(_bypass_rule, {})
                        logger.info(
                            "[VECTOR][bypass] rule '{}' matched input '{}'", 
                            _bypass_rule.category, _voice_text[:50],
                        )
                        try:
                            from core.memory.episodic import EpisodicMemory
                            EpisodicMemory().store(
                                event_type="bypass_response",
                                content="Q: " + _voice_text + " | A: " + _bypass_resp,
                                tags=["bypass", _bypass_rule.category],
                                source="rules_engine",
                            )
                        except Exception as _ep_err:
                            logger.warning("[VECTOR][loop] episodic bypass store suppressed: {}", _ep_err)
                        return
                except Exception as _re_err:
                    logger.debug("[VECTOR][bypass] rules engine failed: {}", _re_err)
            _person_id = self._handle_user_input(_voice_text)
            # 2026-09-23 fix (permission-boundary audit): this used to call
            # self._get_governor().dispatch({...}) here, re-running the exact
            # same intent a SECOND time with zero permission-gateway check.
            # Every real producer of `_pending_voice` --
            # core.voice.ambient_listener.AmbientListener.handle_voice_input()
            # (via PermissionGateway.execute()) and both external-task
            # ingestion routes (core/api/tasks.py, core/api/routers/tasks.py,
            # via PermissionGateway.execute()/evaluate_external()) -- already
            # runs the intent through the gateway (which itself routes
            # approved actions to Governor.dispatch()) before ever setting
            # this field. Re-dispatching here duplicated every approved
            # action's real-world side effect, and -- because this second
            # call bypassed the gateway entirely -- could still carry out an
            # action the gateway had just DENIED (RULE 3 violation: "Permission
            # Gateway is the ONLY path to real-world actions... Nothing
            # bypasses this"). The intent is already fully executed by the
            # time control reaches here; only the person-context update above
            # is still needed.
            logger.debug("[VECTOR][think] voice intent already executed via gateway: {}", pending.get("intent"))
            return

        # RULE 1 — world state snapshot before any reasoning
        # Run in thread — get_world_state() calls ScreenObserver.observe() (blocking OCR)
        world_state = await asyncio.to_thread(self._get_context().get_world_state)

        # EpistemicTracker: track beliefs at the exact point VECTOR has formed
        # semantic assessments from raw sense data + memory retrieval (Gap 3).
        # This is where INFORMATION → BELIEF happens.
        try:
            ctx = self._get_context()
            if hasattr(ctx, "track_beliefs"):
                updated = ctx.track_beliefs(world_state)
                if updated:
                    logger.debug(f"[VECTOR][think] epistemic beliefs updated: {updated}")
        except Exception as _eb:
            logger.debug(f"[VECTOR][think] epistemic belief tracking skipped: {_eb}")

        # 2026-09-23 fix: this used to `return` here when there were zero
        # goal-derived actions, which also skipped the plan-candidate block
        # below every single tick -- a real starvation bug (root cause of
        # VECTOR_TECHNICAL_KNOWLEDGE/STAGE_4_LONG_HORIZON_AUTONOMY_REPORT.md
        # Finding 3: an empty/disabled GoalSystem silently starved active
        # plans of any candidate at all). DecisionEngine.evaluate([]) already
        # returns a safe noop decision, so falling through with zero
        # candidates here is not a new risk.
        actions = self._get_goals().generate_immediate_actions(limit=4)

        # R11 (Native Goal Strategy Candidate Generation): the tag→action_type
        # semantic mapping that used to live here was genuinely dead code —
        # generate_immediate_actions()'s own returned dicts never carried a
        # "tags" key, so this loop's old `a.get("tags", [])` was always []
        # and its remap-on-first-match logic could never fire (see
        # VECTOR_TECHNICAL_KNOWLEDGE/R11_NATIVE_GOAL_STRATEGY_CANDIDATE_GENERATION_REPORT.md
        # for the full audit). It has moved to
        # core.brain.goal_system.GoalSystem.generate_immediate_actions()
        # itself — the correct layer for goal-CONTENT semantics per RULE 6 —
        # where it can propose SEVERAL distinct real strategies for one goal
        # (a single first-match-wins remap loop structurally cannot). Each
        # action dict's "action_type" here is therefore already the final,
        # fully-resolved value (tag-derived, or the GOAL_ACTION_MAP horizon
        # fallback); this loop's only remaining job is the existing 1:1
        # dict → Candidate translation.
        candidates = []
        for a in actions:
            candidates.append(
                Candidate(
                    action_type=a["action_type"],
                    params={"goal_id": a["goal_id"], "title": a["title"]},
                    goal_ids=[a["goal_id"]],
                    urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(
                        a.get("urgency", "low"), 0.5
                    ),
                    confidence=0.7,
                    source="think_loop",
                )
            )

        # ── Plan candidates: next ready steps from active plans ──────────────
        try:
            plan_candidates = self._get_plan_candidates()
            if plan_candidates:
                candidates.extend(plan_candidates)
                logger.debug(f"[VECTOR][think] {len(plan_candidates)} plan step candidates added")
        except Exception as _pc_err:
            logger.debug(f"[VECTOR][think] plan candidates suppressed: {_pc_err}")

        # Avatar on_think: 5% persona nudge based on current mood (mirrors causal_score blending)
        if getattr(self, '_avatar', None) is not None:
            try:
                mood = self._avatar.state.mood_label
                if mood in ("tense", "subdued"):
                    for c in candidates:
                        if any(kw in c.action_type for kw in ("review", "report", "research", "reflect")):
                            c.urgency = min(1.0, c.urgency + 0.05)
                            logger.debug("[VECTOR][think] avatar nudge +0.05 urgency for {} (mood={})", c.action_type, mood)
            except Exception as _av_th_err:
                logger.debug("[VECTOR][think] avatar on_think suppressed: {}", _av_th_err)

        decision = await self._get_decision().evaluate(candidates)
        self._age_plan_candidates(candidates, decision)
        if decision.winner.total_score > 0.3:
            # ContinueGate: step-level budget + coherence check before acting
            _cgate = self._get_continue_gate()
            if _cgate is not None:
                try:
                    _cgate_verdict = _cgate.evaluate(
                        agent_id="think_loop",
                        step_number=self._tick_count,
                        tokens_used=0,
                        tool_calls=0,
                        rework_count=0,
                        coherence_score=self._continue_gate_coherence(),
                    )
                    if _cgate_verdict in ("pause", "stop"):
                        logger.warning(
                            "[VECTOR][continue_gate] verdict='{}' — skipping act for '{}' (score={:.3f})",
                            _cgate_verdict, decision.winner.action_type, decision.winner.total_score,
                        )
                        return
                    if _cgate_verdict == "throttle":
                        logger.debug("[VECTOR][continue_gate] throttle — 5s delay before act")
                        await asyncio.sleep(5)
                except Exception as _cg_err:
                    logger.debug("[VECTOR][continue_gate] evaluation suppressed: {}", _cg_err)

            await self._publish_event(EventType.DECISION_MADE, {
                "action_type": decision.winner.action_type,
                "score": decision.winner.total_score,
                "goal_ids": decision.winner.goal_ids,
            })
            try:
                from core.loop.loop_state import save_goal
                if decision.winner.goal_ids:
                    save_goal(decision.winner.goal_ids[0])
            except Exception as _sg_err:
                logger.warning("[VECTOR][loop] save_goal suppressed: {}", _sg_err)
            await self._act_on(decision.winner)
        else:
            logger.debug(
                f"[VECTOR][decision] Winner '{decision.winner.action_type}' dropped: "
                f"score={decision.winner.total_score:.3f} < 0.3 threshold — no action taken"
            )

    # ─── Act ──────────────────────────────────────────────────────────────────

    def _capture_trace(self, event: str, data: dict) -> None:
        """Feed trace data to the absorbed TraceCollector if available."""
        if getattr(self, "_trace_collector", None) is not None:
            try:
                self._trace_collector.capture(event=event, **data)
            except Exception: logger.debug("[VECTOR][loop] exception suppressed")

    async def _run_soft_safety_checks(self, winner: "Candidate") -> bool:
        """RR-3.3 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
        RR3_OVERNIGHT_REMEDIATION_REPORT.md): the three soft, pre-gateway
        safety filters shared by both the native action path and the
        plan-step path -- CounterfactualMemory rejection-similarity veto,
        ThreatDetector content scan, RedTeamAgent adversarial review for
        RED-tier actions. Extracted verbatim from _act_on()'s previous
        inline block (only the three `return` statements became `return
        False`) so both callers share IDENTICAL veto/logging/suppression
        semantics -- no reimplementation, no behavior change for the
        native path. Returns False if `winner` was vetoed (already logged
        and recorded by this method); True if it's safe to proceed to
        execution. These are additional pre-gateway filters, not the
        authorization boundary itself -- the hard PermissionGateway tier
        gate (GREEN/YELLOW/RED/FORBIDDEN) runs downstream of this, in both
        the native governor.dispatch() path and PlanRunner/AutonomousExecutor,
        and is completely unaffected by this method either way.
        """
        # Gap 4: CounterfactualMemory -- block proposals similar to past rejections
        try:
            from core.memory.counterfactual import CounterfactualMemory
            _proposal = f"{winner.action_type} {json.dumps(winner.params, default=str)}"
            _cf = CounterfactualMemory()
            _should_avoid, _cf_score, _cf_reason = _cf.should_avoid(_proposal, threshold=0.7)
            if _should_avoid and _cf_score > 0.7:
                logger.warning(
                    "[VECTOR][counterfactual] action '{}' blocked (score={:.2f}): {}",
                    winner.action_type, _cf_score, _cf_reason[:80],
                )
                _cf.record_rejection(
                    # R7 (Task 92): pass the real per-decision-occurrence ID
                    # instead of the bare action_type (falls back to
                    # action_type only if this winner was never produced by
                    # DecisionEngine.evaluate() — same degraded behavior as
                    # before R7, never a crash).
                    decision_id=winner.decision_id or winner.action_type,
                    proposal=_proposal,
                    reason=f"auto-blocked: similar to past rejection (score={_cf_score:.2f})",
                    context={"candidate_id": winner.candidate_id} if winner.candidate_id else None,
                )
                # Task 89 (D3) — suppression/reward channel separation.
                # This used to call update_from_outcome(..., reward=0.05):
                # a hardcoded literal blended into the SAME avg_reward
                # cumulative mean real 5-factor/VectorCode outcomes
                # accumulate into -- a control-flow constant permanently
                # contaminating the real reward signal. record_suppression()
                # tracks vetoes in a separate veto_count column instead,
                # never touching avg_reward/sample_count. CounterfactualMemory's
                # own `rejections` table (record_rejection() above) already
                # captures full veto detail; this is not a duplicate of that
                # -- it exists only so a suppression-only row is
                # distinguishable from a real-outcome row under the same
                # canonical (action_type, params) identity decision_engine
                # reads from (PolicyMemory.make_situation_hash()).
                try:
                    _sit_hash = self._get_policy().make_situation_hash(
                        winner.action_type, winner.params
                    )
                    self._get_policy().record_suppression(winner.action_type, _sit_hash)
                except Exception as _pen_err:
                    logger.warning("[VECTOR][counterfactual] suppression record failed: {}", _pen_err)
                return False
            elif 0.4 < _cf_score <= 0.7 and _cf_reason:
                logger.info(
                    "[VECTOR][counterfactual] caution for '{}' (score={:.2f}): {}",
                    winner.action_type, _cf_score, _cf_reason[:80],
                )
                winner.params = {**winner.params, "_cf_caution": _cf_reason[:120]}
        except Exception as _cf_err:
            logger.debug("[VECTOR][counterfactual] check skipped: {}", _cf_err)

        # ThreatDetector: scan action description before execution (guidance.py)
        action_desc = f"{winner.action_type} {json.dumps(winner.params, default=str)}"
        if self._scan_threats(action_desc, context="act"):
            logger.warning(f"[VECTOR][guidance] action '{winner.action_type}' blocked by ThreatDetector")
            self._record_external_rejection(
                winner.action_type, winner.params, "blocked by ThreatDetector",
                decision_id=winner.decision_id, candidate_id=winner.candidate_id,
            )
            return False

        # RedTeamAgent adversarial review for RED-level actions (VECTOR Gap 2)
        _RED_ACTION_TYPES = set(CONFIG.get("permission", {}).get("red", []))
        if winner.action_type in _RED_ACTION_TYPES:
            red_team = self._get_red_team()
            if red_team is not None:
                try:
                    review = await red_team.attack_plan({
                        "action_type": winner.action_type,
                        "params": winner.params,
                        "goal_ids": winner.goal_ids,
                        "score": winner.total_score,
                    })
                    verdict = str(review.get("verdict", "APPROVED")).upper()
                    if verdict.startswith("BLOCKED"):
                        _rt_reason = review.get('reason', 'adversarial review failed')
                        logger.warning(
                            f"[VECTOR][red_team] RED action '{winner.action_type}' BLOCKED: "
                            f"{_rt_reason}"
                        )
                        self._record_external_rejection(
                            winner.action_type, winner.params, f"red_team: {_rt_reason}",
                            decision_id=winner.decision_id, candidate_id=winner.candidate_id,
                        )
                        return False
                    elif verdict.startswith("MODIFY"):
                        logger.info(
                            f"[VECTOR][red_team] RED action '{winner.action_type}' MODIFIED: "
                            f"{review.get('modification', '')}"
                        )
                        # Apply suggested modification to params if provided
                        if "modified_params" in review:
                            winner.params = {**winner.params, **review["modified_params"]}
                    else:
                        logger.debug(f"[VECTOR][red_team] RED action '{winner.action_type}' APPROVED")
                except Exception as rte:
                    logger.warning(f"[VECTOR][red_team] review failed (proceeding): {rte}")

        return True

    async def _act_on(self, winner: "Candidate") -> None:
        """
        Route winner to governor (which routes to permission_gateway).
        RULE 3 — LLM zero direct access. All through gateway.
        RULE 7 — update_from_outcome() AFTER every action.
        """
        self._active_task_count += 1
        # R8: record what VECTOR is acting on so a correction the owner makes
        # right after this action carries the real action_type as its lesson
        # `situation`, not the constant "conversation" fallback (see __init__
        # docstring on this attribute).
        self._current_action_type = winner.action_type
        try:
            await self._publish_event(EventType.AGENT_STATE_CHANGED, {
                "action_type": winner.action_type,
                "state": "acting",
                "score": winner.total_score,
            })

            # Proactive (anticipation / vision) actions surface as owner nudges, never
            # auto-execute. Route straight to the gateway (GREEN → nudge) and skip the
            # governor, which would mis-route them to a district agent.
            if winner.action_type.startswith("proactive_"):
                try:
                    gw = self._get_gateway()
                    if gw is not None:
                        from core.loop.permission_gateway import Action as _GWAction
                        _res = await gw.execute(_GWAction(
                            action_type=winner.action_type,
                            params=winner.params,
                            proposed_by=winner.source or "anticipation",
                        ))
                        logger.info(
                            "[VECTOR][act] proactive '{}' surfaced (status={})",
                            winner.action_type, _res.result.get("status") if _res.result else "?",
                        )
                except Exception as _pa_err:
                    logger.debug("[VECTOR][act] proactive surfacing skipped: {}", _pa_err)
                return

            # ── Plan step routing — execute through PlanRunner, still via gateway ──
            if winner.source and winner.source.startswith("plan:"):
                try:
                    # RR-3.3 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
                    # RR3_OVERNIGHT_REMEDIATION_REPORT.md): plan steps used
                    # to reach the hard PermissionGateway (unchanged, still
                    # authoritative) but skip the three NATIVE soft
                    # pre-checks entirely, since this branch returned before
                    # ever reaching them. Plan-step candidates carry every
                    # field these checks consume (action_type/params/
                    # goal_ids/total_score), and are arguably MORE in need
                    # of a fresh check than a spontaneous candidate: a plan
                    # step may have been authored well before a relevant
                    # rejection pattern existed, and its params are resolved
                    # from prior step outputs not fully known at authoring
                    # time. Defense-in-depth parity, not an authorization
                    # change -- PermissionGateway's tier gate is untouched.
                    if not await self._run_soft_safety_checks(winner):
                        return
                    await self._act_on_plan_step(winner)
                except Exception as _ps_err:
                    logger.error(f"[VECTOR][act] plan step execution failed: {_ps_err}")
                return

            # VectorCode routing — coding actions go through permission_gateway first, then bridge
            # RULE 3: LLM has ZERO direct access — gateway always gates, even for VectorCode tasks
            _VC_ACTION_TYPES = {"code_task", "code_review_vc", "code_generate", "code_fix", "code_debug"}
            if winner.action_type in _VC_ACTION_TYPES:
                try:
                    # RULE 3: gate through permission_gateway before executing
                    gw = self._get_gateway()
                    if gw is not None:
                        _level = gw.classify(winner.action_type)
                        if _level == "FORBIDDEN":
                            logger.warning(f"[VECTOR][act] VectorCode action '{winner.action_type}' is FORBIDDEN — blocked")
                            return
                        # 53_PERMISSION_BOUNDARY_INTEGRITY.md Finding 2 — see
                        # the identical fix in the skill-matching block below
                        # for the full rationale. No _VC_ACTION_TYPES member
                        # is currently classified YELLOW (all are RED or
                        # GREEN — see core/config.py), so this is a
                        # consistency/defense-in-depth fix, not an active
                        # bypass today; kept identical to the skill-matching
                        # block so a future YELLOW addition here can't
                        # silently reintroduce the same gap.
                        if _level in ("RED", "YELLOW"):
                            from core.loop.permission_gateway import Action as _GWAction
                            _gw_result = await gw.execute(_GWAction(
                                action_type=winner.action_type,
                                params=winner.params,
                                proposed_by="think_loop",
                            ))
                            if not _gw_result.approved:
                                logger.warning(f"[VECTOR][act] {_level} VectorCode action '{winner.action_type}' denied: {_gw_result.reason}")
                                return
                            # 2026-09-23 fix (independent review found this):
                            # gw.execute() for a RED/YELLOW _VC_ACTION_TYPES
                            # member already runs the REAL VectorCode task
                            # itself, inside PermissionGateway._execute_action()'s
                            # own code_task/code_review_vc/code_generate/
                            # code_fix/code_debug branch. The code below used
                            # to ALSO call get_bridge().run_task() again
                            # after approval -- one RED approval genuinely
                            # ran the underlying task twice. Use the result
                            # gw.execute() already produced; only fall
                            # through to a fresh bridge call for GREEN/
                            # UNKNOWN, which never went through
                            # _execute_action() at all.
                            #
                            # 2026-09-23 round 2 (independent re-review found
                            # this too): once gw.execute() has genuinely
                            # approved AND executed the task, NOTHING must be
                            # able to fall through to a second execution path
                            # below -- not even a bookkeeping failure. The
                            # outer `except Exception` around this whole
                            # block used to catch a reward/policy-update
                            # error here and log "falling through to
                            # governor", which could reach a real second
                            # dispatch. Bookkeeping is now its own try/except
                            # that can fail safely without ever un-committing
                            # this `return`.
                            try:
                                vc_result = _gw_result.result or {}
                                reward = 0.8 if vc_result.get("status") == "ok" else 0.3
                                pm = self._get_policy()
                                h = pm.make_situation_hash(winner.action_type, winner.params)
                                pm.update_from_outcome(winner.action_type, h, reward)
                                logger.info(f"[VECTOR][act] VectorCode {winner.action_type} → {vc_result.get('status')} reward={reward}")
                            except Exception as _bk_err:
                                logger.warning(f"[VECTOR][act] VectorCode reward/policy bookkeeping failed after real execution (not re-executing): {_bk_err}")
                            return
                        # GREEN / UNKNOWN → proceed to bridge (never went
                        # through gw.execute()/_execute_action() above, so
                        # this is still the only real execution).
                    from districts.coding.vectorcode_bridge import get_bridge
                    bridge = get_bridge()
                    if bridge.is_available():
                        # F-5: mark the context as gateway-approved for code
                        # execution so coding_tools file-write helpers accept calls
                        # from this path. Reset after the bridge runs.
                        from core.loop.permission_gateway import set_coding_grant
                        set_coding_grant(True)
                        try:
                            vc_result = await bridge.run_task(
                                winner.params.get("title", winner.action_type),
                                mode="run",
                            )
                        finally:
                            set_coding_grant(False)
                        reward = 0.8 if vc_result.get("status") == "ok" else 0.3
                        pm = self._get_policy()
                        # Task 89 (D2): canonical (action_type, params) identity,
                        # shared with decision_engine.py's reader — see
                        # PolicyMemory.make_situation_hash()'s docstring.
                        h = pm.make_situation_hash(winner.action_type, winner.params)
                        pm.update_from_outcome(winner.action_type, h, reward)
                        logger.info(f"[VECTOR][act] VectorCode {winner.action_type} → {vc_result.get('status')} reward={reward}")
                        return
                except Exception as _vc_err:
                    logger.warning(f"[VECTOR][act] VectorCode routing failed: {_vc_err} — falling through to governor")

            # Gap 17: SwarmCoordinator — for multi-agent actions, coordinate via swarm
            # before dispatching to the governor. Only activates when action_type
            # suggests multi-agent work (research, analysis, complex coding).
            _SWARM_ACTION_TYPES = {"research", "deep_research", "analyze", "code_task", "code_generate"}
            if winner.action_type in _SWARM_ACTION_TYPES:
                try:
                    from vectorcode.src.swarm import SwarmCoordinator, Topology
                    from core.city.agent_registry import get_registry
                    reg = get_registry()
                    alive_agents = [a for a in reg.list_all() if a.get("is_alive")]
                    if len(alive_agents) >= 3:
                        swarm = SwarmCoordinator(topology=Topology.ADAPTIVE)
                        for a in alive_agents[:8]:  # cap at 8 to avoid overhead
                            swarm.register_agent(
                                agent_id=a["id"],
                                hp=a.get("health_points", 500),
                                district=a.get("district", ""),
                            )
                        consensus = swarm.propose(
                            action_type=winner.action_type,
                            params=winner.params,
                            proposer_id="autonomous_loop",
                        )
                        if consensus and not consensus.get("approved", True):
                            logger.info(
                                f"[VECTOR][swarm] action '{winner.action_type}' rejected by swarm "
                                f"({consensus.get('reason', 'no consensus')})"
                            )
                            return
                        logger.debug(f"[VECTOR][swarm] {winner.action_type} approved by swarm")
                except Exception as _sw_err:
                    logger.debug(f"[VECTOR][swarm] coordination skipped: {_sw_err}")

            # Gap 17: Comms — broadcast action result to configured channels after execution.
            # This is done post-execution (see _broadcast_result below).

            # RR-3.3 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
            # RR3_OVERNIGHT_REMEDIATION_REPORT.md): these three soft
            # pre-execution safety checks used to live inline here only --
            # the plan-step branch above (`winner.source.startswith("plan:")`)
            # returned before ever reaching them, so a plan step could
            # execute something native action execution would soft-veto.
            # Extracted into _run_soft_safety_checks() so both paths share
            # the exact same veto/logging/suppression logic (no PermissionGateway
            # change, no planner redesign -- pure reuse).
            if not await self._run_soft_safety_checks(winner):
                return

            try:
                # Phase 3B: check VectorCode Skills system before governor dispatch
                # If a skill matches with confidence > 0.6, execute via skills and skip governor.
                _skill_executed = False
                try:
                    from vectorcode.src.skills.manager import SkillManager
                    sm = SkillManager()
                    skills = sm.match(action_type=winner.action_type, params=winner.params)
                    skill = skills[0] if skills else None
                    if skill and skill.confidence > 0.6:
                        # RULE 3: a matched skill is an LLM-selected action — it MUST pass
                        # the PermissionGateway like any other action. This path used to call
                        # sm.execute() directly, bypassing all gating (FORBIDDEN/RED never
                        # enforced). Mirror the VectorCode gate above.
                        _skill_allowed = True
                        gw = self._get_gateway()
                        if gw is not None:
                            _level = gw.classify(winner.action_type)
                            if _level == "FORBIDDEN":
                                logger.warning(
                                    f"[VECTOR][skills] '{winner.action_type}' is FORBIDDEN — skill '{skill.name}' blocked"
                                )
                                return
                            # 53_PERMISSION_BOUNDARY_INTEGRITY.md Finding 2:
                            # this only checked RED, so a YELLOW-classified
                            # action_type matched to a skill silently got
                            # GREEN (no-confirmation) treatment instead of
                            # the owner-confirmation/trust-ladder flow
                            # gw.execute() already implements for YELLOW —
                            # gw.execute() itself is the single source of
                            # truth for what YELLOW requires, so routing it
                            # through the same call RED already uses is the
                            # complete fix (no new logic).
                            if _level in ("RED", "YELLOW"):
                                from core.loop.permission_gateway import Action as _GWAction
                                _sk_gw = await gw.execute(_GWAction(
                                    action_type=winner.action_type,
                                    params=winner.params,
                                    proposed_by="skill",
                                ))
                                if not _sk_gw.approved:
                                    logger.warning(
                                        f"[VECTOR][skills] {_level} skill '{skill.name}' denied: {_sk_gw.reason}"
                                    )
                                    # RR-3.1 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
                                    # RR3_OVERNIGHT_REMEDIATION_REPORT.md): a denied
                                    # RED/YELLOW skill action used to only clear
                                    # _skill_allowed, leaving _skill_executed False —
                                    # which fell through to the general
                                    # `if not _skill_executed:` branch below and
                                    # dispatched the SAME action_type/params via
                                    # governor.dispatch(), an ungated path (unlike
                                    # the FORBIDDEN case just above, which correctly
                                    # `return`s). A gateway denial must actually stop
                                    # execution, not just skip one execution route.
                                    return
                        if _skill_allowed:
                            # F-5: a matched skill that writes code runs within
                            # the gateway-approved code context.
                            from core.loop.permission_gateway import set_coding_grant
                            _is_code_skill = winner.action_type in _VC_ACTION_TYPES
                            if _is_code_skill:
                                set_coding_grant(True)
                            try:
                                skill_result = sm.execute(skill.name, winner.params)
                            finally:
                                if _is_code_skill:
                                    set_coding_grant(False)
                            if skill_result and getattr(skill_result, "status", None) != "error":
                                result = {"status": "ok", "skill": skill.name}
                                _skill_executed = True
                                logger.info(f"[VECTOR][skills] {winner.action_type} handled by skill '{skill.name}' (conf={skill.confidence:.2f})")
                except Exception as _sk_err:
                    logger.debug(f"[VECTOR][skills] skill match skipped: {_sk_err}")

                if not _skill_executed:
                    # 2026-09-23 fix (independent review found this): a
                    # goal-derived candidate that isn't VC/swarm/skill-
                    # matched used to dispatch straight to
                    # Governor.dispatch() with NO permission-gateway
                    # involvement at all -- a real RULE 3 authorization
                    # bypass, not merely an audit-log gap. GREEN classified
                    # candidates were harmless in practice (GREEN never
                    # required approval), but GoalSystem can derive a
                    # YELLOW-classified action_type from a goal tag (e.g.
                    # "finance" -> "monthly_report", which is YELLOW and has
                    # a real handler that writes an Obsidian note) -- that
                    # class of action reached its handler with zero owner
                    # confirmation whenever no skill happened to intercept
                    # it first. Mirror the skill-match gate immediately
                    # above: classify first, and for RED/YELLOW require
                    # real gateway approval before Governor.dispatch() ever
                    # runs. GREEN is unchanged (dispatches directly, as
                    # before -- no approval was ever required for it).
                    gw = self._get_gateway()
                    _already_dispatched = False
                    if gw is not None:
                        _level = gw.classify(winner.action_type)
                        if _level == "FORBIDDEN":
                            logger.warning(
                                f"[VECTOR][act] '{winner.action_type}' is FORBIDDEN — blocked"
                            )
                            return
                        if _level in ("RED", "YELLOW"):
                            from core.loop.permission_gateway import Action as _GWAction
                            _gen_gw = await gw.execute(_GWAction(
                                action_type=winner.action_type,
                                params=winner.params,
                                proposed_by="think_loop",
                            ))
                            if not _gen_gw.approved:
                                logger.warning(
                                    f"[VECTOR][act] {_level} action '{winner.action_type}' denied: {_gen_gw.reason}"
                                )
                                return
                            # 2026-09-23 (fix, independent review found
                            # this): gw.execute() already ran
                            # _execute_action() for this exact
                            # action_type -- for the handful of types
                            # that branch dedicated handles (play_music,
                            # launch_app, run_shell_command, pc_*,
                            # write_note_personal, ...), REAL work
                            # already happened and its real result is
                            # sitting in _gen_gw.result. Unconditionally
                            # calling Governor.dispatch() again after
                            # this (the pre-existing code below) was a
                            # genuine double-execution bug for those
                            # types -- the same class already fixed in
                            # core/api/routers/control.py's
                            # _dispatch_pc_action() and the VC-action
                            # path earlier this session. Only fall
                            # through to a SEPARATE Governor.dispatch()
                            # when _execute_action() itself had no real
                            # handler for this action_type
                            # ("not_implemented" -- the generic fallback
                            # every action_type without a dedicated
                            # branch hits, which is the intentional,
                            # correct design for reaching a real
                            # district agent). Also issue the receipt
                            # that separate dispatch's own new
                            # authorization check (governor.py) now
                            # requires -- this exact action_type was
                            # just, genuinely, real-approved above.
                            if _gen_gw.result and _gen_gw.result.get("status") != "not_implemented":
                                result = _gen_gw.result
                                _already_dispatched = True
                            else:
                                self._get_gateway()._issue_approval_receipt(
                                    winner.action_type, purpose="governor_dispatch"
                                )
                    if not _already_dispatched:
                        result = await self._get_governor().dispatch({
                            "type": winner.action_type,
                            "params": winner.params,
                            "source": "autonomous_loop",
                        })
                    # 2026-09-23 fix (found alongside the gate above, then
                    # corrected after independent re-review): a handful of
                    # real, verified-safe read-only capabilities
                    # (core/loop/permission_gateway.py's own
                    # _OWNER_READONLY_DISPATCH_ACTION_TYPES -- git_status,
                    # check_git, git_log, recent_commits, search_arxiv)
                    # return their real handler's raw dict with NO "status"
                    # key EITHER on success (e.g. GitBot.get_status()'s real
                    # branch data) OR on a genuine internal failure
                    # (GitBot.get_status() returns {} when the repo can't be
                    # opened; get_recent_commits() returns [] both for a
                    # truly empty history and for a real failure). An
                    # earlier version of this fix defaulted ANY missing
                    # "status" to "ok" unconditionally -- which certified a
                    # real git failure as a false success just as much as
                    # the original bug certified a real success as a
                    # failure. Only default to "ok" when there is REAL
                    # evidence of success in the result -- the exact same
                    # evidence fields core/api/routers/commands.py's
                    # `_is_git_readonly_empty()` already uses to report this
                    # honestly to the owner. search_arxiv's real handlers
                    # already set "status" themselves, so it needs no
                    # special-casing here.
                    if winner.action_type in ("git_status", "check_git") and "status" not in result:
                        if result.get("branch"):
                            result["status"] = "ok"
                    elif winner.action_type in ("git_log", "recent_commits") and "status" not in result:
                        if result.get("commits"):
                            result["status"] = "ok"

                # Check for real user feedback in episodic memory (RULE 7 — real outcomes)
                user_feedback = self._get_recent_feedback(winner.action_type)

                # 5-factor RL reward (Architecture.md spec):
                completed = 1.0 if result.get("status") in ("ok", "executed") else 0.0
                # RR-2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
                # RR2_MEANINGFUL_UTILITY_REPORT.md): goal_progress must be
                # evidence-based, never a fabricated neutral default. This
                # used to be `float(result.get("goal_progress", 0.5))` --
                # since no production action handler ever populates this
                # key (RR-0's own exhaustive grep confirmed zero writers),
                # every action silently received a fake "half advanced my
                # goal" credit regardless of whether it had any attached
                # goal at all. That is the exact, proven root cause of
                # RG-D's repeated read_code (goal_alignment=0.00, no
                # attached goal) earning ~0.755 reward -- structurally
                # indistinguishable from a real, evidenced 0.5-progress
                # outcome. Distinguish "no evidence was ever provided"
                # (UNKNOWN) from a real, explicit 0.0-1.0 value via
                # EXPLICIT KEY PRESENCE, not a fallback default. UNKNOWN
                # contributes 0 to this weighted term -- a conservative,
                # non-rewarding treatment, never silently promoted to
                # "known positive" (the old bug) NOR conflated with a real,
                # evidenced "known zero" in the numeric reward alone; the
                # unknown/known distinction itself is preserved separately
                # in this action's own reasoning_chain steps below (RULE 8
                # observability), not collapsed away.
                _goal_progress_known = (
                    "goal_progress" in result and result.get("goal_progress") is not None
                )
                goal_progress = float(result["goal_progress"]) if _goal_progress_known else 0.0
                not_overridden = 0.0 if result.get("overridden") else 1.0
                not_corrected = 0.0 if result.get("corrected") else 1.0
                # Use real user feedback if available, else estimate from result
                if user_feedback is not None:
                    uf = user_feedback
                else:
                    uf = 0.7 if completed else 0.3

                reward = (
                    uf * 0.40
                    + goal_progress * 0.25
                    + not_overridden * 0.15
                    + not_corrected * 0.15
                    + completed * 0.05
                )

                pm = self._get_policy()
                # Task 89 (D2): canonical (action_type, params) identity,
                # shared with decision_engine.py's reader — see
                # PolicyMemory.make_situation_hash()'s docstring.
                h = pm.make_situation_hash(winner.action_type, winner.params)
                pm.update_from_outcome(winner.action_type, h, reward)

                # Epistemic belief update (JARVIS Gap 3): record the outcome
                # confidence for this action's domain so future scoring can
                # dampen uncertain/stale domains.
                # RR-3.2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
                # RR3_OVERNIGHT_REMEDIATION_REPORT.md): "blocked" (a
                # Governor-internal security-policy veto -- taint/prompt-
                # injection scanning; never a PermissionGateway RED/YELLOW
                # denial, which correctly never reaches this point at all)
                # and "no_capable_agent" (no agent anywhere declares this
                # capability -- a ROUTING gap) are NOT evidence the
                # capability itself misbehaves. Feeding them into the same
                # epistemic-confidence learning as a genuine error/failed/
                # timeout would teach "this action doesn't work" from a
                # security refusal or a routing gap -- the exact
                # authorization-denial/execution-failure conflation this
                # architecture must not make. Skip the belief write
                # entirely for these two shapes (leaves confidence
                # unchanged) rather than inventing a neutral value
                # merge_belief()'s real EMA has no concept of.
                _epistemic_status = result.get("status", "unknown")
                if _epistemic_status not in ("blocked", "no_capable_agent"):
                    try:
                        self._get_decision().record_epistemic_belief(
                            winner.action_type,
                            _epistemic_status,
                            reward,
                        )
                    except Exception as _eb_err:
                        logger.debug("[VECTOR][act] epistemic belief update skipped: {}", _eb_err)

                # Close the neural learning loop: train the policy network on the
                # real reward for the action it observed at decision time.
                try:
                    self._get_decision().record_outcome(reward)
                except Exception as _ne:
                    logger.warning(f"[VECTOR][act] neural record_outcome failed: {_ne}")

                # Goal feedback loop: REMOVED 2026-09-08 (Task 89C — goal progress semantics).
                # This block used to call gs.update_goal_progress() with a reward-scaled
                # increment on every successful action linked to a goal. Because
                # update_goal_progress() unconditionally sets status="completed" once
                # progress >= 1.0 (with no completion-criterion check), pure reward
                # accumulation could — and did — silently auto-complete goals that were
                # never meant to have a one-time "done" state (e.g. a recurring/habitual
                # goal). See VECTOR_TECHNICAL_KNOWLEDGE/89C_GOAL_PROGRESS.md for the full
                # writeup. Progress is no longer mutated here; explicit callers (human/API)
                # still use update_goal_progress() exactly as before. We keep a
                # observability-only log noting which goals this reward was associated
                # with — no goal.progress mutation happens here anymore.
                if winner.goal_ids and completed >= 1.0:
                    logger.debug(
                        "[VECTOR][goal] reward={:.3f} associated with goal_ids={} via {} "
                        "(progress NOT updated — reward-driven goal completion removed, Task 89C)",
                        reward, winner.goal_ids, winner.action_type,
                    )

                # Gap 6 / R24: record a real, STATE-SCOPED action -> outcome
                # causal edge so the graph populates over time with genuine
                # "under state S, action A produced outcome B" knowledge,
                # not an unscoped "A produced B in general" correlation log.
                # State key reuses the SAME real, already-proven presence
                # field R22's _situational_factor() consumes (see
                # causal_state_key()'s own docstring) -- winner.context_snapshot
                # is already populated by DecisionEngine.evaluate()'s RULE 1
                # injection by the time a winner reaches this point.
                try:
                    from core.memory.causal_graph import CausalGraph, causal_state_key
                    _cg = CausalGraph()
                    _state_key = causal_state_key(getattr(winner, "context_snapshot", None))
                    _action_id = f"action:{winner.action_type}@{_state_key}"
                    _outcome_id = f"outcome:{result.get('status', 'unknown')}"
                    if _cg.get_node(_action_id) is None:
                        _cg.add_node(_action_id, "action", winner.action_type, metadata={"state_key": _state_key})
                    if _cg.get_node(_outcome_id) is None:
                        _cg.add_node(_outcome_id, "outcome", result.get("status", "unknown"))
                    _cg.add_edge(_action_id, _outcome_id, strength=max(0.0, min(1.0, reward)), label="action_outcome")
                except Exception as _cg_err:
                    logger.warning("[VECTOR][loop] causal_graph record suppressed: {}", _cg_err)

                try:
                    from core.loop.loop_state import save_decision
                    save_decision(
                        winner.action_type, winner.params, winner.total_score,
                        decision_id=winner.decision_id, candidate_id=winner.candidate_id,
                    )
                except Exception as _sd_err:
                    logger.warning("[VECTOR][loop] save_decision suppressed: {}", _sd_err)

                if winner.reasoning_chain:
                    # R7 (Task 92): "candidate_executed" correlation — append a
                    # correlation marker to the existing reasoning_chain JSON
                    # list (steps) rather than adding a new column/table. This
                    # is a per-call INSERT (reasoning_chains.chain_id is fresh
                    # every time — not an aggregate row like policy_memory), so
                    # attaching per-occurrence identity here is safe.
                    self._get_memory().store_chain(
                        situation=winner.action_type,
                        goal_ids=winner.goal_ids,
                        steps=winner.reasoning_chain + [{
                            "correlation": {
                                "decision_id": winner.decision_id,
                                "candidate_id": winner.candidate_id,
                            }
                        }, {
                            # RR-2: preserve the unknown/known distinction
                            # for observability even though the single
                            # blended `reward` float cannot carry it —
                            # "unknown" must never read back indistinguishable
                            # from a real, evidenced "known zero".
                            "goal_progress_evidence": "known" if _goal_progress_known else "unknown",
                            "goal_progress_value": goal_progress if _goal_progress_known else None,
                        }],
                        action=winner.action_type,
                        outcome=f"status={result.get('status')} reward={reward}",
                        reward=reward,
                    )

                try:
                    from core.training.data_collector import DataCollector
                    DataCollector().record(
                        input_text=f"{winner.action_type}: {json.dumps(winner.params, default=str)}",
                        output_text=json.dumps(result.get("data", {}), default=str),
                        reward=reward,
                        metadata={"source": "autonomous_loop", "goal_ids": winner.goal_ids}
                    )
                except Exception: logger.debug("[VECTOR][loop] exception suppressed")

                self._capture_trace("act", {
                    "action": winner.action_type,
                    "result": result.get("status"),
                    "reward": reward,
                    "goal_ids": winner.goal_ids,
                })
                if result.get("status") in ("ok", "executed"):
                    await self._publish_event(EventType.TASK_COMPLETED, {
                        "action_type": winner.action_type,
                        "reward": reward,
                        "goal_ids": winner.goal_ids,
                    })
                else:
                    await self._publish_event(EventType.TASK_FAILED, {
                        "action_type": winner.action_type,
                        "status": result.get("status"),
                        "goal_ids": winner.goal_ids,
                    })
                logger.info(
                    f"[VECTOR][act] {winner.action_type} -> {result.get('status')} reward={reward:.3f}"
                    + (f" (user_feedback={uf:.2f})" if user_feedback is not None else "")
                )
                # Gap 17: Comms broadcast — notify configured channels when a significant
                # action completes. Only fires for YELLOW/RED-tier actions to avoid spam.
                _NOTIFY_ACTION_TYPES = {"send_message_routine", "commit_code", "create_calendar_event",
                                        "send_email", "deploy_production", "financial_transaction"}
                if winner.action_type in _NOTIFY_ACTION_TYPES and result.get("status") == "ok":
                    try:
                        from vectorcode.src.comms.platform_adapters import PlatformAdapters
                        adapters = PlatformAdapters()
                        msg = result.get("message") or f"VECTOR completed: {winner.action_type}"
                        await adapters.broadcast(msg, channels=["telegram", "discord"], priority="low")
                    except Exception as _comms_err:
                        logger.debug(f"[VECTOR][comms] broadcast skipped: {_comms_err}")
            except Exception as e:
                await self._publish_event(EventType.SYSTEM_ERROR, {
                    "action_type": getattr(winner, "action_type", "unknown"),
                    "error": str(e)[:200],
                })
                _capture_loop_error(e, "act_loop", district=str(getattr(winner, 'district', '') if 'winner' in dir() else ''))
                # RR-3.2 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
                # RR3_OVERNIGHT_REMEDIATION_REPORT.md): an uncaught exception
                # here used to reach ONLY the RetryQueue push below (pure
                # infrastructure resilience -- replays the identical
                # action_type/params on a backoff timer, never consulted by
                # PolicyMemory/EpistemicTracker/CausalGraph). Repeated real
                # crashes for the same action_type therefore produced ZERO
                # decision-relevant learning, unlike a status="error"/
                # "failed" result, which already dampens that action_type's
                # future candidate score via the proven epistemic-confidence
                # mechanism (see record_epistemic_belief below). This
                # reuses that SAME existing mechanism and the SAME reward
                # value the normal path already computes for a genuine
                # failure (no real user feedback -> uf=0.3, completed=0.0,
                # goal_progress=0 unknown, not_overridden=not_corrected=1.0
                # -> reward = 0.3*0.40+1.0*0.15+1.0*0.15 = 0.42) -- not an
                # invented penalty, the existing "failed" reward applied to
                # a shape that previously skipped it entirely. Uses status
                # "error" (never "blocked"/"no_capable_agent", so this is
                # NOT skipped by the shape-differentiation guard above --
                # an exception is a genuine capability malfunction signal).
                try:
                    _exc_action_type = getattr(winner, "action_type", "unknown")
                    _exc_reward = 0.3 * 0.40 + 0.0 * 0.25 + 1.0 * 0.15 + 1.0 * 0.15 + 0.0 * 0.05
                    _exc_pm = self._get_policy()
                    _exc_hash = _exc_pm.make_situation_hash(_exc_action_type, getattr(winner, "params", {}))
                    _exc_pm.update_from_outcome(_exc_action_type, _exc_hash, _exc_reward)
                    self._get_decision().record_epistemic_belief(_exc_action_type, "error", _exc_reward)
                except Exception as _exc_learn_err:
                    logger.debug("[VECTOR][act] exception-path failure learning skipped: {}", _exc_learn_err)
                # Gap 4: push to retry queue instead of silently dropping
                try:
                    from core.queue.retry_queue import RetryQueue
                    RetryQueue.get().push(
                        action_type=getattr(winner, "action_type", "unknown"),
                        params=getattr(winner, "params", {}),
                        proposed_by="autonomous_loop",
                        error=str(e)[:500],
                    )
                except Exception as _rq_err:
                    logger.debug(f"[VECTOR][act] retry_queue push failed: {_rq_err}")
        finally:
            self._active_task_count -= 1

    def _get_recent_feedback(self, action_type: str) -> float | None:
        """Check episodic memory for recent user feedback on this action type. Returns 0.0-1.0 or None."""
        try:
            mem = self._get_memory()
            results = mem.recall(f"feedback: {action_type}", limit=1, event_type="user_feedback")
            if results:
                ctx = results[0].get("context") or {}
                if isinstance(ctx, str):
                    import json as _json
                    ctx = _json.loads(ctx)
                reward = ctx.get("reward")
                if reward is not None:
                    return float(reward)
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return None

    # ── Plan system integration ──────────────────────────────────────────────

    def _get_plan_store(self):
        """Lazy-init PlanStore singleton."""
        if getattr(self, "_plan_store", None) is None:
            from core.runtime.plans import get_plan_store
            self._plan_store = get_plan_store()
        return self._plan_store

    def _get_plan_candidates(self) -> list:
        """Get next ready steps from all active plans as Candidate objects.

        Each ready step becomes a Candidate with source="plan:{plan_id}:{step_id}"
        and a +0.05 urgency bonus (plan momentum). The existing decision engine
        scores these alongside goal candidates — no separate path.
        """
        from core.loop.decision_engine import Candidate

        plan_store = self._get_plan_store()
        waits = getattr(self, "_plan_step_waits", {})
        candidates = []
        for plan in plan_store.active_plans():
            for step in plan.next_ready_steps(limit=2):
                source = f"plan:{plan.id}:{step.id}"
                waited = waits.get(source, 0)
                c = Candidate(
                    action_type=step.action_type,
                    params={**step.params, "_plan_id": plan.id, "_step_id": step.id},
                    goal_ids=[plan.goal_id] if plan.goal_id else [],
                    # Anti-starvation aging (2026-09-27): a ready step that keeps losing to ambient goal candidates gains
                    # confidence and urgency (+0.1 each per lost tick, capped at 1.0) until it is picked. Without it a
                    # plan step scoring 0.715 lost to an ambient candidate at 0.72-0.76 tick after tick, and the plan
                    # never advanced (tests/test_stage4_real_goalsystem_competition.py).
                    confidence=min(1.0, step.confidence + 0.1 * waited),
                    urgency=min(1.0, 0.55 + 0.05 + 0.1 * waited),  # plan momentum bonus + aging
                    timing_score=1.0,
                    estimated_cost_inr=step.estimated_cost_inr,
                    source=source,
                    priority_bonus=min(0.3, 0.04 * waited),   # goal-less plans (neutral 0.3 alignment) need more than inputs
                )
                candidates.append(c)
        return candidates

    def _age_plan_candidates(self, candidates: list, decision) -> None:
        """Count, per ready plan step, the consecutive decisions it lost; a step that won (or vanished) starts over."""
        try:
            winner_source = getattr(decision.winner, "source", "") or ""
            waits = getattr(self, "_plan_step_waits", {})
            self._plan_step_waits = {
                c.source: (0 if c.source == winner_source else waits.get(c.source, 0) + 1)
                for c in candidates
                if isinstance(getattr(c, "source", None), str) and c.source.startswith("plan:")
            }
        except Exception as e:  # noqa: BLE001 -- bookkeeping must never break the think tick
            logger.debug("[VECTOR][think] plan aging skipped: {}", e)

    async def _act_on_plan_step(self, winner: "Candidate") -> None:
        """Execute a plan step through PlanRunner (which uses the permission gateway).

        Called from _act_on when winner.source starts with 'plan:'.
        Still goes through the gateway — PlanRunner.execute_step() calls
        AutonomousExecutor which wraps permission_gateway.
        """
        source_parts = winner.source.split(":")
        if len(source_parts) < 3:
            logger.warning(f"[VECTOR][act] malformed plan source: {winner.source}")
            return
        plan_id, step_id = source_parts[1], source_parts[2]

        plan_store = self._get_plan_store()
        plan = plan_store.get(plan_id)
        if plan is None:
            logger.warning(f"[VECTOR][act] plan {plan_id} not found — skipping")
            return
        step = plan.get_step(step_id)
        if step is None:
            logger.warning(f"[VECTOR][act] step {step_id} not found in plan {plan_id}")
            return

        try:
            from core.runtime.plans import PlanRunner
            runner = PlanRunner(store=plan_store)
            result = await runner.execute_step(plan, step)
            logger.info(
                "[VECTOR][act] plan step {}:{} → {} (plan={:.0%}, status={})",
                plan_id, step_id,
                result.get("status"), result.get("plan_progress", 0),
                result.get("plan_status"),
            )

            # Update policy (RULE 7) — same reward shape as _act_on
            completed = 1.0 if result.get("status") == "completed" else 0.0
            reward = 0.7 if completed else 0.3
            try:
                pm = self._get_policy()
                # E2 (outcome attribution audit): this used to hash a
                # "plan_step:"-prefixed key locally (hashlib.sha256(f"plan_step:
                # {action_type}:{json.dumps(params, sort_keys=True)}")) instead
                # of PolicyMemory's own canonical make_situation_hash(). That
                # was a SEPARATE identity namespace from every other writer/
                # reader in this codebase (decision_engine._score_candidate()'s
                # get_score(), the main _act_on() reward writer, the
                # VectorCode reward writer) -- a reward learned from executing
                # a plan step could never be read back by DecisionEngine
                # scoring the same (action_type, params) as a regular
                # candidate, and vice versa. Task 89 (D2) identified this
                # exact writer as a 4th non-canonical caller and explicitly
                # deferred it as an "identity-merge design question" rather
                # than silently leaving it undocumented. Per PolicyMemory's
                # own identity model -- (action_type, params) is a reusable
                # SITUATION, independent of what proposed it -- there is no
                # stated reason a plan-driven execution of the same action
                # should be tracked separately from a spontaneous one, so
                # this reconnects it to the same canonical identity every
                # other writer already uses. No plan_step:-prefixed historical
                # rows are affected or migrated -- they simply stop being
                # written to going forward.
                h = pm.make_situation_hash(winner.action_type, winner.params)
                pm.update_from_outcome(winner.action_type, h, reward)
            except Exception as _pm_err:
                logger.debug(f"[VECTOR][act] plan step policy update skipped: {_pm_err}")

            # Epistemic belief update
            try:
                self._get_decision().record_epistemic_belief(
                    winner.action_type,
                    result.get("status", "unknown"),
                    reward,
                )
            except Exception:
                pass

            # R26 (Cognitive Integration audit): the main _act_on() path has
            # written real, state-scoped causal edges (Gap 6 / R24) since
            # R24 shipped, but this plan-step path -- reached whenever
            # winner.source starts with "plan:" (see _act_on()'s own early
            # dispatch above) -- never did, despite writing the SAME
            # PolicyMemory/EpistemicTracker updates just above. That meant
            # R24's causal factor and R25's simulation factor were
            # permanently blind to any real experience gained through plan
            # execution -- a genuine "learning not correlated to
            # causal/simulation state" gap the R26 architecture audit was
            # explicitly asked to find. Real, distinct outcome statuses
            # here (`step.status`: "completed"/"failed"/"blocked", richer
            # than the main path's often-unknown status) make this a
            # genuinely informative real signal once connected, not a
            # cosmetic parity fix. Same real writer shape as the main path.
            try:
                from core.memory.causal_graph import CausalGraph, causal_state_key
                _cg = CausalGraph()
                _state_key = causal_state_key(getattr(winner, "context_snapshot", None))
                _action_id = f"action:{winner.action_type}@{_state_key}"
                _outcome_id = f"outcome:{result.get('status', 'unknown')}"
                if _cg.get_node(_action_id) is None:
                    _cg.add_node(_action_id, "action", winner.action_type, metadata={"state_key": _state_key})
                if _cg.get_node(_outcome_id) is None:
                    _cg.add_node(_outcome_id, "outcome", result.get("status", "unknown"))
                _cg.add_edge(_action_id, _outcome_id, strength=max(0.0, min(1.0, reward)), label="action_outcome")
            except Exception as _cg_err:
                logger.warning("[VECTOR][loop] plan-step causal_graph record suppressed: {}", _cg_err)

            # Bridge only verified plan progress into the linked goal. Ordinary
            # action rewards remain excluded (Task 89C). A plan reaching 1.0 is
            # capped below 1.0 (PLAN_PROGRESS_GOAL_CAP) rather than excluded
            # outright: excluding exactly 1.0 gave single-step plans (progress
            # jumps 0.0 -> 1.0 in one step, never passing through the open
            # interval) zero contribution to their linked goal, ever, while
            # multi-step plans still got partial credit. Capping preserves the
            # real invariant this bridge exists to guarantee -- plan progress
            # alone can never fire GoalSystem.update_goal_progress()'s
            # progress>=1.0 -> status="completed" transition -- without that
            # asymmetry.
            plan_progress = result.get("plan_progress")
            if (
                plan.goal_id
                and result.get("status") == "completed"
                and result.get("verification_passed") is True
                and isinstance(plan_progress, (int, float))
                and not isinstance(plan_progress, bool)
                and 0.0 < plan_progress <= 1.0
            ):
                goal_system = self._get_goals()
                goal = next(
                    (g for g in goal_system.get_active_goals() if g.get("id") == plan.goal_id),
                    None,
                )
                if goal is not None:
                    PLAN_PROGRESS_GOAL_CAP = 0.99
                    current_progress = goal.get("progress", 0.0)
                    new_progress = min(PLAN_PROGRESS_GOAL_CAP, max(current_progress, plan_progress))
                    if new_progress > current_progress:
                        goal_system.update_goal_progress(
                            plan.goal_id,
                            new_progress,
                            note=(
                                f"Verified partial plan progress: plan_id={plan_id}, "
                                f"step_id={step_id}, verification_passed="
                                f"{result.get('verification_passed')}, "
                                f"old_progress={current_progress}, new_progress={new_progress}"
                            ),
                        )

        except Exception as e:
            logger.error(f"[VECTOR][act] plan step execution error: {e}")

    # ─── Reflect ──────────────────────────────────────────────────────────────

    def _notify_user(self, text: str) -> None:
        """Send formatted text to user via TTS or log. Never raises."""
        if not text:
            return
        try:
            from core.voice.tts import TextToSpeech
            tts = TextToSpeech()
            tts.speak(text)
            return
        except Exception as e:
            logger.debug('[VECTOR][notify] TTS unavailable: {}', e)
        logger.info('[VECTOR][RESPONSE] {}', text[:200])

    def _handle_user_input(self, text: str, person_id: str = "owner") -> str:
        """
        Tag incoming user voice/text input with person_id so PersonalityLayer
        can adapt the LLM response style to the addressed person's preferences.
        Stores person_id as _current_person_id; returns it for testability.
        Default is 'owner' -- the primary user of this VECTOR instance.

        Also runs correction detection: if the owner is correcting VECTOR's
        previous response, the correction is stored as a lesson for future use.
        Never raises.
        """
        self._current_person_id = person_id
        logger.debug("[VECTOR][loop] user input from person={} len={}", person_id, len(text))

        # ── Correction detection (owner only) ────────────────────────────
        if person_id == "owner":
            try:
                self._detect_and_store_correction(text)
            except Exception as _cl_err:
                logger.debug("[VECTOR][loop] correction detection suppressed: {}", _cl_err)

        return person_id

    def _detect_and_store_correction(self, utterance: str) -> None:
        """Check if the owner's utterance is a correction and store it as a lesson.

        Retrieves the most recent VECTOR response from episodic_memory to use as
        the 'wrong_behavior' context for lesson extraction.
        """
        try:
            from core.memory.correction_learner import CorrectionLearner
            learner = CorrectionLearner()

            # Get VECTOR's last response as context for the correction
            prior_response = ""
            try:
                mem = self._get_memory()
                recent = mem.recall("", limit=3, event_type="vector_response")
                if recent:
                    prior_response = recent[0].get("content", "")[:300]
            except Exception:
                pass

            context = {
                "situation": getattr(self, '_current_action_type', 'conversation') or "conversation",
                "person_id": "owner",
            }

            lesson = learner.process_owner_message(
                utterance=utterance,
                prior_vector_response=prior_response,
                context=context,
            )
            if lesson is not None:
                logger.info(
                    "[VECTOR][loop] correction stored: domain={} lesson='{}'",
                    lesson.domain,
                    lesson.lesson[:60],
                )
        except Exception as e:
            logger.debug("[VECTOR][loop] correction detection failed: {}", e)

    async def reflect_loop(self):
        """2AM daily reflection. Never crashes."""
        logger.info("[VECTOR][reflect] started — fires at 2:00 AM daily")
        while self._running:
            try:
                now = datetime.datetime.now(datetime.timezone.utc)
                reflect_hour = CONFIG["loop"]["reflect_hour"]
                reflect_min = CONFIG["loop"]["reflect_minute"]

                next_reflect = now.replace(
                    hour=reflect_hour, minute=reflect_min, second=0, microsecond=0
                )
                if now >= next_reflect:
                    next_reflect += datetime.timedelta(days=1)

                wait_secs = (next_reflect - now).total_seconds()
                logger.info(f"[VECTOR][reflect] next in {wait_secs/3600:.1f}h")
                # Sleep in 1s chunks so stop() takes effect immediately
                remaining = min(wait_secs, 3600)
                while self._running and remaining > 0:
                    await asyncio.sleep(min(1.0, remaining))
                    remaining -= 1.0

                if self._running and datetime.datetime.now(datetime.timezone.utc).hour == reflect_hour:
                    # 2026-08-06 (loop-stall root-cause hunt, KNOWN_ISSUES #0):
                    # observe_tick (15s) and think_tick (60s) already had
                    # asyncio.timeout coverage; this one didn't, despite
                    # calling out to DailyReviewer, SelfImprovementCycle,
                    # ConsolidationBot, EvolutionEngine, and more — any one
                    # hanging froze the loop thread with literally no bound.
                    try:
                        async with asyncio.timeout(CONFIG["loop"]["reflect_tick_timeout_sec"]):
                            await self._reflect_tick()
                    except asyncio.TimeoutError:
                        logger.warning(
                            "[VECTOR][reflect] tick timed out (>{}s) — skipping",
                            CONFIG["loop"]["reflect_tick_timeout_sec"],
                        )

            except Exception as e:
                _capture_loop_error(e, "reflect_loop")
                # Chunked backoff so stop() is responsive
                for _ in range(300):
                    if not self._running:
                        break
                    await asyncio.sleep(1.0)

    async def _reflect_tick(self) -> None:
        logger.info("[VECTOR][reflect] 2AM reflection starting...")
        try:
            from districts.reflection.daily_reviewer import DailyReviewer
            reviewer = DailyReviewer()
            ok = await reviewer.review()
            logger.info(f"[VECTOR][reflect] DailyReviewer done — ok={ok}")
        except Exception as e:
            logger.error(f"[VECTOR][reflect] DailyReviewer failed: {e}")

        # ── Plan review: pause stale plans, abandon low-confidence plans ──────
        try:
            from core.runtime.plans import get_plan_store
            _plan_store = get_plan_store()
            _now = datetime.datetime.now(datetime.timezone.utc)
            for _plan in _plan_store.active_plans():
                _age_days = (_now - datetime.datetime.fromisoformat(_plan.created_at)).days
                # Abandon low-confidence plans that have exhausted replan budget
                if _plan.confidence < 0.3 and _plan.replan_count >= 2 and _plan.status == "active":
                    _plan.status = "abandoned"
                    _plan.record_event("abandoned_reflect", "Low confidence after multiple replans (2AM review)")
                    _plan_store.save()
                    logger.info("[VECTOR][reflect] plan {} abandoned (conf={:.2f}, replans={})", _plan.id, _plan.confidence, _plan.replan_count)
                # Pause stale plans (>30 days old and still active)
                elif _age_days > 30 and _plan.status == "active":
                    _plan.status = "paused"
                    _plan.record_event("paused_reflect", f"Stale plan ({_age_days}d old, 2AM review)")
                    _plan_store.save()
                    logger.info("[VECTOR][reflect] plan {} paused (age={}d)", _plan.id, _age_days)
                # Decay epistemic confidence for plan steps that haven't run recently
                elif _age_days > 7:
                    for _step in _plan.steps:
                        if _step.status == "planned" and _step.confidence > 0.3:
                            _step.confidence = round(_step.confidence * 0.95, 3)  # 5% decay per week
                    _plan.update_progress()
                    _plan_store.save()
        except Exception as _pr_err:
            logger.debug(f"[VECTOR][reflect] plan review suppressed: {_pr_err}")

        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            if now.weekday() == 6:
                from core.training.self_improvement_cycle import SelfImprovementCycle
                cycle = SelfImprovementCycle()
                result = await asyncio.to_thread(cycle.run_weekly)
                status = result.get("status", "?")
                phases = result.get("phases", {})
                logger.info(f"[VECTOR][reflect] SelfImprovementCycle: {status} "
                            f"(collect={phases.get('collect',{}).get('samples',0)}, "
                            f"train={phases.get('train',{}).get('status','?')})")

                if result.get("status") == "ok":
                    try:
                        from core.training.openmythos.trainer import SelfImprovementTrainer
                        trainer = SelfImprovementTrainer()
                        eval_result = trainer.evaluate()
                        baseline = {"coherence": eval_result["coherence"] * 0.9}
                        deploy_ok, reason = trainer.should_deploy(eval_result, baseline)
                        if not deploy_ok:
                            logger.warning("[VECTOR][training] eval gate rejected: {}", reason)
                        else:
                            logger.info("[VECTOR][training] eval gate passed: {}", reason)
                    except Exception as eval_err:
                        logger.warning("[VECTOR][training] eval gate failed: {}", eval_err)
        except Exception as e:
            logger.error(f"[VECTOR][reflect] SelfImprovementCycle failed: {e}")

        try:
            from core.memory.counterfactual import CounterfactualMemory
            cfm = CounterfactualMemory()
            patterns = cfm.get_rejection_patterns()
            if patterns.get("total_rejections", 0) > 0:
                logger.info(
                    "[VECTOR][reflect] counterfactual: {} rejections, {} outcomes learned, top: {}",
                    patterns["total_rejections"],
                    patterns.get("total_outcomes_learned", 0),
                    (patterns.get("top_rejection_reasons") or [{}])[0].get("reason", "none"),
                )
        except Exception as _cf_err:
            logger.warning("[VECTOR][reflect] CounterfactualMemory reflect failed: {}", _cf_err)

        try:
            from core.city.meta_cognition import MetaCognition
            mc = MetaCognition()
            report = mc.get_monthly_report()
            bias_count = len(report.get("bias_analysis", {}).get("detected_biases", []))
            blind_spots = report.get("new_blind_spots_30d", 0)
            logger.info(
                "[VECTOR][reflect] meta_cognition: {} biases detected, {} new blind spots",
                bias_count, blind_spots,
            )
            mc.close()
        except Exception as _mc_err:
            logger.warning("[VECTOR][reflect] MetaCognition reflect failed: {}", _mc_err)

        # Epistemic decay — age all beliefs so stale information triggers
        # dampening in future decisions (JARVIS Gap 3).
        try:
            decayed = self._get_decision().decay_epistemic()
            if decayed > 0:
                logger.info("[VECTOR][reflect] epistemic decay: {} beliefs aged", decayed)
        except Exception as _ep_err:
            logger.warning("[VECTOR][reflect] epistemic decay failed: {}", _ep_err)

        # Correction lesson maintenance — expire stale unvalidated lessons
        try:
            from core.memory.correction_learner import CorrectionLearner
            _cl = CorrectionLearner()
            _expired = _cl.expire_old_lessons(max_age_days=90)
            _total = len(_cl.list_all_lessons(limit=200))
            if _expired > 0 or _total > 0:
                logger.info(
                    "[VECTOR][reflect] correction_learner: {} active lessons, {} expired",
                    _total, _expired,
                )
        except Exception as _cl_err:
            logger.debug("[VECTOR][reflect] correction learner maintenance suppressed: {}", _cl_err)

        try:
            from scripts.db_backup import run_backup
            result = await asyncio.to_thread(run_backup)
            logger.info(
                "[VECTOR][reflect] db_backup: {} backed up, {} failed",
                len(result["backed"]), len(result["failed"]),
            )
        except Exception as _bk_err:
            logger.warning("[VECTOR][reflect] db_backup failed: {}", _bk_err)

        # 2026-07-30 audit fix (memory subsystem — scheduled forgetting): the
        # real forgetting/prune pass lives in ConsolidationBot.run_forever()
        # (daily reflection + Monday consolidation, which calls
        # EpisodicMemory.prune_old_episodes()), but nothing in the actually
        # running process ever started that loop — cloud/agent_workers/
        # workers.py (which spins it up via run_memory_workers()) is only
        # invoked from its own `if __name__ == "__main__"` block, and
        # START_VECTOR.bat never launches it. Net effect: episodic memory
        # grew unbounded in production; decay math existed but never fired.
        # Fixed by piggybacking on this already-running 2AM reflect tick
        # (same cron slot DailyReviewer/db_backup/etc. already use) instead
        # of introducing yet another background task that could go unstarted
        # the same way. Weekday gate mirrors ConsolidationBot.run_forever()'s
        # own "Monday = weekly consolidation" rule exactly.
        try:
            from districts.memory_curator.consolidation_bot import ConsolidationBot
            _bot = ConsolidationBot()
            _reflected = await _bot.write_daily_reflection()
            _consolidated = 0
            if datetime.datetime.now().weekday() == 0:  # Monday
                _consolidated = await _bot.consolidate_old_episodes()
            logger.info(
                "[VECTOR][reflect] memory forgetting pass: daily_reflection={} "
                "consolidated_episodes={}", _reflected, _consolidated,
            )
        except Exception as _forget_err:
            logger.warning("[VECTOR][reflect] memory forgetting pass failed: {}", _forget_err)

        try:
            from core.city.evolution_engine import EvolutionEngine
            from core.city.agent_registry import get_registry
            registry = get_registry()
            engine   = EvolutionEngine(registry=registry)
            agents   = registry.get_all_agents()
            districts = {getattr(a, "district", None) for a in agents} - {None}
            total_culled: list[str] = []
            for district in districts:
                culled = await engine.cull_bottom(district, keep_top=5)
                total_culled.extend(culled)
            if total_culled:
                logger.info("[VECTOR][reflect] cull_bottom: {} agents culled across {} districts",
                            len(total_culled), len(districts))
            else:
                logger.debug("[VECTOR][reflect] cull_bottom: no agents culled (all districts healthy)")
        except Exception as _cull_err:
            logger.warning("[VECTOR][reflect] cull_bottom failed: {}", _cull_err)

        try:
            # Fallback: at minimum store a log entry
            self._get_memory().store(
                event_type="reflect",
                content=f"2AM reflection fallback — ticks={self._tick_count}",
                tags=["reflect", "daily"],
                source="autonomous_loop",
            )
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        # Avatar on_reflect: advance relationship state + save mood persistence
        try:
            avatar = getattr(self, '_avatar', None)
            if avatar is not None:
                avatar.on_reflect(
                    interaction_summary=f'daily_reflect tick={self._tick_count}',
                    outcome='ok',
                )
        except Exception as _av_ref_err:
            logger.warning('[VECTOR][reflect] avatar on_reflect failed: {}', _av_ref_err)

        # Proactive care check: emit care interventions after each reflect cycle
        try:
            from core.avatar.proactive_care import get_proactive_care
            _care = get_proactive_care()
            _interventions = _care.check()
            for _iv in _interventions:
                logger.info('[VECTOR][reflect] proactive_care {} (sev={:.2f}): {}',
                            _iv.kind, _iv.severity, _iv.message[:80])
                self._notify_user(_iv.message)
        except Exception as _care_err:
            logger.debug('[VECTOR][reflect] proactive_care suppressed: {}', _care_err)

        # Phase 3 — cross-domain synthesis when anomaly severity >= threshold
        try:
            from districts.predictive_analytics.anomaly_predictor import AnomalyPredictor
            from core.brain.synthesis_bridge import SynthesisBridge
            from core.brain.hypothesis_engine import HypothesisEngine
            from core.memory.episodic import EpisodicMemory
            _anomaly_pred = AnomalyPredictor()
            _recent = self._get_memory().get_recent_events(limit=20) if hasattr(self._get_memory(), 'get_recent_events') else []
            _district_outputs = [{'source': e.get('source', 'unknown'), 'content': str(e.get('content', ''))} for e in _recent[:10]]
            if _district_outputs:
                _bridge = SynthesisBridge()
                import asyncio as _asyncio
                _synthesis = await _bridge.synthesize(_district_outputs, synthesis_type='daily_reflect')
                if _synthesis:
                    logger.info('[VECTOR][reflect] cross-domain synthesis ({} chars)', len(_synthesis))
                    self._get_memory().store(
                        event_type='cross_domain_synthesis',
                        content=_synthesis[:500],
                        tags=['synthesis', 'reflect', 'cross_domain'],
                        source='synthesis_bridge',
                    )
        except Exception as _synth_err:
            logger.debug('[VECTOR][reflect] cross-domain synthesis suppressed: {}', _synth_err)

        # Gap 5 — SuggestionQueue: drain top-3 pending hypotheses → HYPOTHESIS_SURFACED event
        try:
            from core.brain.suggestion_queue import SuggestionQueue
            from core.event_bus.types import EventType
            _sq = SuggestionQueue()
            _pending = _sq.get_top_pending(limit=3)
            for _item in _pending:
                await self._publish_event(EventType.HYPOTHESIS_SURFACED, {
                    "id": _item["id"],
                    "hypothesis": _item["hypothesis"],
                    "confidence": _item["confidence"],
                })
                _sq.mark_surfaced(_item["id"])
                logger.info("[VECTOR][reflect] hypothesis surfaced: {}", _item["hypothesis"][:80])
                # Feed the proactive-speech stream: the voice duplex speaks
                # nudges (its own quiet-hours/DND/priority gates apply) and
                # the HUD polls nudge.latest — insights no longer die in the log.
                try:
                    from core.loop.nudge_engine import nudge_engine
                    nudge_engine.push(
                        text=str(_item["hypothesis"])[:280],
                        source="hypothesis",
                        priority=float(_item.get("confidence", 0.7)),
                    )
                except Exception as _ng_err:
                    logger.debug("[VECTOR][reflect] hypothesis nudge push skipped: {}", _ng_err)
            _sq.close()
        except Exception as _sq_err:
            logger.debug("[VECTOR][reflect] SuggestionQueue drain suppressed: {}", _sq_err)

        # Trust ladder weekly digest — Sunday 2AM reflect: what got promoted to
        # auto-execute / demoted this week, so earned autonomy stays visible.
        try:
            if datetime.datetime.now().weekday() == 6:
                from core.loop.trust_ladder import get_trust_ladder
                _changes = get_trust_ladder().recent_changes(days=7)
                if _changes["promoted"] or _changes["demoted"]:
                    _lines = [
                        f"↑ {p['action_type']} now auto-executes" for p in _changes["promoted"]
                    ] + [
                        f"↓ {d['action_type']} demoted ({d['reason']})" for d in _changes["demoted"]
                    ]
                    _msg = ("Trust ladder this week:\n" + "\n".join(_lines[:10]) +
                            f"\nAuto-executed {_changes['total_auto_execs']} trusted actions total."
                            "\nReview: /gateway/trust")
                    self._notify_user(_msg)
                    logger.info("[VECTOR][reflect] trust digest sent ({} promoted, {} demoted)",
                                len(_changes["promoted"]), len(_changes["demoted"]))
        except Exception as _tr_err:
            logger.debug("[VECTOR][reflect] trust digest suppressed: {}", _tr_err)

        # Daily DB backup — runs every 2AM reflect cycle
        try:
            import subprocess
            import sys as _sys
            _backup_script = Path(__file__).parent.parent.parent / "scripts" / "backup_dbs.py"
            if _backup_script.exists():
                result = await asyncio.to_thread(
                    subprocess.run,
                    [_sys.executable, str(_backup_script), "--prune-days", "30"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    logger.info("[VECTOR][reflect] DB backup completed")
                else:
                    logger.warning("[VECTOR][reflect] DB backup exited {}: {}", result.returncode, result.stderr[:200])
        except Exception as _bk_err:
            logger.warning("[VECTOR][reflect] DB backup suppressed: {}", _bk_err)

        # jcode — check if session context is approaching compaction thresholds
        await self._check_session_compact()

    async def _check_session_compact(self) -> None:
        """Check if context needs compacting and notify owner if thresholds exceeded."""
        try:
            from core.jcode.session_persistence import StoredCompactionState, SessionPersistence
            _sp = SessionPersistence()
            _session = getattr(self, '_session', None)
            # Estimate context usage from stored session message count (rough proxy)
            _context_used = 0
            _context_total = 200_000  # default max context window
            if _session is not None:
                _loaded = _sp.load(_session.id)
                if _loaded is not None:
                    _context_used = len(_loaded.messages) * 500  # ~500 tokens/msg average
            _state = StoredCompactionState(summary="runtime_check")
            result = _state.check_compact_needed(
                context_used=float(_context_used),
                context_total=float(_context_total),
            )
            if result == "force":
                self._notify_user(
                    "⚠️ VECTOR context nearly full (95%) — compact recommended"
                )
            elif result == "warn":
                logger.info("[VECTOR][jcode] Context at 80%+ — consider compacting")
        except Exception as e:
            logger.debug("[VECTOR][jcode] compact check skipped: {}", e)

    # ─── Sync ─────────────────────────────────────────────────────────────────

    async def sync_loop(self):
        """Multi-DB mesh reconciliation every db_sync_hours (default 24h). Never crashes."""
        sync_hours = CONFIG["loop"]["db_sync_hours"]
        logger.info(f"[VECTOR][sync] started — {sync_hours}h cloud sync interval")
        while self._running:
            try:
                # Chunked sleep so stop() takes effect immediately
                remaining = sync_hours * 3600
                while self._running and remaining > 0:
                    await asyncio.sleep(min(60.0, remaining))
                    remaining -= 60.0
                if self._running:
                    await self._sync_tick()
            except Exception as e:
                logger.error(f"[VECTOR][sync] error: {e}")
                for _ in range(300):
                    if not self._running:
                        break
                    await asyncio.sleep(1.0)

    async def _sync_tick(self) -> None:
        """24h tick: reconcile the multi-DB mesh, then push heartbeat to brain server."""
        logger.info("[VECTOR][sync] DB sync tick")

        # ── multi-DB mesh reconciliation (local SQLite ↔ Supabase ↔ Turso ↔ D1) ──
        # This is the 24h "databases merge each other" pass. Quarantined backends
        # (Phase 2) are skipped inside sync_all. Never crashes the loop.
        try:
            from core.memory.multi_db_manager import get_manager
            merge = await get_manager().sync_all()
            logger.info(f"[VECTOR][sync] multi-DB merge: {merge}")
        except Exception as e:
            logger.warning(f"[VECTOR][sync] multi-DB merge skipped: {e}")

        # Heartbeat + remote-command draining now run on the fast command-poll
        # loop (command_poll_loop, ~3s) for responsive remote control. The 24h
        # tick is DB-merge only.

    # ─── Remote command relay (fast + safe) ───────────────────────────────────

    async def command_poll_loop(self) -> None:
        """Fast heartbeat + remote-command poll. Keeps the cloud brain warm and
        delivers commands from any device within a few seconds. Never crashes."""
        interval = CONFIG["loop"].get("command_poll_sec", 3.0)
        logger.info(f"[VECTOR][cmd] command_poll_loop started — {interval}s interval")
        while self._running:
            try:
                await self._command_poll_tick()
            except Exception as e:
                logger.warning(f"[VECTOR][cmd] poll error: {e}")
            slept = 0.0
            while self._running and slept < interval:
                await asyncio.sleep(min(1.0, interval - slept))
                slept += 1.0

    async def _command_poll_tick(self) -> None:
        """POST a heartbeat to the cloud brain (Cloudflare Worker) and execute any
        commands it returns. No-ops cleanly until the Worker URL is configured."""
        import os
        import httpx
        brain_url = (CONFIG.get("cloud", {}).get("brain_url") or os.environ.get("VECTOR_BRAIN_URL") or "").rstrip("/")
        if not brain_url:
            return  # cloud relay not configured yet (set VECTOR_BRAIN_URL to the Worker URL)
        # NOTE (2026-07-21): CONFIG["api_keys"] never wires up a "vector_api_key"
        # entry — core/api/auth.py (and the Worker's env.VECTOR_API_KEY) both read
        # the raw VECTOR_API_KEY env var, so this must match or the heartbeat sends
        # no Authorization header at all and the Worker always 401s.
        api_key = os.environ.get("VECTOR_API_KEY", "") or CONFIG.get("api_keys", {}).get("vector_api_key", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload = {
            "uptime_sec": self.uptime_seconds,
            "tick_count": self._tick_count,
            "source": "command_poll",
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.post(f"{brain_url}/heartbeat", json=payload, headers=headers)
                if r.status_code != 200:
                    # Log on status-code CHANGE only — this ticks every ~3s, so an
                    # unconditional warning would flood the log, but swallowing
                    # non-200s hid a rate-limit collision (429s) for weeks.
                    if r.status_code != getattr(self, "_last_hb_status", 200):
                        logger.warning(
                            "[VECTOR][cmd] heartbeat rejected by cloud brain: HTTP {} "
                            "(remote commands stalled until this clears)", r.status_code)
                    self._last_hb_status = r.status_code
                    return
                if getattr(self, "_last_hb_status", 200) != 200:
                    logger.info("[VECTOR][cmd] heartbeat recovered (HTTP 200)")
                self._last_hb_status = 200
                for cmd in (r.json().get("commands") or []):
                    await self._handle_remote_command(cmd)
        except Exception as e:
            logger.debug(f"[VECTOR][cmd] heartbeat/poll failed: {e}")

    async def _handle_remote_command(self, cmd: dict) -> None:
        """Run a remote command through the permission gateway (GREEN/YELLOW/RED).

        Untrusted by origin: text params are prompt-injection scanned, and the
        gateway gates destructive/RED actions (requiring approval) — a remote
        device can never auto-run an unsafe action."""
        cmd_type = (cmd.get("type") or "").strip()
        params = cmd.get("params") or {}
        if not cmd_type:
            return
        # Prompt-injection scan on free-text params (remote input is untrusted)
        for k in ("query", "text", "prompt", "message"):
            v = params.get(k)
            if isinstance(v, str) and v and not _scan_incoming(v, context=f"remote_command.{cmd_type}"):
                logger.critical(f"[VECTOR][cmd] prompt injection in remote '{cmd_type}.{k}' — BLOCKED")
                params[k] = ""
        logger.info(f"[VECTOR][cmd] remote command {cmd.get('id','')} type={cmd_type}")

        # Email-bridge ingress: cloud inbox → brain. HMAC-verified + injection-scanned
        # inside the handler; off unless VECTOR_EMAIL_BRIDGE=1. Not an "action" to
        # gate — it's an inbound event that lands in episodic memory for triage.
        if cmd_type == "email_received":
            try:
                from core.loop.handlers.email_received import handle_email_received
                signature = cmd.get("signature") or params.get("signature") or ""
                await handle_email_received(params, signature=signature)
            except Exception as e:
                logger.error(f"[VECTOR][cmd] email_received handler failed: {e}")
            return

        # Free-text command → run through the FULL local /command pipeline
        # (context → decision → gateway → policy/memory). Reuses the API so we
        # never duplicate the intelligence stack. The gateway gates it there.
        text = params.get("text")
        if cmd_type in ("command", "chat") and isinstance(text, str) and text:
            try:
                import httpx
                port = CONFIG.get("api", {}).get("port", 8000)
                api_key = CONFIG.get("api_keys", {}).get("vector_api_key") or CONFIG.get("vector_api_key", "")
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                async with httpx.AsyncClient(timeout=30.0) as c:
                    await c.post(f"http://127.0.0.1:{port}/command",
                                 json={"text": text, "source": "remote_device"},
                                 headers=headers)
                return
            except Exception as e:
                logger.error(f"[VECTOR][cmd] local /command forward failed: {e}")
                return

        # Structured command → permission gateway (GREEN/YELLOW/RED gating).
        # Must be the SHARED gateway: a fresh instance would hold any pending
        # RED approval in a queue the HUD/API approval endpoints never see.
        try:
            from core.loop.permission_gateway import PermissionGateway, Action
            gw = PermissionGateway.get_shared()
            await gw.execute(Action(
                action_type=cmd_type,
                params=params,
                proposed_by="remote_device",
            ))
        except Exception as e:
            logger.error(f"[VECTOR][cmd] remote command '{cmd_type}' failed: {e}")

    # ─── Obsidian vault watcher ───────────────────────────────────────────────

    async def obsidian_loop(self) -> None:
        """Start vault watcher + bulk ingest at startup. Never crashes."""
        logger.info("[VECTOR][obsidian] loop starting")
        while self._running:
            try:
                from core.memory.obsidian_sync import ObsidianSync
                obs = ObsidianSync()

                if CONFIG.get("obsidian", {}).get("ingest_on_startup", True):
                    try:
                        count = await obs.ingest_existing()
                        logger.info(f"[VECTOR][obsidian] startup ingest: {count} files")
                    except Exception as e:
                        logger.warning(f"[VECTOR][obsidian] startup ingest failed: {e}")

                await obs.start_watching()  # blocks until vault is unavailable
            except Exception as e:
                logger.error("[VECTOR][obsidian] watcher crashed: {} — restarting in 30s", e)
                await asyncio.sleep(30)

    # ─── Phone node poll ──────────────────────────────────────────────────────

    async def phone_loop(self) -> None:
        """Poll phone ambient server every 60s. Graceful if phone disconnected."""
        logger.info("[VECTOR][phone] loop starting")
        while self._running:
            try:
                from phone_node.adb_bridge import poll_loop
                await poll_loop(interval_sec=60)
            except Exception as e:
                logger.error("[VECTOR][phone] loop crashed: {} — restarting in 30s", e)
                await asyncio.sleep(30)

    # ─── Health monitoring cycles ────────────────────────────────────────────

    async def wearable_poll_cycle(self) -> None:
        cfg = CONFIG.get("health", {})
        if not cfg.get("enabled", False):
            return
        interval = cfg.get("wearable_poll_interval_minutes", 15) * 60
        logger.info(f"[VECTOR][health] wearable_poll_cycle started — {interval//60}min interval")
        while self._running:
            try:
                from districts.health.wearable_connector import WearableConnector
                from districts.health.metrics_store import MetricsStore
                connector = WearableConnector()
                store = MetricsStore()
                results = await connector.poll_all()
                for metrics in results:
                    store.store_wearable(metrics.get("source", "unknown"), metrics)
                logger.debug(f"[VECTOR][health] wearable poll: {len(results)} sources")
            except Exception as e:
                logger.warning(f"[VECTOR][health] wearable poll error: {e}")
            for _ in range(interval):
                if not self._running:
                    return
                await asyncio.sleep(1)

    async def health_analysis_cycle(self) -> None:
        cfg = CONFIG.get("health", {})
        if not cfg.get("enabled", False):
            return
        interval = cfg.get("health_analysis_interval_minutes", 60) * 60
        logger.info(f"[VECTOR][health] health_analysis_cycle started — {interval//60}min interval")
        while self._running:
            try:
                from districts.health.trend_analyzer import TrendAnalyzer
                from districts.health.metrics_store import MetricsStore
                from districts.health.health_advisor import HealthAdvisor
                store = MetricsStore()
                analyzer = TrendAnalyzer(store=store)
                analysis = analyzer.full_analysis(days=7)
                for name, trend in analysis.get("trends", {}).items():
                    store.store_trend(trend)
                for name, anomalies in analysis.get("anomalies", {}).items():
                    for a in anomalies:
                        store.store_anomaly(a)
                logger.info(f"[VECTOR][health] analysis complete: {len(analysis.get('trends', {}))} trends, {sum(len(v) for v in analysis.get('anomalies', {}).values())} anomalies")
            except Exception as e:
                logger.warning(f"[VECTOR][health] analysis error: {e}")
            for _ in range(interval):
                if not self._running:
                    return
                await asyncio.sleep(1)

    async def emergency_detection_cycle(self) -> None:
        cfg = CONFIG.get("health", {})
        if not cfg.get("enabled", False):
            return
        interval = cfg.get("emergency_detection_interval_seconds", 60)
        logger.info(f"[VECTOR][health] emergency_detection_cycle started — {interval}s interval")
        while self._running:
            try:
                from districts.health.emergency_detector import HealthEmergencyDetector
                from districts.health.metrics_store import MetricsStore
                store = MetricsStore()
                detector = HealthEmergencyDetector(store=store)
                latest = store.get_latest_wearable()
                if latest:
                    events = detector.check(latest)
                    if events:
                        logger.warning(f"[VECTOR][health] {len(events)} emergency event(s) detected")
            except Exception as e:
                logger.warning(f"[VECTOR][health] emergency detection error: {e}")
            for _ in range(interval):
                if not self._running:
                    return
                await asyncio.sleep(1)

    # ─── VectorCode MCP server ────────────────────────────────────────────────

    async def vectorcode_loop(self) -> None:
        """Start VectorCode MCP server at startup. Restarts if it crashes.

        Uses exponential backoff + a circuit breaker instead of a fixed 5s
        restart: a process that dies fast (<30s uptime) repeatedly means a
        real problem (e.g. port bind conflict) — hammering it every 5s just
        burns CPU in a crash loop. See ~/.vector_ca/logs/mcp_server.log for
        the subprocess's real stderr (previously discarded to DEVNULL).
        """
        # Owner rule (2026-07-16): ONE localhost server only. The MCP tool
        # server (port 9001) is opt-in — it only powers background coding-agent
        # tooling, and VECTOR runs fine without it. Set VECTOR_MCP=1 to enable.
        import os as _os
        if _os.environ.get("VECTOR_MCP", "").strip().lower() in ("", "0", "off", "false", "none"):
            logger.info("[VECTOR][vectorcode] MCP server disabled (single-server mode) — set VECTOR_MCP=1 to enable coding-agent tools")
            return
        logger.info("[VECTOR][vectorcode] loop starting")
        _FAST_FAIL_THRESHOLD_SEC = 30.0
        _BACKOFF_SCHEDULE = [5, 15, 60, 300]  # seconds, indexed by fast-fail count - 1
        _CIRCUIT_BREAKER_LIMIT = 5
        _CIRCUIT_BREAKER_COOLDOWN_SEC = 1800  # 30 min
        consecutive_fast_fails = 0
        while self._running:
            try:
                from districts.coding.vectorcode_bridge import get_bridge
                bridge = get_bridge()
                if not bridge.is_available():
                    logger.warning("[VECTOR][vectorcode] VectorCode not available — skipping MCP server")
                    return
                mcp_port = 9001
                try:
                    from core.config import CONFIG
                    mcp_port = CONFIG.get("vectorcode", {}).get("mcp_port", 9001)
                except Exception:
                    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
                proc = await bridge.start_mcp_server(port=mcp_port)
                if proc:
                    logger.info(f"[VECTOR][vectorcode] MCP server running on port {mcp_port}")
                    # Block until the process exits — without this the loop
                    # re-spawns a new MCP process on every iteration (runaway).
                    start_time = asyncio.get_event_loop().time()
                    try:
                        await asyncio.get_event_loop().run_in_executor(None, proc.wait)
                    except Exception:
                        logger.warning("[VECTOR] silent swallow")
                        pass
                    uptime = asyncio.get_event_loop().time() - start_time
                    if uptime < _FAST_FAIL_THRESHOLD_SEC:
                        consecutive_fast_fails += 1
                    else:
                        consecutive_fast_fails = 0

                    if consecutive_fast_fails >= _CIRCUIT_BREAKER_LIMIT:
                        logger.warning(
                            "[VECTOR][vectorcode] MCP server crash-looping — see "
                            "~/.vector_ca/logs/mcp_server.log; backing off 30 min"
                        )
                        await asyncio.sleep(_CIRCUIT_BREAKER_COOLDOWN_SEC)
                        consecutive_fast_fails = 0
                        continue

                    delay = _BACKOFF_SCHEDULE[
                        min(consecutive_fast_fails, len(_BACKOFF_SCHEDULE)) - 1
                    ] if consecutive_fast_fails > 0 else _BACKOFF_SCHEDULE[0]
                    logger.info(
                        f"[VECTOR][vectorcode] MCP server exited after {uptime:.1f}s — "
                        f"restarting in {delay}s (consecutive fast fails={consecutive_fast_fails})"
                    )
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(30)
            except Exception as e:
                logger.error("[VECTOR][vectorcode] loop crashed: {} — restarting in 10s", e)
                await asyncio.sleep(10)

    # NOTE: emergency_loop was removed 2026-07-15 — it was never launched by
    # run_forever (dead code); emergency_detection_cycle is the live path.

    # ─── Main entry ───────────────────────────────────────────────────────────

    # ── running-loop singleton ────────────────────────────────────────────────
    # API routers (core/api/tasks.py, routers/tasks.py) need the RUNNING loop
    # to inject voice intents. Constructing AutonomousLoop() gives a fresh,
    # disconnected instance — get_instance() returns the one inside
    # run_forever(), or None when the loop isn't running.
    _instance = None

    @classmethod
    def get_instance(cls):
        return cls._instance

    async def wake_think(self) -> None:
        """Trigger an immediate think tick (event-driven — kills the 10s poll
        latency for injected voice intents). Busy-guarded so an event burst
        can't stack concurrent ticks on top of the scheduled one."""
        if getattr(self, "_think_busy", False):
            return
        self._think_busy = True
        try:
            await self._think_tick()
        except Exception as e:
            _capture_loop_error(e, "wake_think")
        finally:
            self._think_busy = False

    async def run_forever(self) -> None:
        """
        RULE 2 — Never returns in production.
        return_exceptions=True ensures one crashed coroutine doesn't kill others.
        """
        self._running = True
        AutonomousLoop._instance = self
        self._start_time = datetime.datetime.now(datetime.timezone.utc)
        logger.info(
            f"[VECTOR][autonomous_loop] run_forever() at {self._start_time.isoformat()}"
        )
        try:
            from core.loop import loop_state as _ls
            _ls.update_runtime(tick_count=0, running=True, start_time=self._start_time.isoformat())
        except Exception as e:
            logger.debug("[VECTOR][autonomous_loop] loop_state init skipped: {}", e)

        try:
            from core.loop.task_queue import TaskQueue
            TaskQueue.get()
            logger.info("[VECTOR][autonomous_loop] task_queue ready")
        except Exception as e:
            logger.warning(f"[VECTOR][autonomous_loop] task_queue init failed: {e}")

        eb_cfg = CONFIG.get("event_bus", {})
        if eb_cfg.get("enabled", True):
            try:
                from core.event_bus.bus import get_event_bus
                self._event_bus = await get_event_bus(max_queue_size=eb_cfg.get("max_queue_size", 1000))
                self._worker_pool = WorkerPool(
                    max_workers=eb_cfg.get("worker_pool_size", 4),
                    name="autonomous_loop"
                )
                logger.info("[VECTOR][autonomous_loop] event_bus + worker_pool ready")
            except Exception as e:
                logger.warning(f"[VECTOR][autonomous_loop] event_bus init failed: {e}")

        # Wire absorbed modules: traces, operators, daemon
        try:
            from vectorcode.src.vc_traces.collector import TraceCollector
            self._trace_collector = TraceCollector()
        except Exception:
            self._trace_collector = None
        try:
            from vectorcode.src.operators.manager import OperatorManager
            self._operator_mgr = OperatorManager()
        except Exception:
            self._operator_mgr = None
        try:
            from vectorcode.src.daemon.service import ServiceManager
            self._daemon_mgr = ServiceManager()
        except Exception:
            self._daemon_mgr = None

        # ── Agent-to-Agent event fan-out handler ──────────────────────────
        try:
            from core.event_bus.base import Subscription
            from core.event_bus.types import Event
            from core.city.agent_registry import AgentRegistry
            from core.loop.context_engine import ContextEngine
            bus = await self._get_event_bus()
            self._fanout_sub = bus.subscribe(None, self._fanout_handler)
            logger.info("[VECTOR][autonomous_loop] event fan-out subscriber registered")
            # DB guardian: auto-quarantine the cloud mesh on a security threat.
            try:
                from core.memory.db_guardian import install_db_guardian
                await install_db_guardian(bus)
            except Exception as _ge:
                logger.warning(f"[VECTOR][autonomous_loop] db_guardian install failed: {_ge}")
        except Exception as e:
            self._fanout_sub = None
            logger.warning(f"[VECTOR][autonomous_loop] event fan-out init failed: {e}")

        # ── AmbientScheduler: recover any crashed sessions from prior run ──────
        try:
            from core.jcode.session_persistence import SessionPersistence
            _store = SessionPersistence()
            crashed = _store.recover_crashed_sessions()
            if crashed:
                logger.warning(
                    "[VECTOR][autonomous_loop] {} crashed session(s) recovered — "
                    "context available in ~/.vector_ca/sessions/",
                    len(crashed),
                )
            # Register this run as a new persisted session
            self._session = _store.create(
                model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                working_dir=str(Path(__file__).parent.parent.parent),
            )
            logger.info("[VECTOR][autonomous_loop] session persisted: {}", self._session.id[:8])
        except Exception as e:
            logger.debug("[VECTOR][autonomous_loop] session persistence skipped: {}", e)
            self._session = None

        # Restore agent HP from last checkpoint
        try:
            from core.loop.loop_state import restore_agent_hp, load_decision
            from core.city.agent_registry import get_registry
            restored = restore_agent_hp(get_registry())
            last = load_decision()
            if last:
                logger.info(
                    "[VECTOR][loop_state] last decision: {} score={:.3f} at {}",
                    last.get("action_type"), last.get("score", 0), last.get("ts", "?")[:19],
                )
        except Exception as _ls_err:
            logger.debug("[VECTOR][loop_state] restore skipped: {}", _ls_err)

        # Avatar layer — warm up singleton so governor reuses the same instance
        try:
            from core.avatar.avatar_core import AvatarCore
            self._avatar = AvatarCore.get_instance()
            logger.info("[VECTOR][autonomous_loop] AvatarCore ready — mood={}", self._avatar.state.mood_label)
        except Exception as _av_err:
            self._avatar = None
            logger.warning("[VECTOR][autonomous_loop] AvatarCore init failed: {}", _av_err)

        # Every coroutine runs under a supervisor (RULE 2: log → back off →
        # restart). Bare gather(return_exceptions=True) merely COLLECTED an
        # escaped exception — the coroutine stayed dead, silently, forever.
        loops: list[tuple[str, Callable]] = [
            ("observe", self.observe_loop),
            ("think", self.think_loop),
            ("reflect", self.reflect_loop),
            ("sync", self.sync_loop),
            ("obsidian", self.obsidian_loop),
            ("phone", self.phone_loop),
            ("vectorcode", self.vectorcode_loop),
            ("scheduler", self.scheduler_loop),
            ("ambient_scheduler", self.ambient_scheduler_loop),
            ("hypothesis", self.hypothesis_loop),
            ("predict", self.predict_cycle),
            ("degradation", self.degradation_monitor),
            ("wearable", self.wearable_poll_cycle),
            ("health_analysis", self.health_analysis_cycle),
            ("emergency_detection", self.emergency_detection_cycle),
            ("research", self.research_loop),
            ("state_checkpoint", self.state_checkpoint_loop),
            ("sense", self.sense_loop),
            ("anticipation", self.anticipation_loop),
            ("command_poll", self.command_poll_loop),
            ("growth", self.growth_loop),
        ]
        await asyncio.gather(
            *(self._supervised(name, fn) for name, fn in loops),
            return_exceptions=True,
        )

    async def _supervised(self, name: str, coro_fn: Callable) -> None:
        """Restart wrapper for one eternal coroutine.

        A coroutine that RETURNS did so deliberately (feature disabled in
        config, or _running=False shutdown) — never restarted. An exception
        that escapes the coroutine's own guards (typically a setup line
        before its while-loop) restarts it with exponential backoff, capped
        at 5 minutes, so one bad init can no longer kill a subsystem for the
        life of the process without a trace.
        """
        backoff = 5.0
        while True:
            try:
                await coro_fn()
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _capture_loop_error(e, f"supervisor:{name}")
                if not self._running:
                    return
                logger.warning(
                    "[VECTOR][supervisor] {} loop died ({}: {}) — restarting in {:.0f}s",
                    name, type(e).__name__, e, backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 300.0)

    async def growth_loop(self) -> None:
        """Launch the Growth Engine orchestrator (ARM A content + ARM B software).
        No-ops unless CONFIG.growth.enabled (default False). Self-gates and never
        crashes the autonomous loop (RULE 2 never-die)."""
        try:
            if not CONFIG.get("growth", {}).get("enabled", False):
                logger.info("[VECTOR][growth] disabled (CONFIG.growth.enabled=False) — growth_loop idle")
                return
            from districts.growth.growth_orchestrator import GrowthOrchestrator
            logger.info("[VECTOR][growth] launching orchestrator from autonomous loop")
            await GrowthOrchestrator().run_forever()
        except Exception as _ge:
            logger.error("[VECTOR][growth] growth_loop error (loop survives): {}", _ge)

    async def sense_loop(self) -> None:
        """Call _sense_tick() every 30s. Skipped when sensing disabled. Never crashes."""
        _sense_interval = 30.0
        logger.info("[VECTOR][sense] sense_loop started — 30s interval")
        while self._running:
            try:
                await self._sense_tick()
            except Exception as _se:
                logger.error("[VECTOR][sense] sense_loop error: {}", _se)
            await asyncio.sleep(_sense_interval)

    async def _sense_tick(self) -> None:
        """Capture screen and camera state; write to context_engine sense cache."""
        sensing_cfg = CONFIG.get("sensing", {})
        screen_enabled = sensing_cfg.get("screen_enabled", False)
        camera_enabled = sensing_cfg.get("camera_enabled", False)
        phone_enabled = sensing_cfg.get("phone_enabled", False)
        wearable_enabled = sensing_cfg.get("wearable_enabled", False)

        if not screen_enabled and not camera_enabled and not phone_enabled and not wearable_enabled:
            return

        screen_summary = ""
        presence = "unknown"
        owner_identity = ""
        fatigue_score = 0.0

        if screen_enabled:
            try:
                from core.sensing.screen_observer import ScreenObserver
                obs_result = await asyncio.to_thread(ScreenObserver().observe)
                snippet = obs_result.get("text_snippet", "")
                activity = obs_result.get("activity", "unknown")
                window = obs_result.get("window", "")
                # Always include the foreground window title so VECTOR knows what
                # the owner is doing even when OCR is off (Tesseract not
                # installed) — otherwise screen_summary was just "[idle]"
                # (2026-07-17).
                _win = f" in {window}" if window else ""
                screen_summary = (f"[{activity}]{_win} {snippet[:180]}".rstrip()
                                  if snippet else f"[{activity}]{_win}")

                # Coding Companion — proactive stuck detection. Armed whenever
                # the owner has a live vectorcode CLI session (marker file) or
                # the screen shows coding/terminal activity.
                if sensing_cfg.get("stuck_detection_enabled", True):
                    try:
                        from core.sensing.stuck_detector import (
                            get_stuck_detector, get_active_session)
                        _vc_session = get_active_session()
                        if _vc_session is not None:
                            # Visible to the context engine / hydration prompt.
                            screen_summary = (
                                f"[owner-coding:{_vc_session.get('project', '?')}] "
                                + screen_summary)
                        if _vc_session is not None or activity == "coding":
                            _stuck = get_stuck_detector().feed(
                                obs_result.get("raw_text", snippet), activity)
                            if _stuck:
                                self._tracked_task(
                                    self._coding_companion_nudge(_stuck, _vc_session),
                                    "coding_nudge",
                                )
                    except Exception as _cc_err:
                        logger.debug("[VECTOR][sense] stuck detection skipped: {}", _cc_err)
            except Exception as _se:
                logger.debug("[VECTOR][sense] screen observe failed: {}", _se)

        face_detected = False
        if camera_enabled:
            try:
                from core.sensing.camera import FaceDetector
                faces = await asyncio.to_thread(FaceDetector().capture_and_scan)
                if not faces:
                    presence = "absent"
                else:
                    face_detected = True
                    owner_faces = [f for f in faces if f.get("name", "unknown") != "unknown"]
                    if len(faces) > 1:
                        presence = "multiple"
                    elif owner_faces:
                        presence = "present"
                        owner_identity = owner_faces[0].get("name", "")
                    else:
                        presence = "unknown_visitor"
            except Exception as _ce:
                logger.debug("[VECTOR][sense] camera scan failed: {}", _ce)

            # Task B.1 (governor-wiring-and-ambient-perception.md): health_monitor.py
            # computes a real EAR-based fatigue score, but nothing ever called it
            # from the loop — context_engine read a permanent 0.0 default despite
            # its own docstring claiming FaceDetector wrote face.fatigue (it never
            # did). Only score fatigue when a face was actually seen this tick.
            if face_detected:
                try:
                    from core.sensing.health_monitor import HealthMonitor
                    fatigue_score = await asyncio.to_thread(HealthMonitor().get_fatigue_score)
                except Exception as _fe:
                    logger.debug("[VECTOR][sense] fatigue scoring failed: {}", _fe)

        # Task B.2 (governor-wiring-and-ambient-perception.md): ADB-phone
        # observe source. PhoneController already exists and degrades
        # gracefully with no device (is_connected()=False,
        # get_notifications()=[]) — it just was never polled from the loop.
        phone_connected = False
        phone_notifications: list[dict] = []
        if phone_enabled:
            try:
                from core.control.phone_controller import PhoneController

                def _poll_phone():
                    pc = PhoneController()
                    return pc.is_connected(), pc.get_notifications()

                phone_connected, phone_notifications = await asyncio.to_thread(_poll_phone)
            except Exception as _pe:
                logger.debug("[VECTOR][sense] phone poll failed: {}", _pe)

        # Task B.3 (governor-wiring-and-ambient-perception.md): wearable
        # (HR/sleep/steps) observe source. Architecture docs name it as a
        # core observe source; districts/health/wearable_connector.py
        # already exists and degrades gracefully (available=False) with no
        # sources configured — it just was never polled from the loop.
        # poll_all() is itself async, so call it directly (no to_thread) —
        # HealthMonitor._get_wearable_data() explicitly defers to this path
        # for async callers to avoid its own asyncio.run()-in-running-loop guard.
        wearable_data: dict = {"available": False, "note": "wearable disabled"}
        if wearable_enabled:
            try:
                from districts.health.wearable_connector import WearableConnector
                connector = WearableConnector()
                results = await connector.poll_all()
                wearable_data = (
                    {"available": True, "data": results}
                    if results
                    else {"available": False, "note": "wearable poll returned empty"}
                )
            except Exception as _we:
                logger.debug("[VECTOR][sense] wearable poll failed: {}", _we)
                wearable_data = {"available": False, "note": "wearable unavailable"}

        from core.loop.context_engine import update_sense_cache
        update_sense_cache(
            screen_summary=screen_summary,
            presence=presence,
            face={"detected": face_detected, "identity": owner_identity, "fatigue": fatigue_score},
            phone={
                "connected": phone_connected,
                "notification_count": len(phone_notifications),
                "recent": phone_notifications[:5],
            },
            wearable=wearable_data,
        )
        logger.debug(
            "[VECTOR][sense] tick — presence={} screen_chars={} fatigue={} phone_connected={} wearable_available={}",
            presence, len(screen_summary), fatigue_score, phone_connected, wearable_data.get("available"),
        )

        # Vision → action: react to presence changes
        last_presence = getattr(self, "_last_presence", "unknown")
        if presence != last_presence:
            await self._on_presence_change(last_presence, presence)
            self._last_presence = presence

    async def _coding_companion_nudge(self, stuck: dict, session: dict | None) -> None:
        """Owner is stuck on the same error — proactively offer one concrete
        suggestion (spoken via the voice duplex if live, always on the HUD).
        Advice comes from vector-focus (resident model, think=False); if the
        LLM is unavailable the nudge still fires with the observation alone."""
        try:
            error_text = "\n".join(stuck.get("error_lines", []))[:600]
            # Screen OCR can contain anything — scrub keys/tokens/PII before
            # the text can leave the machine via a cloud provider.
            try:
                from core.browser.pii_scrub import scrub_text
                error_text = scrub_text(error_text).text
            except Exception as _scrub_err:
                logger.debug("[VECTOR][companion] pii scrub unavailable: {}", _scrub_err)
            project = (session or {}).get("project", "")
            advice = ""
            try:
                prompt = (
                    "The owner has been staring at the same error for "
                    f"{stuck.get('since_min')} minutes"
                    + (f" while working in {project}" if project else "")
                    + ". Screen OCR of the error (may be noisy):\n"
                    f"{error_text}\n\n"
                    "Give ONE short, concrete suggestion (2-3 sentences max) for "
                    "what to try next. No preamble."
                )
                # provider_client, not direct Ollama: route_policy sends this
                # cloud-first (owner's API keys) with local fallback — exactly
                # right here, since hitting local focus would evict the owner's
                # coding model from the shared GPU mid-session.
                from core.inference.provider_client import get_client
                _res = await get_client().chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=220,
                    caller_id="coding_companion",
                    district="coding",
                )
                advice = (_res.content or "").strip()
                if advice:
                    logger.debug("[VECTOR][companion] advice from {} ({})",
                                 _res.provider, _res.model)
            except Exception as _llm_err:
                logger.debug("[VECTOR][companion] advice LLM failed: {}", _llm_err)
            text = (
                f"You've hit the same error for {stuck.get('since_min')} minutes. "
                + (advice if advice else "Want me to take a look?")
            )[:500]
            from core.loop.nudge_engine import nudge_engine
            nudge_engine.push(text=text, source="coding_companion",
                              need="unstick", priority=0.85)
            logger.info("[VECTOR][companion] proactive nudge sent ({} chars advice)",
                        len(advice))
        except Exception as e:
            logger.debug("[VECTOR][companion] nudge failed: {}", e)

    async def _on_presence_change(self, prev: str, current: str) -> None:
        """Trigger proactive behaviour when the owner arrives or leaves frame."""
        try:
            from core.loop.decision_engine import Candidate
            # Owner returned after being away → surface a welcome-back brief
            if current == "present" and prev in ("absent", "unknown"):
                logger.info("[VECTOR][sense] owner returned — surfacing welcome-back brief")
                await self._act_on(Candidate(
                    action_type="proactive_welcome_back",
                    params={
                        "need": "welcome_back",
                        "description": "Welcome back. Want a quick brief on what changed while you were away?",
                    },
                    goal_ids=[],
                    urgency=0.7,
                    confidence=0.8,
                    source="vision_presence",
                ))
            # Owner left frame → log only (do not act; avoids noise)
            elif current == "absent" and prev in ("present", "multiple"):
                logger.info("[VECTOR][sense] owner left frame — pausing proactive nudges")
        except Exception as _pc_err:
            logger.debug("[VECTOR][sense] presence-change handler skipped: {}", _pc_err)

    async def state_checkpoint_loop(self) -> None:
        """Save agent HP snapshot to semantic_memory every 60 s for crash recovery."""
        logger.info("[VECTOR][loop_state] checkpoint loop started — 60s interval")
        while self._running:
            try:
                await asyncio.sleep(60)
                from core.loop.loop_state import save_agent_hp
                from core.city.agent_registry import get_registry
                save_agent_hp(get_registry())
                logger.debug("[VECTOR][loop_state] agent HP snapshot saved")
            except Exception as e:
                logger.debug("[VECTOR][loop_state] checkpoint error: {}", e)

    async def degradation_monitor(self) -> None:
        logger.info("[VECTOR][degradation] monitor started — 30s check cycle")
        while self._running:
            try:
                await asyncio.sleep(30)
                old_tier = self._degradation.current_tier
                await self._degradation.auto_degrade()
                await self._degradation.auto_escalate()
                new_tier = self._degradation.current_tier
                if old_tier != new_tier:
                    logger.warning("[VECTOR][degradation] tier changed: {} -> {}", old_tier.name, new_tier.name)
            except Exception as e:
                logger.debug("[VECTOR][degradation] monitor error: {}", e)

    async def ambient_scheduler_loop(self) -> None:
        """
        AmbientScheduler: polls for due directives every 60s and dispatches them.
        Directives are persistent tasks added by agents or the owner that should
        run at a specific time (e.g. 'research LLM papers at 22:00').
        RULE 2 — never dies.
        """
        logger.info("[VECTOR][autonomous_loop] ambient_scheduler_loop starting — 60s poll")
        while self._running:
            try:
                await asyncio.sleep(60)
                if not self._running:
                    break
                from core.jcode.ambient_scheduler import AmbientScheduler, AmbientStatus
                sched = AmbientScheduler()
                due = sched.take_due_items()
                if due:
                    sched.set_status(AmbientStatus.RUNNING, detail=f"{len(due)} item(s) processing")
                    for item in due:
                        context = item.context if hasattr(item, "context") else str(item.get("context", ""))
                        logger.info("[VECTOR][ambient] firing due item: {}", context[:80])
                        # Dispatch to governor as a think task
                        try:
                            from core.city.governor import Governor
                            gov = Governor()
                            await gov.dispatch({
                                "type": "think",
                                "params": {"content": context, "source": "ambient_scheduler"},
                            })
                        except Exception as dispatch_err:
                            logger.warning("[VECTOR][ambient] dispatch failed: {}", dispatch_err)
                    sched.set_status(AmbientStatus.IDLE)

                # Also fire pending directives
                directives = sched.take_pending_directives()
                for d in directives:
                    text = d.get("text", "")
                    if text:
                        logger.info("[VECTOR][ambient] directive: {}", text[:80])
                        self._get_memory().store(
                            event_type="ambient_directive",
                            content=text,
                            tags=["ambient", "directive"],
                            source="ambient_scheduler",
                        )
            except Exception as e:
                _capture_loop_error(e, "ambient_scheduler_loop")
                await asyncio.sleep(60)

    async def hypothesis_loop(self) -> None:
        """
        VECTOR Gap 5 — HypothesisEngine: proactive insight generation.
        Runs every 4 hours. Only surfaces insights with confidence > 0.85.
        RULE 2 — never dies: all exceptions caught, loop always restarts.
        """
        logger.info("[VECTOR][autonomous_loop] hypothesis_loop starting — fires every 4h")
        while self._running:
            try:
                await asyncio.sleep(4 * 3600)
                if not self._running:
                    break
                engine = self._get_hypothesis_engine()
                if engine is None:
                    continue
                context = self._get_context().get_world_state()
                # ContextEngine.get_world_state() always returns a dict (its
                # declared -> dict return type, and every other of its 6+
                # callers — decision_engine.py, planner.py, chief_of_staff.py,
                # etc. — treat it as one via dict access). HypothesisEngine.
                # generate_hypotheses(observation: str) is consistently
                # string-typed instead: its own signature, its prompt
                # template, its observation[:50] logging slice, and every
                # OTHER caller (t06_proactive_cognition.py, this module's own
                # __main__ self-test) all pass a plain string. Convert here,
                # at the boundary closest to the mismatch, using the same
                # str(world_state)[:500] convention
                # districts/chief_of_staff/subconscious_loop.py already uses
                # to turn get_world_state()'s dict into LLM-prompt text — no
                # new serialization format introduced. See
                # VECTOR_TECHNICAL_KNOWLEDGE/56_HYPOTHESIS_OBSERVATION_
                # CONTRACT.md.
                observation = str(context)[:500]
                hypotheses = await engine.generate_hypotheses(observation)
                if not hypotheses:
                    continue
                for h in hypotheses if isinstance(hypotheses, list) else [hypotheses]:
                    confidence = h.get("confidence", 0.0) if isinstance(h, dict) else 0.0
                    if confidence >= 0.85:
                        # HypothesisEngine.generate_hypotheses() returns the
                        # generated text under the "text" key (see
                        # core/brain/hypothesis_engine.py) — that is the
                        # established field name (also read internally by the
                        # engine's own SuggestionQueue enqueue call and its
                        # __main__ self-test). "hypothesis" was never a real
                        # key on this dict, so this branch always fell
                        # through to str(h) before this fix. See
                        # VECTOR_TECHNICAL_KNOWLEDGE/55_HYPOTHESIS_PIPELINE_
                        # REMEDIATION.md.
                        content = h.get("text", str(h)) if isinstance(h, dict) else str(h)
                        logger.info(f"[VECTOR][hypothesis] High-confidence insight (conf={confidence:.2f}): {content[:120]}")
                        self._get_memory().store(
                            event_type="hypothesis",
                            content=content,
                            tags=["hypothesis", "proactive"],
                            context={"confidence": confidence},
                            source="hypothesis_engine",
                        )
                    else:
                        logger.debug(f"[VECTOR][hypothesis] Low-confidence insight suppressed (conf={confidence:.2f})")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[VECTOR][hypothesis] loop error: {e}")
                await asyncio.sleep(300)

    async def predict_cycle(self) -> None:
        cfg = CONFIG.get("predictive_analytics", {})
        if not cfg.get("enabled", False):
            logger.info("[VECTOR][predict_cycle] disabled in config")
            return
        pred_interval = cfg.get("forecast_interval_minutes", 15)
        sim_interval = cfg.get("simulation_interval_minutes", 60)
        logger.info(
            f"[VECTOR][predict_cycle] started — forecast every {pred_interval}min, sim every {sim_interval}min"
        )
        last_sim = datetime.datetime.now(datetime.timezone.utc)
        while self._running:
            try:
                forecast_start = datetime.datetime.now(datetime.timezone.utc)
                from districts.predictive_analytics.time_series_forecaster import TimeSeriesForecaster
                from districts.predictive_analytics.anomaly_predictor import AnomalyPredictor
                from districts.predictive_analytics.strategy_recommender import StrategyRecommender
                from districts.predictive_analytics.prediction_store import PredictionStore

                tf = TimeSeriesForecaster()
                ap = AnomalyPredictor()
                sr = StrategyRecommender()
                ps = PredictionStore()

                predictions = tf.forecast_all()
                for metric_name, forecast_result in predictions.items():
                    forecast_id = ps.store_forecast(forecast_result)
                    if forecast_result.values:
                        anomalies = ap.analyze(forecast_result, forecast_result.values)
                        for anomaly in anomalies:
                            ps.store_anomaly(anomaly)

                all_anomalies = []
                for _metric, forecast_result in predictions.items():
                    if forecast_result.values:
                        all_anomalies.extend(
                            ap.analyze(forecast_result, forecast_result.values)
                        )

                elapsed = (datetime.datetime.now(datetime.timezone.utc) - forecast_start).total_seconds()
                logger.info(f"[VECTOR][predict_cycle] forecast cycle: {len(predictions)} metrics in {elapsed:.1f}s")

                simulations = []
                now = datetime.datetime.now(datetime.timezone.utc)
                sim_elapsed = (now - last_sim).total_seconds()
                if sim_elapsed >= sim_interval * 60:
                    last_sim = now
                    from districts.predictive_analytics.causal_simulator import CausalSimulator
                    cs = CausalSimulator()
                    scenarios = cs.suggest_scenarios()
                    for scenario in scenarios[:3]:
                        sim_result = cs.run_monte_carlo(
                            scenario["name"], scenario, iterations=500
                        )
                        simulations.append(sim_result)
                        ps.store_simulation(sim_result)
                    logger.info(f"[VECTOR][predict_cycle] simulation cycle: {len(simulations)} scenarios")

                all_recs = sr.generate_all(predictions, all_anomalies, simulations)
                for rec in all_recs:
                    ps.store_recommendation(rec)

                ps.prune_old_records(days=cfg.get("retention_days", 90))

            except Exception as e:
                _capture_loop_error(e, "predict_cycle")
                logger.error(f"[VECTOR][predict_cycle] error: {e}")

            await asyncio.sleep(pred_interval * 60)

    async def research_loop(self) -> None:
        """SPEC-10 scheduled research — fires at research_lab.schedule_interval_hours."""
        cfg = CONFIG.get("research_lab", {})
        if not cfg.get("enabled", False):
            logger.info("[VECTOR][research] research_lab disabled — research_loop skipped")
            return
        interval = cfg.get("schedule_interval_hours", 6)
        logger.info("[VECTOR][research] research_loop started — fires every {}h", interval)
        while self._running:
            try:
                await asyncio.sleep(interval * 3600)
                if not self._running:
                    break
                from core.research_engine.auto_research_agent import AutoResearchAgent
                agent = AutoResearchAgent()
                topics = ["recent advances in AI agents", "LLM benchmark performance trends"]
                for topic in topics:
                    logger.info("[VECTOR][research] running scheduled research on: {}", topic)
                    report = agent.run_full_cycle(topic)
                    logger.info("[VECTOR][research] report complete: {}", report.sections.get("title", "?") if report.sections else "?")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[VECTOR][research] loop error: {e}")
                await asyncio.sleep(300)

    # ── Anticipation loop (C3) ────────────────────────────────────────────────

    async def anticipation_loop(self) -> None:
        """
        C3 — AnticipationEngine: predict what the owner needs next.
        Runs every 10 minutes. High-confidence predictions (>= 0.75) are
        proposed as proactive_* actions through the normal _act_on flow.
        RULE 2 — never dies.
        """
        logger.info("[VECTOR][anticipation] loop starting — 10min cycle")
        while self._running:
            try:
                await asyncio.sleep(600)
                if not self._running:
                    break
                await self._anticipation_tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[VECTOR][anticipation] loop error: {}", e)
                await asyncio.sleep(60)

    async def _anticipation_tick(self) -> None:
        """Predict next need and route high-confidence predictions as proactive_* candidates."""
        try:
            from core.brain.anticipation import get_anticipation_engine
            from core.loop.decision_engine import Candidate
            engine = get_anticipation_engine()
            predictions = engine.predict_next_need(window_minutes=30)
            for pred in predictions:
                if pred.confidence >= 0.75:
                    candidate = Candidate(
                        action_type=pred.action_type,
                        params={"need": pred.need, "description": pred.description, **pred.params},
                        goal_ids=[],
                        urgency=pred.confidence,
                        confidence=pred.confidence,
                        source="anticipation_engine",
                    )
                    logger.info(
                        "[VECTOR][anticipation] proactive action: {} conf={:.2f} ({})",
                        pred.action_type, pred.confidence, pred.source,
                    )
                    await self._act_on(candidate)
        except Exception as e:
            logger.debug("[VECTOR][anticipation] tick skipped: {}", e)

    def active_task_count(self) -> int:
        """Return the number of in-flight act_loop tasks. Used by graceful shutdown."""
        return self._active_task_count

    def stop(self) -> None:
        """Graceful stop — cleans up worker pool, scheduler, and background tasks."""
        self._running = False
        # Cancel tracked background tasks
        bg_tasks = getattr(self, "_background_tasks", set())
        for task in list(bg_tasks):
            if not task.done():
                task.cancel()
        bg_tasks.clear()
        # Shutdown worker pool (async — schedule if we're in a running loop)
        if self._worker_pool is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._worker_pool.shutdown(wait=False))
            except RuntimeError:
                pass  # no running loop — pool will be GC'd
        # Shutdown APScheduler
        if getattr(self, "_callable_scheduler", None) is not None:
            try:
                self._callable_scheduler.shutdown(wait=False)
            except Exception:
                pass
        logger.info("[VECTOR][autonomous_loop] stopped (cleanup complete)")

    @property
    def uptime_seconds(self) -> int:
        if self._start_time is None:
            return 0
        return int((datetime.datetime.now(datetime.timezone.utc) - self._start_time).total_seconds())


async def _smoke_test() -> dict:
    """Bounded, isolated self-test (P0-A remediation — M1c/M1d, 2026-09-09).

    The previous version of this self-test called the REAL
    AutonomousLoop.run_forever() for 2 real seconds against real, unisolated
    GoalSystem/PolicyMemory/EpisodicMemory/Governor/PermissionGateway
    instances -- think_loop()'s immediate first tick would construct a real
    GoalSystem and could produce a real winning candidate, meaning a real
    GREEN-tier action (real district dispatch, real LLM calls) could
    genuinely execute within that window. See
    VECTOR_TECHNICAL_KNOWLEDGE/M1c_DEVELOPMENT_TEST_ISOLATION_SAFETY_AUDIT.md
    (finding P0-A) and M1d_DEVELOPMENT_TEST_SAFETY_REMEDIATION.md for the
    full incident/remediation history.

    This version never calls run_forever()/observe_loop()/think_loop() --
    the real tick methods are exactly what touched real stores and could
    execute a real action, so this self-test does not exercise them at all
    (per the "prefer a bounded isolated test over a real run_forever() path"
    principle). It instead proves two things a REAL run would have to be
    true for it to be a valid smoke test:
      (1) construction is genuinely lazy -- __init__ does not eagerly touch
          any real persistent store (every lazy-getter-backed attribute is
          still None right after AutonomousLoop()), and start/stop toggles
          `_running` cleanly with no tick ever invoked;
      (2) the actual safety boundary this self-test exists to protect --
          _act_on() genuinely stops a RED-classified candidate before any
          execution bridge -- using a fully stubbed PermissionGateway. This
          reuses the exact pattern already proven in
          tests/test_r11_end_to_end_trace.py rather than reinventing it.
    """
    loop = AutonomousLoop()

    # (1) No real persistent store may be eagerly constructed at __init__.
    _lazy_attrs = (
        "_context_engine", "_goal_system", "_decision_engine", "_governor",
        "_gateway", "_policy", "_memory", "_red_team", "_hypothesis_engine",
        "_ambient", "_event_bus", "_worker_pool",
    )
    for _attr in _lazy_attrs:
        actual = getattr(loop, _attr, None)
        if actual is not None:
            raise AssertionError(
                f"AutonomousLoop() eagerly constructed self.{_attr} = {actual!r} "
                "at __init__ -- this self-test's isolation assumption no longer "
                "holds; refusing to proceed rather than risk touching real state."
            )

    assert loop._running is False
    loop._running = True   # toggled directly -- no real tick method invoked
    loop.stop()
    assert loop._running is False

    # (2) Prove a RED candidate genuinely stops before the execution bridge,
    # with the real _act_on() code path but a fully stubbed gateway/bridge --
    # no real GoalSystem/PolicyMemory/EpisodicMemory/Governor construction,
    # no real LLM call, no real district dispatch.
    from unittest.mock import AsyncMock, MagicMock
    from core.loop.decision_engine import Candidate

    fake_gateway = MagicMock()
    fake_gateway.classify = MagicMock(return_value="RED")
    denied_result = MagicMock()
    denied_result.approved = False
    denied_result.reason = "M1d smoke test -- no real approval requested"
    fake_gateway.execute = AsyncMock(return_value=denied_result)
    loop._gateway = fake_gateway

    bridge_reached = {"value": False}

    class _BridgeGuard:
        def is_available(self):
            bridge_reached["value"] = True  # would only be reached past the gate
            return False

    import districts.coding.vectorcode_bridge as vcb
    original_get_bridge = vcb.get_bridge
    vcb.get_bridge = lambda: _BridgeGuard()
    try:
        red_candidate = Candidate(
            action_type="code_task",
            params={"probe": "M1d smoke test — never executed for real"},
            goal_ids=[],
            urgency=0.5,
            confidence=0.5,
            source="smoke_test",
        )
        await loop._act_on(red_candidate)
    finally:
        vcb.get_bridge = original_get_bridge

    fake_gateway.execute.assert_called_once()
    if bridge_reached["value"]:
        raise AssertionError(
            "a RED action reached the code-execution bridge during this "
            "smoke test -- the authorization boundary did not hold"
        )

    return {
        "lazy_construction_clean": True,
        "lifecycle_ok": True,
        "red_action_blocked_before_bridge": True,
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    result = asyncio.run(_smoke_test())
    ok = all(result.values())
    print(
        f"✅ autonomous_loop OK — isolated smoke test passed: {result}"
        if ok else f"❌ FAILED — {result}"
    )
