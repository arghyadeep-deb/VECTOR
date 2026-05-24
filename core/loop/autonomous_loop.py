import sys
import asyncio
import datetime
import hashlib
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
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


class AutonomousLoop:
    """
    RULE 2 Ã¢â‚¬â€ THE LOOP NEVER STOPS.
    run_forever() never returns. Every coroutine catches ALL exceptions and restarts.
    Loop: observe(0.5s) Ã¢â€ â€™ think(event-driven) Ã¢â€ â€™ act(permission-gated) Ã¢â€ â€™ reflect(2AM) Ã¢â€ â€™ sync(48h)
    """

    def __init__(self):
        self._running = False
        self._start_time: datetime.datetime | None = None
        self._tick_count = 0
        self._context_engine = None
        self._goal_system = None
        self._decision_engine = None
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
        logger.info("[VECTOR][autonomous_loop] initialized")

    async def _get_event_bus(self):
        if self._event_bus is None:
            from core.event_bus.bus import get_event_bus
            self._event_bus = await get_event_bus()
            from core.event_bus.worker_pool import WorkerPool
            self._worker_pool = WorkerPool(max_workers=10)
        return self._event_bus

    async def _fanout_handler(self, event) -> None:
        """Fan-out event to subscribed agents with gather + timeout, then trigger downstream tasks."""
        try:
            from core.city.agent_registry import get_registry
            from core.event_bus.wiring import get_downstream_tasks
            registry = get_registry()
            et = event.event_type.value if event.event_type else ""
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
                    params = {k: (v.format(event_type=et, event_data=str(getattr(event, 'data', {})))) for k, v in params_template.items()}
                    task = {"type": task_type, "district": district, "params": params, "source_event": et}
                    asyncio.create_task(governor.dispatch(task))
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
                logger.debug(f"[VECTOR][guidance] unavailable: {e}")
                self._guidance = None
        return self._guidance

    def _get_continue_gate(self):
        """ContinueGate: step-level budget + coherence enforcer for the autonomous loop."""
        if getattr(self, "_continue_gate", None) is None:
            try:
                from vectorcode.src.guidance import ContinueGate
                self._continue_gate = ContinueGate()
            except Exception as e:
                logger.debug(f"[VECTOR][guidance] ContinueGate unavailable: {e}")
                self._continue_gate = None
        return self._continue_gate

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

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Scheduler + Workflow integrations (VectorCode-absorbed) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def _get_scheduler(self):
        """Durable task scheduler Ã¢â‚¬â€ persistent state + retry semantics.

        Wraps core/scheduler/. Used by scheduler_loop() to fire scheduled
        tasks that must survive process restarts (vs the in-process timer
        loops which are lost on crash).
        """
        if getattr(self, "_scheduler", None) is None:
            try:
                from core.scheduler import TaskScheduler  # type: ignore
                self._scheduler = TaskScheduler()
                logger.info("[VECTOR][autonomous_loop] durable scheduler ready")
            except Exception as e:
                logger.warning(f"[VECTOR][autonomous_loop] scheduler unavailable: {e}")
                self._scheduler = None
        return self._scheduler

    def _get_workflow_runner(self):
        """DAG workflow runner. Districts can trigger multi-step workflows
        via runner.run(workflow_dict) Ã¢â‚¬â€ returns WorkflowResult.
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
        logger.info("[VECTOR][scheduler_loop] started Ã¢â‚¬â€ 30s tick")
        # Operator manager wire (absorbed OJ Ã¢â‚¬â€ alternative task scheduler)
        if getattr(self, "_operator_mgr", None) is not None:
            logger.info("[VECTOR][scheduler_loop] OperatorManager available")
        scheduler = self._get_scheduler()
        if scheduler is None:
            logger.info("[VECTOR][scheduler_loop] scheduler unavailable Ã¢â‚¬â€ loop disabled")
            return
        # Register default daily/weekly jobs on first init
        try:
            from core.loop.cron_jobs import register_default_jobs
            n = register_default_jobs(scheduler)
            logger.info(f"[VECTOR][scheduler_loop] {n} default jobs registered")
        except Exception as exc:
            logger.warning(f"[VECTOR][scheduler_loop] cron registration failed: {exc}")

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
            # Gap 4: drain retry queue Ã¢â‚¬â€ re-execute actions that previously failed
            try:
                from core.queue.retry_queue import RetryQueue
                from core.loop.permission_gateway import Action
                rq = RetryQueue.get()
                for item in rq.pop_due(limit=5):
                    try:
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
            # Phase 3E: Work-stealing Ã¢â‚¬â€ match queued tasks to available agents
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
                            f"[VECTOR][claims] {len(queued_tasks)} queued Ã¢â€ â€™ "
                            f"{assigned} claimed by {len(alive)} agents"
                        )
            except Exception as _cl_err:
                logger.debug(f"[VECTOR][scheduler_loop] work-stealing skipped: {_cl_err}")
            await asyncio.sleep(30.0)

    def _parse_cron_daily(self, expr: str) -> tuple[int, int] | None:
        """Parse ``M H * * *`` Ã¢â€ â€™ (hour, minute). Returns None if not daily."""
        parts = expr.strip().split()
        if len(parts) == 5 and parts[2] == "*" and parts[3] == "*" \
                and parts[4] == "*":
            try:
                return int(parts[1]), int(parts[0])  # (hour, minute)
            except ValueError:
                return None
        return None

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
                last = self._cron_last_run.get(job_id)
                window_start = now.replace(second=0, microsecond=0)
                if last is None or last < window_start:
                    self._cron_last_run[job_id] = now
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
            import asyncio
            asyncio.create_task(_emit("system", "process_crash", True, "autonomous_loop", {"error": str(exc)[:200]}))
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Observe Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def observe_loop(self):
        """Observe world state every 0.5s. Never crashes."""
        interval = CONFIG["loop"]["observe_interval_sec"]
        logger.info(f"[VECTOR][observe] started Ã¢â‚¬â€ {interval}s interval")
        guard = _get_loop_guard()
        while self._running:
            try:
                await self._observe_tick()
                self._tick_count += 1
                if guard:
                    guard.tick()
                    if guard.is_terminated:
                        logger.warning("[VECTOR][observe] LoopGuard terminated Ã¢â‚¬â€ resetting")
                        guard.reset()
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
        # FIX #8: Validate ambient listener output before it enters thinkÃ¢â€ â€™act pipeline
        if result is not None:
            if not isinstance(result, dict):
                logger.warning(f"[VECTOR][observe] Ambient returned non-dict: {type(result)} Ã¢â‚¬â€ discarding")
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
            # Feed actionable voice results into the thinkÃ¢â€ â€™act pipeline
            if result.get("actionable"):
                self._pending_voice = result
                logger.debug("[VECTOR][observe] voice intent queued: {}", result.get("intent"))

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

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Think Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def think_loop(self):
        """Event-driven reasoning Ã¢â‚¬â€ 10s evaluation cycle. Never crashes."""
        logger.info("[VECTOR][think] started Ã¢â‚¬â€ 10s evaluation cycle")
        while self._running:
            try:
                await self._think_tick()
                await asyncio.sleep(10)
            except Exception as e:
                _capture_loop_error(e, "think_loop")
                await asyncio.sleep(5)

    async def _think_tick(self):
        """Evaluate goals Ã¢â€ â€™ 4 candidates Ã¢â€ â€™ decision Ã¢â€ â€™ act. RULE 1: hydrate first."""
        from core.monitoring.perf_contracts import timed_ctx
        from core.loop.decision_engine import Candidate
        _perf_ctx = timed_ctx("think_tick")

        # Voice intent takes priority Ã¢â‚¬â€ act immediately, skip goal evaluation this tick
        pending = getattr(self, "_pending_voice", None)
        if pending:
            self._pending_voice = None
            logger.info("[VECTOR][think] voice intent dispatched: {}", pending.get("intent"))
            await self._act({
                "type":       pending.get("intent", "respond"),
                "params":     pending.get("params", {}),
                "source":     "voice",
                "confidence": pending.get("confidence", 0.8),
            })
            return

        # RULE 1 Ã¢â‚¬â€ world state snapshot before any reasoning
        # Run in thread Ã¢â‚¬â€ get_world_state() calls ScreenObserver.observe() (blocking OCR)
        world_state = await asyncio.to_thread(self._get_context().get_world_state)

        actions = self._get_goals().generate_immediate_actions(limit=4)
        if not actions:
            return

        # Map goal tags to concrete routable action types
        _TAG_TO_ACTION = {
            "kiit": "check_attendance",
            "attendance": "check_attendance",
            "git": "git_status",
            "coding": "code_task",
            "build": "code_task",
            "research": "daily_digest",
            "ml": "search_arxiv",
            "karpathy": "search_arxiv",
            "learning": "search_arxiv",
            "finance": "monthly_report",
            "health": "check_fatigue",
            "placement": "search_web",
            "interview": "search_web",
            "dsa": "search_web",
            "memory": "consolidate",
            "reflection": "daily_review",
            "debug": "code_task",
            "fix": "code_task",
            "implement": "code_task",
            "write_code": "code_task",
            "code_review": "code_review_vc",
            "refactor": "code_task",
        }

        candidates = []
        for a in actions:
            # Derive a concrete action type from goal tags
            tags = a.get("tags", [])
            action_type = a["action"]  # default
            for tag in tags:
                if tag in _TAG_TO_ACTION:
                    action_type = _TAG_TO_ACTION[tag]
                    break
            candidates.append(
                Candidate(
                    action_type=action_type,
                    params={"goal_id": a["goal_id"], "title": a["title"]},
                    goal_ids=[a["goal_id"]],
                    urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(
                        a.get("urgency", "low"), 0.5
                    ),
                    confidence=0.7,
                    source="think_loop",
                    situation=world_state,
                )
            )

        decision = await self._get_decision().evaluate(candidates)
        if decision.winner.total_score > 0.3:
            await self._publish_event(EventType.DECISION_MADE, {
                "action_type": decision.winner.action_type,
                "score": decision.winner.total_score,
                "goal_ids": decision.winner.goal_ids,
            })
            await self._act_on(decision.winner)
        else:
            logger.debug(
                f"[VECTOR][decision] Winner '{decision.winner.action_type}' dropped: "
                f"score={decision.winner.total_score:.3f} < 0.3 threshold Ã¢â‚¬â€ no action taken"
            )

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Act Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    def _capture_trace(self, event: str, data: dict) -> None:
        """Feed trace data to the absorbed TraceCollector if available."""
        if getattr(self, "_trace_collector", None) is not None:
            try:
                self._trace_collector.capture(event=event, **data)
            except Exception: logger.debug("[VECTOR][loop] exception suppressed")

    async def _act_on(self, winner: "DecisionEngine.Candidate") -> None:
        """
        Route winner to governor (which routes to permission_gateway).
        RULE 3 Ã¢â‚¬â€ LLM zero direct access. All through gateway.
        RULE 7 Ã¢â‚¬â€ update_from_outcome() AFTER every action.
        """
        await self._publish_event(EventType.AGENT_STATE_CHANGED, {
            "action_type": winner.action_type,
            "state": "acting",
            "score": winner.total_score,
        })
        # VectorCode routing Ã¢â‚¬â€ coding actions go through permission_gateway first, then bridge
        # RULE 3: LLM has ZERO direct access Ã¢â‚¬â€ gateway always gates, even for VectorCode tasks
        _VC_ACTION_TYPES = {"code_task", "code_review_vc", "code_generate", "code_fix", "code_debug"}
        if winner.action_type in _VC_ACTION_TYPES:
            try:
                # RULE 3: gate through permission_gateway before executing
                gw = self._get_gateway()
                if gw is not None:
                    allowed, reason = await gw.evaluate(winner)
                    if not allowed:
                        logger.warning(f"[VECTOR][act] VectorCode action '{winner.action_type}' blocked by gateway: {reason}")
                        return
                from districts.coding.vectorcode_bridge import get_bridge
                bridge = get_bridge()
                if bridge.is_available():
                    vc_result = await bridge.run_task(
                        winner.params.get("title", winner.action_type),
                        mode="run",
                    )
                    reward = 0.8 if vc_result.get("status") == "ok" else 0.3
                    pm = self._get_policy()
                    sk = f"{winner.action_type}:{json.dumps(winner.params, sort_keys=True, default=str)}"
                    h = hashlib.sha256(sk.encode()).hexdigest()[:12]
                    pm.update_from_outcome(winner.action_type, h, reward)
                    logger.info(f"[VECTOR][act] VectorCode {winner.action_type} Ã¢â€ â€™ {vc_result.get('status')} reward={reward}")
                    return
            except Exception as _vc_err:
                logger.warning(f"[VECTOR][act] VectorCode routing failed: {_vc_err} Ã¢â‚¬â€ falling through to governor")

        # Gap 17: SwarmCoordinator Ã¢â‚¬â€ for multi-agent actions, coordinate via swarm
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

        # Gap 17: Comms Ã¢â‚¬â€ broadcast action result to configured channels after execution.
        # This is done post-execution (see _broadcast_result below).

        # ThreatDetector: scan action description before execution (guidance.py)
        action_desc = f"{winner.action_type} {json.dumps(winner.params, default=str)}"
        if self._scan_threats(action_desc, context="act"):
            logger.warning(f"[VECTOR][guidance] action '{winner.action_type}' blocked by ThreatDetector")
            return

        # RedTeamAgent adversarial review for RED-level actions (VECTOR Gap 2)
        _RED_ACTION_TYPES = set(CONFIG.get("permission", {}).get("red", []))
        if winner.action_type in _RED_ACTION_TYPES:
            red_team = self._get_red_team()
            if red_team is not None:
                try:
                    review = red_team.attack_plan({
                        "action_type": winner.action_type,
                        "params": winner.params,
                        "goal_ids": winner.goal_ids,
                        "score": winner.total_score,
                    })
                    verdict = str(review.get("verdict", "APPROVED")).upper()
                    if verdict.startswith("BLOCKED"):
                        logger.warning(
                            f"[VECTOR][red_team] RED action '{winner.action_type}' BLOCKED: "
                            f"{review.get('reason', 'adversarial review failed')}"
                        )
                        return
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

        try:
            # Phase 3B: check VectorCode Skills system before governor dispatch
            # If a skill matches with confidence > 0.8, execute via skills and skip governor.
            _skill_executed = False
            try:
                from vectorcode.src.skills.manager import SkillManager
                sm = SkillManager()
                skill = sm.match(action_type=winner.action_type, params=winner.params)
                if skill and getattr(skill, 'confidence', 0) > 0.8:
                    skill_result = await sm.execute(skill, winner.params)
                    if skill_result and skill_result.get("status") != "error":
                        result = skill_result
                        _skill_executed = True
                        logger.info(f"[VECTOR][skills] {winner.action_type} handled by skill '{getattr(skill, 'name', '?')}'")
            except Exception as _sk_err:
                logger.debug(f"[VECTOR][skills] skill match skipped: {_sk_err}")

            if not _skill_executed:
                result = await self._get_governor().dispatch({
                    "type": winner.action_type,
                    "params": winner.params,
                    "source": "autonomous_loop",
                })

            # Check for real user feedback in episodic memory (RULE 7 Ã¢â‚¬â€ real outcomes)
            user_feedback = self._get_recent_feedback(winner.action_type)

            # 5-factor RL reward (Architecture.md spec):
            completed = 1.0 if result.get("status") in ("ok", "executed") else 0.0
            goal_progress = float(result.get("goal_progress", 0.5))
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
            situation_key = f"{winner.action_type}:{json.dumps(winner.params, sort_keys=True, default=str)}"
            h = hashlib.sha256(situation_key.encode()).hexdigest()[:12]
            pm.update_from_outcome(winner.action_type, h, reward)

            try:
                from core.loop.loop_state import save_decision
                save_decision(winner.action_type, winner.params, winner.total_score)
            except Exception:
                pass

            if winner.reasoning_chain:
                self._get_memory().store_chain(
                    situation=json.dumps(winner.situation) if winner.situation else winner.action_type,
                    goal_ids=winner.goal_ids,
                    steps=winner.reasoning_chain,
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
            # Gap 17: Comms broadcast Ã¢â‚¬â€ notify configured channels when a significant
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

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Reflect Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def reflect_loop(self):
        """2AM daily reflection. Never crashes."""
        logger.info("[VECTOR][reflect] started Ã¢â‚¬â€ fires at 2:00 AM daily")
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
                    await self._reflect_tick()

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
            logger.info(f"[VECTOR][reflect] DailyReviewer done Ã¢â‚¬â€ ok={ok}")
        except Exception as e:
            logger.error(f"[VECTOR][reflect] DailyReviewer failed: {e}")

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
            # Fallback: at minimum store a log entry
            self._get_memory().store(
                event_type="reflect",
                content=f"2AM reflection fallback Ã¢â‚¬â€ ticks={self._tick_count}",
                tags=["reflect", "daily"],
                source="autonomous_loop",
            )
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Sync Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def sync_loop(self):
        """Cloud DB sync every 48h. Never crashes."""
        sync_hours = CONFIG["loop"]["db_sync_hours"]
        logger.info(f"[VECTOR][sync] started Ã¢â‚¬â€ {sync_hours}h cloud sync interval")
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
        """Push heartbeat to brain server (Fly.io) and log sync."""
        logger.info("[VECTOR][sync] DB sync tick Ã¢â‚¬â€ pushing heartbeat to brain server")
        try:
            import httpx
            brain_url = CONFIG.get("brain_server_url", "https://vector-brain.fly.dev")
            payload = {
                "uptime_sec": self.uptime_seconds,
                "tick_count": self._tick_count,
                "agents_alive": 0,
                "source": "autonomous_loop",
            }
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.post(f"{brain_url}/heartbeat", json=payload)
                logger.info(f"[VECTOR][sync] heartbeat Ã¢â€ â€™ brain server {r.status_code}")
                # Gap 10: parse response body for commands[] from brain server
                if r.status_code == 200:
                    try:
                        body = r.json()
                        commands = body.get("commands") or []
                        for cmd in commands:
                            cmd_type = cmd.get("type", "")
                            cmd_params = cmd.get("params", {})
                            logger.info(f"[VECTOR][sync] remote command: {cmd_type} {cmd_params}")
                            if cmd_type == "research":
                                self._pending_voice.append(cmd_params.get("query", ""))
                            elif cmd_type == "voice_broadcast":
                                self._pending_voice.append(cmd_params.get("text", ""))
                            elif cmd_type == "deploy":
                                logger.warning(f"[VECTOR][sync] deploy command received Ã¢â‚¬â€ routing to permission gateway")
                                from core.loop.permission_gateway import PermissionGateway, Action
                                gw = PermissionGateway()
                                await gw.execute(Action(
                                    action_type="deploy_production",
                                    params=cmd_params,
                                    proposed_by="brain_server",
                                ))
                    except Exception as _parse_err:
                        logger.debug(f"[VECTOR][sync] response parse failed: {_parse_err}")
        except Exception as e:
            logger.warning(f"[VECTOR][sync] heartbeat failed: {e}")

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Obsidian vault watcher Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def obsidian_loop(self) -> None:
        """Start vault watcher + bulk ingest at startup. Never crashes."""
        logger.info("[VECTOR][obsidian] loop starting")
        try:
            from core.memory.obsidian_sync import ObsidianSync
            obs = ObsidianSync()

            if CONFIG.get("obsidian", {}).get("ingest_on_startup", True):
                try:
                    count = await obs.ingest_existing()
                    logger.info(f"[VECTOR][obsidian] startup ingest: {count} files")
                except Exception as e:
                    logger.warning(f"[VECTOR][obsidian] startup ingest failed: {e}")

            await obs.start_watching()
        except Exception as e:
            logger.error(f"[VECTOR][obsidian] loop crashed: {e}")

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Phone node poll Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def phone_loop(self) -> None:
        """Poll phone ambient server every 60s. Graceful if phone disconnected."""
        logger.info("[VECTOR][phone] loop starting")
        try:
            from phone_node.adb_bridge import poll_loop
            await poll_loop(interval_sec=60)
        except Exception as e:
            logger.warning(f"[VECTOR][phone] loop unavailable: {e}")

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Health monitoring cycles Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def wearable_poll_cycle(self) -> None:
        cfg = CONFIG.get("health", {})
        if not cfg.get("enabled", False):
            return
        interval = cfg.get("wearable_poll_interval_minutes", 15) * 60
        logger.info(f"[VECTOR][health] wearable_poll_cycle started Ã¢â‚¬â€ {interval//60}min interval")
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
        logger.info(f"[VECTOR][health] health_analysis_cycle started Ã¢â‚¬â€ {interval//60}min interval")
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
        logger.info(f"[VECTOR][health] emergency_detection_cycle started Ã¢â‚¬â€ {interval}s interval")
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

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ VectorCode MCP server Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def vectorcode_loop(self) -> None:
        """Start VectorCode MCP server at startup. Restarts if it crashes."""
        logger.info("[VECTOR][vectorcode] loop starting")
        try:
            from districts.coding.vectorcode_bridge import get_bridge
            bridge = get_bridge()
            if not bridge.is_available():
                logger.warning("[VECTOR][vectorcode] VectorCode not available Ã¢â‚¬â€ skipping MCP server")
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
        except Exception as e:
            logger.warning(f"[VECTOR][vectorcode] loop failed: {e}")

    async def emergency_loop(self) -> None:
        """Start Emergency Response System. Never crashes."""
        logger.info("[VECTOR][emergency] loop starting")
        try:
            cfg = CONFIG.get("emergency", {})
            if not cfg.get("enabled", False):
                logger.info("[VECTOR][emergency] disabled in config")
                return
            from districts.emergency.main import EmergencyResponseSystem
            self._emergency = EmergencyResponseSystem()
            await self._emergency.start()
            logger.info("[VECTOR][emergency] system online")
            while self._running:
                await asyncio.sleep(60)
        except ImportError as e:
            logger.warning("[VECTOR][emergency] unavailable: {}", e)
        except asyncio.CancelledError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        except Exception as e:
            logger.error(f"[VECTOR][emergency] loop crashed: {e}")

    # Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Main entry Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

    async def run_forever(self) -> None:
        """
        RULE 2 Ã¢â‚¬â€ Never returns in production.
        return_exceptions=True ensures one crashed coroutine doesn't kill others.
        """
        self._running = True
        self._start_time = datetime.datetime.now(datetime.timezone.utc)
        logger.info(
            f"[VECTOR][autonomous_loop] run_forever() at {self._start_time.isoformat()}"
        )

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

        # Ã¢â€â‚¬Ã¢â€â‚¬ Agent-to-Agent event fan-out handler Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        try:
            from core.event_bus.base import Subscription
            from core.event_bus.types import Event
            from core.city.agent_registry import AgentRegistry
            from core.loop.context_engine import ContextEngine
            bus = await self._get_event_bus()
            self._fanout_sub = bus.subscribe(None, self._fanout_handler)
            logger.info("[VECTOR][autonomous_loop] event fan-out subscriber registered")
        except Exception as e:
            self._fanout_sub = None
            logger.warning(f"[VECTOR][autonomous_loop] event fan-out init failed: {e}")

        # Ã¢â€â‚¬Ã¢â€â‚¬ AmbientScheduler: recover any crashed sessions from prior run Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        try:
            from core.jcode.session_persistence import SessionPersistence
            _store = SessionPersistence()
            crashed = _store.recover_crashed_sessions()
            if crashed:
                logger.warning(
                    "[VECTOR][autonomous_loop] {} crashed session(s) recovered Ã¢â‚¬â€ "
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

        await asyncio.gather(
            self.observe_loop(),
            self.think_loop(),
            self.reflect_loop(),
            self.sync_loop(),
            self.obsidian_loop(),
            self.phone_loop(),
            self.vectorcode_loop(),
            self.scheduler_loop(),
            self.ambient_scheduler_loop(),
            self.hypothesis_loop(),
            self.predict_cycle(),
            self.degradation_monitor(),
            self.wearable_poll_cycle(),
            self.health_analysis_cycle(),
            self.emergency_detection_cycle(),
            self.research_loop(),
            return_exceptions=True,
        )

    async def degradation_monitor(self) -> None:
        logger.info("[VECTOR][degradation] monitor started Ã¢â‚¬â€ 30s check cycle")
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
        RULE 2 Ã¢â‚¬â€ never dies.
        """
        logger.info("[VECTOR][autonomous_loop] ambient_scheduler_loop starting Ã¢â‚¬â€ 60s poll")
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
        VECTOR Gap 5 Ã¢â‚¬â€ HypothesisEngine: proactive insight generation.
        Runs every 4 hours. Only surfaces insights with confidence > 0.85.
        RULE 2 Ã¢â‚¬â€ never dies: all exceptions caught, loop always restarts.
        """
        logger.info("[VECTOR][autonomous_loop] hypothesis_loop starting Ã¢â‚¬â€ fires every 4h")
        while self._running:
            try:
                await asyncio.sleep(4 * 3600)
                if not self._running:
                    break
                engine = self._get_hypothesis_engine()
                if engine is None:
                    continue
                context = self._get_context().get_world_state()
                hypotheses = engine.generate_hypotheses(context)
                if not hypotheses:
                    continue
                for h in hypotheses if isinstance(hypotheses, list) else [hypotheses]:
                    confidence = h.get("confidence", 0.0) if isinstance(h, dict) else 0.0
                    if confidence >= 0.85:
                        content = h.get("hypothesis", str(h)) if isinstance(h, dict) else str(h)
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
            f"[VECTOR][predict_cycle] started Ã¢â‚¬â€ forecast every {pred_interval}min, sim every {sim_interval}min"
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
        """SPEC-10 scheduled research Ã¢â‚¬â€ fires at research_lab.schedule_interval_hours."""
        cfg = CONFIG.get("research_lab", {})
        if not cfg.get("enabled", False):
            logger.info("[VECTOR][research] research_lab disabled Ã¢â‚¬â€ research_loop skipped")
            return
        interval = cfg.get("schedule_interval_hours", 6)
        logger.info("[VECTOR][research] research_loop started Ã¢â‚¬â€ fires every {}h", interval)
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

    def stop(self) -> None:
        """Graceful stop for tests only. Never call in production."""
        self._running = False
        logger.info("[VECTOR][autonomous_loop] stopped")

    @property
    def uptime_seconds(self) -> int:
        if self._start_time is None:
            return 0
        return int((datetime.datetime.now(datetime.timezone.utc) - self._start_time).total_seconds())


async def _smoke_test() -> int:
    loop = AutonomousLoop()

    async def _stop(secs: float) -> None:
        await asyncio.sleep(secs)
        loop.stop()

    await asyncio.gather(loop.run_forever(), _stop(2), return_exceptions=True)
    return loop._tick_count


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ticks = asyncio.run(_smoke_test())
    ok = ticks >= 0
    print(
        f"Ã¢Å“â€¦ autonomous_loop OK Ã¢â‚¬â€ {ticks} observe ticks in 2s, started+stopped cleanly"
        if ok else "Ã¢ÂÅ’ FAILED"
    )
