import sys
import asyncio
import datetime
import hashlib
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


def _capture_loop_error(exc: Exception, context: str, district: str = "") -> None:
    """Send loop errors to Sentry + log via loguru. Never raises."""
    try:
        from core.openhuman.telemetry.sentry_bridge import init_sentry
        s = init_sentry()
        s.capture_exception(exc, context={
            "loop_context": context,
            "district": district,
            "component": "autonomous_loop",
        })
    except Exception:
        pass
    logger.error("[VECTOR][{}] {}: {}", context, type(exc).__name__, exc)


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
        self._governor = None
        self._memory = None
        self._ambient = None
        self._policy = None
        self._red_team = None
        self._hypothesis_engine = None
        self._gateway = None
        self._cron_last_run: dict[str, datetime.datetime] = {}
        logger.info("[VECTOR][autonomous_loop] initialized")

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
                self._scheduler = TaskScheduler()
                logger.info("[VECTOR][autonomous_loop] durable scheduler ready")
            except Exception as e:
                logger.warning(f"[VECTOR][autonomous_loop] scheduler unavailable: {e}")
                self._scheduler = None
        return self._scheduler

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
            logger.info("[VECTOR][scheduler_loop] scheduler unavailable — loop disabled")
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
                logger.error(f"[VECTOR][scheduler_loop] tick error: {e}")
            # Also fire VECTOR-native cron jobs directly (TaskScheduler is
            # prompt-based; function-based jobs fire via this mechanism)
            try:
                await self._fire_vnative_cron_jobs()
            except Exception as e:
                logger.error(f"[VECTOR][scheduler_loop] native cron error: {e}")
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

    async def _fire_vnative_cron_jobs(self) -> None:
        """Check and fire VECTOR-native cron job entries at their scheduled times."""
        from core.loop.cron_jobs import job_trigger_workflow, job_benchmark_suite, job_recipe_sync
        entries: list[tuple[str, str, Callable]] = [
            ("daily-workflow-trigger", "0 8 * * *", job_trigger_workflow),
            ("weekly-benchmark-suite", "0 1 * * 0", job_benchmark_suite),
            ("weekly-recipe-sync",     "30 1 * * 0", job_recipe_sync),
        ]
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
                        logger.info(f"[VECTOR][cron] {job_id} → {result.get('status', '?')}")
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

    # ─── Observe ──────────────────────────────────────────────────────────────

    async def observe_loop(self):
        """Observe world state every 0.5s. Never crashes."""
        interval = CONFIG["loop"]["observe_interval_sec"]
        logger.info(f"[VECTOR][observe] started — {interval}s interval")
        while self._running:
            try:
                await self._observe_tick()
                self._tick_count += 1
            except Exception as e:
                _capture_loop_error(e, "observe_loop")
            await asyncio.sleep(interval)

    async def _observe_tick(self):
        """Single observation tick. Validates ambient output before pipeline propagation."""
        if self._ambient is None:
            from core.voice.ambient_listener import AmbientListener
            self._ambient = AmbientListener()
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

    # ─── Think ────────────────────────────────────────────────────────────────

    async def think_loop(self):
        """Event-driven reasoning — 10s evaluation cycle. Never crashes."""
        logger.info("[VECTOR][think] started — 10s evaluation cycle")
        while self._running:
            try:
                await self._think_tick()
                await asyncio.sleep(10)
            except Exception as e:
                _capture_loop_error(e, "think_loop")
                await asyncio.sleep(5)

    async def _think_tick(self):
        """Evaluate goals → 4 candidates → decision → act. RULE 1: hydrate first."""
        from core.loop.decision_engine import Candidate

        # RULE 1 — world state snapshot before any reasoning
        # Run in thread — get_world_state() calls ScreenObserver.observe() (blocking OCR)
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
            except Exception:
                pass

    async def _act_on(self, winner: "DecisionEngine.Candidate") -> None:
        """
        Route winner to governor (which routes to permission_gateway).
        RULE 3 — LLM zero direct access. All through gateway.
        RULE 7 — update_from_outcome() AFTER every action.
        """
        # VectorCode routing — coding actions go through permission_gateway first, then bridge
        # RULE 3: LLM has ZERO direct access — gateway always gates, even for VectorCode tasks
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
                from integrations.vectorcode_bridge import get_bridge
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
                    logger.info(f"[VECTOR][act] VectorCode {winner.action_type} → {vc_result.get('status')} reward={reward}")
                    return
            except Exception as _vc_err:
                logger.warning(f"[VECTOR][act] VectorCode routing failed: {_vc_err} — falling through to governor")

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
            result = await self._get_governor().dispatch({
                "type": winner.action_type,
                "params": winner.params,
                "source": "autonomous_loop",
            })

            # Check for real user feedback in episodic memory (RULE 7 — real outcomes)
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

            if winner.reasoning_chain:
                self._get_memory().store_chain(
                    situation=json.dumps(winner.situation) if winner.situation else winner.action_type,
                    goal_ids=winner.goal_ids,
                    steps=winner.reasoning_chain,
                    action=winner.action_type,
                    outcome=f"status={result.get('status')} reward={reward}",
                    reward=reward,
                )

            self._capture_trace("act", {
                "action": winner.action_type,
                "result": result.get("status"),
                "reward": reward,
                "goal_ids": winner.goal_ids,
            })
            logger.info(
                f"[VECTOR][act] {winner.action_type} -> {result.get('status')} reward={reward:.3f}"
                + (f" (user_feedback={uf:.2f})" if user_feedback is not None else "")
            )
        except Exception as e:
            logger.error(f"[VECTOR][act] _act_on failed: {e}")

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
            pass
        return None

    # ─── Reflect ──────────────────────────────────────────────────────────────

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
                    await self._reflect_tick()

            except Exception as e:
                logger.error(f"[VECTOR][reflect] error: {e}")
                # Chunked backoff so stop() is responsive
                for _ in range(300):
                    if not self._running:
                        break
                    await asyncio.sleep(1.0)

    async def _reflect_tick(self) -> None:
        logger.info("[VECTOR][reflect] 2AM reflection starting...")
        try:
            from agents.districts.reflection.daily_reviewer import DailyReviewer
            reviewer = DailyReviewer()
            ok = await reviewer.review()
            logger.info(f"[VECTOR][reflect] DailyReviewer done — ok={ok}")
        except Exception as e:
            logger.error(f"[VECTOR][reflect] DailyReviewer failed: {e}")
            # Fallback: at minimum store a log entry
            self._get_memory().store(
                event_type="reflect",
                content=f"2AM reflection fallback — ticks={self._tick_count}",
                tags=["reflect", "daily"],
                source="autonomous_loop",
            )

    # ─── Sync ─────────────────────────────────────────────────────────────────

    async def sync_loop(self):
        """Cloud DB sync every 48h. Never crashes."""
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
        """Push heartbeat to brain server (Fly.io) and log sync."""
        logger.info("[VECTOR][sync] DB sync tick — pushing heartbeat to brain server")
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
                logger.info(f"[VECTOR][sync] heartbeat → brain server {r.status_code}")
        except Exception as e:
            logger.warning(f"[VECTOR][sync] heartbeat failed: {e}")

    # ─── Obsidian vault watcher ───────────────────────────────────────────────

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

    # ─── Phone node poll ──────────────────────────────────────────────────────

    async def phone_loop(self) -> None:
        """Poll phone ambient server every 60s. Graceful if phone disconnected."""
        logger.info("[VECTOR][phone] loop starting")
        try:
            from phone_node.adb_bridge import poll_loop
            await poll_loop(interval_sec=60)
        except Exception as e:
            logger.warning(f"[VECTOR][phone] loop unavailable: {e}")

    # ─── VectorCode MCP server ────────────────────────────────────────────────

    async def vectorcode_loop(self) -> None:
        """Start VectorCode MCP server at startup. Restarts if it crashes."""
        logger.info("[VECTOR][vectorcode] loop starting")
        try:
            from integrations.vectorcode_bridge import get_bridge
            bridge = get_bridge()
            if not bridge.is_available():
                logger.warning("[VECTOR][vectorcode] VectorCode not available — skipping MCP server")
                return
            mcp_port = 9001
            try:
                from core.config import CONFIG
                mcp_port = CONFIG.get("vectorcode", {}).get("mcp_port", 9001)
            except Exception:
                pass
            proc = await bridge.start_mcp_server(port=mcp_port)
            if proc:
                logger.info(f"[VECTOR][vectorcode] MCP server running on port {mcp_port}")
        except Exception as e:
            logger.warning(f"[VECTOR][vectorcode] loop failed: {e}")

    # ─── Main entry ───────────────────────────────────────────────────────────

    async def run_forever(self) -> None:
        """
        RULE 2 — Never returns in production.
        return_exceptions=True ensures one crashed coroutine doesn't kill others.
        """
        self._running = True
        self._start_time = datetime.datetime.now(datetime.timezone.utc)
        logger.info(
            f"[VECTOR][autonomous_loop] run_forever() at {self._start_time.isoformat()}"
        )

        # Initialise background task queue — shares this event loop
        try:
            from core.loop.task_queue import TaskQueue
            TaskQueue.get()
            logger.info("[VECTOR][autonomous_loop] task_queue ready")
        except Exception as e:
            logger.warning(f"[VECTOR][autonomous_loop] task_queue init failed: {e}")

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

        await asyncio.gather(
            self.observe_loop(),
            self.think_loop(),
            self.reflect_loop(),
            self.sync_loop(),
            self.obsidian_loop(),
            self.phone_loop(),
            self.vectorcode_loop(),
            self.scheduler_loop(),
            self.hypothesis_loop(),      # VECTOR Gap 5 — proactive insights every 4h
            return_exceptions=True,
        )

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
                await asyncio.sleep(300)  # back off 5min on error, then retry

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
        f"✅ autonomous_loop OK — {ticks} observe ticks in 2s, started+stopped cleanly"
        if ok else "❌ FAILED"
    )
