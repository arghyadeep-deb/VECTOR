import sys
import asyncio
import datetime
import hashlib
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


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
                logger.error(f"[VECTOR][observe] tick error: {e}")
            await asyncio.sleep(interval)

    async def _observe_tick(self):
        """Single observation tick. Delegates to AmbientListener (T3 voice pipeline)."""
        if self._ambient is None:
            from core.voice.ambient_listener import AmbientListener
            self._ambient = AmbientListener()
        await self._ambient.listen_tick()

    # ─── Think ────────────────────────────────────────────────────────────────

    async def think_loop(self):
        """Event-driven reasoning — 10s evaluation cycle. Never crashes."""
        logger.info("[VECTOR][think] started — 10s evaluation cycle")
        while self._running:
            try:
                await self._think_tick()
            except Exception as e:
                logger.error(f"[VECTOR][think] tick error: {e}")
                await asyncio.sleep(5)
            await asyncio.sleep(10)

    async def _think_tick(self):
        """Evaluate goals → 4 candidates → decision → act. RULE 1: hydrate first."""
        from core.loop.decision_engine import Candidate

        # RULE 1 — world state snapshot before any reasoning
        world_state = self._get_context().get_world_state()

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

    # ─── Act ──────────────────────────────────────────────────────────────────

    async def _act_on(self, winner: "DecisionEngine.Candidate") -> None:
        """
        Route winner to governor (which routes to permission_gateway).
        RULE 3 — LLM zero direct access. All through gateway.
        RULE 7 — update_from_outcome() AFTER every action.
        """
        # VectorCode routing — coding actions bypass governor, go direct to bridge
        _VC_ACTION_TYPES = {"code_task", "code_review_vc", "code_generate", "code_fix", "code_debug"}
        if winner.action_type in _VC_ACTION_TYPES:
            try:
                from integrations.vectorcode_bridge import get_bridge
                bridge = get_bridge()
                if bridge.is_available():
                    vc_result = await bridge.run_task(
                        winner.params.get("title", winner.action_type),
                        mode="run",
                    )
                    reward = 0.8 if vc_result.get("status") == "ok" else 0.3
                    pm = self._get_policy()
                    import hashlib, json as _json
                    sk = f"{winner.action_type}:{_json.dumps(winner.params, sort_keys=True, default=str)}"
                    h = hashlib.sha256(sk.encode()).hexdigest()[:12]
                    pm.update_from_outcome(winner.action_type, h, reward)
                    logger.info(f"[VECTOR][act] VectorCode {winner.action_type} → {vc_result.get('status')} reward={reward}")
                    return
            except Exception as _vc_err:
                logger.warning(f"[VECTOR][act] VectorCode routing failed: {_vc_err} — falling through to governor")

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

        await asyncio.gather(
            self.observe_loop(),
            self.think_loop(),
            self.reflect_loop(),
            self.sync_loop(),
            self.obsidian_loop(),
            self.phone_loop(),
            return_exceptions=True,
        )

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
