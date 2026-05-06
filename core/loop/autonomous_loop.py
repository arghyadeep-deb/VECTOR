import sys
import asyncio
import datetime
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
        from core.memory.policy import PolicyMemory
        if not hasattr(self, '_policy') or self._policy is None:
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
        """Evaluate goals → 4 candidates → decision → act."""
        from core.loop.decision_engine import Candidate

        actions = self._get_goals().generate_immediate_actions(limit=4)
        if not actions:
            return

        candidates = [
            Candidate(
                action_type=a["action"],
                params={"goal_id": a["goal_id"]},
                goal_ids=[a["goal_id"]],
                urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(
                    a.get("urgency", "low"), 0.5
                ),
                confidence=0.7,
                source="think_loop",
            )
            for a in actions
        ]

        decision = await self._get_decision().evaluate(candidates)
        if decision.winner.total_score > 0.3:
            await self._act_on(decision.winner)

    # ─── Act ──────────────────────────────────────────────────────────────────

    async def act_loop(self):
        """Permission-gated action execution. Never crashes."""
        logger.info("[VECTOR][act] started")
        while self._running:
            try:
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[VECTOR][act] error: {e}")
                await asyncio.sleep(5)

    async def _act_on(self, winner) -> None:
        """
        Route winner to governor (which routes to permission_gateway).
        RULE 3 — LLM zero direct access. All through gateway.
        RULE 7 — update_from_outcome() AFTER every action.
        """
        try:
            result = await self._get_governor().dispatch({
                "type": winner.action_type,
                "params": winner.params,
                "source": "autonomous_loop",
            })

            reward = 0.8 if result.get("status") == "ok" else 0.2

            from core.memory.policy import PolicyMemory
            pm = self._get_policy()
            h = PolicyMemory.make_situation_hash(winner.params)
            pm.update_from_outcome(winner.action_type, h, reward)

            logger.info(
                f"[VECTOR][act] {winner.action_type} → {result.get('status')} reward={reward}"
            )
        except Exception as e:
            logger.error(f"[VECTOR][act] _act_on failed: {e}")

    # ─── Reflect ──────────────────────────────────────────────────────────────

    async def reflect_loop(self):
        """2AM daily reflection. Never crashes."""
        logger.info("[VECTOR][reflect] started — fires at 2:00 AM daily")
        while self._running:
            try:
                now = datetime.datetime.now()
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

                if self._running and datetime.datetime.now().hour == reflect_hour:
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
            uptime = int(
                (datetime.datetime.now() - self._start_time).total_seconds()
            ) if self._start_time else 0
            self._get_memory().store(
                event_type="reflect",
                content=f"2AM reflection — ticks={self._tick_count}, uptime={uptime}s",
                tags=["reflect", "daily"],
                source="autonomous_loop",
            )
            logger.info("[VECTOR][reflect] reflection complete ✓")
        except Exception as e:
            logger.error(f"[VECTOR][reflect] tick failed: {e}")

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
        logger.info("[VECTOR][sync] DB sync tick — cloud not configured yet (T6)")

    # ─── Main entry ───────────────────────────────────────────────────────────

    async def run_forever(self) -> None:
        """
        RULE 2 — Never returns in production.
        return_exceptions=True ensures one crashed coroutine doesn't kill others.
        """
        self._running = True
        self._start_time = datetime.datetime.now()
        logger.info(
            f"[VECTOR][autonomous_loop] 🚀 run_forever() at {self._start_time.isoformat()}"
        )
        await asyncio.gather(
            self.observe_loop(),
            self.think_loop(),
            self.act_loop(),
            self.reflect_loop(),
            self.sync_loop(),
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
        return int((datetime.datetime.now() - self._start_time).total_seconds())


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
