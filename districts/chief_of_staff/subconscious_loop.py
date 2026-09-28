"""
Subconscious Loop — cron-driven LLM situation assessment.
Every 30min: compare VECTOR world state vs last situation report -> act/escalate/noop.
Based on openhuman pattern.
"""

import asyncio
from datetime import datetime

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

class SubconsciousLoop(AgentBase):
    """Cron-driven background reflection -- compares state, decides escalation."""

    INTERVAL_MINUTES = 30

    def __init__(self):
        super().__init__(agent_id="subconscious_001", name="SubconsciousLoop", district="chief_of_staff")
        self._last_report: str = ""
        self._last_run: datetime | None = None

    async def run_once(self) -> dict:
        """One iteration: assess situation, decide action."""
        try:
            from core.loop.context_engine import ContextEngine
            ctx = ContextEngine()
            world_state = ctx.get_world_state() if hasattr(ctx, 'get_world_state') else {}

            # Build situation summary
            situation = f"Time: {datetime.now().isoformat()}\n"
            situation += f"World: {str(world_state)[:500]}\n"
            situation += f"Last: {self._last_report[:200] if self._last_report else 'none'}\n"

            # Ask LLM: what changed? what to do?
            from core.inference.provider_client import get_client
            client = get_client()
            prompt = f"""You are VECTOR's subconscious reflection layer.
Compare the current situation with the last report and decide:
- 'noop' -- nothing significant changed
- 'act:<action>' -- VECTOR should do something specific
- 'escalate:<reason>' -- alert the owner

Current situation:
{situation}

Respond with just: noop | act:<action> | escalate:<reason>"""

            # ProviderClient.complete() is single-turn: `prompt` is its first positional argument and there is no
            # `messages=`. This call used the chat-style shape, so every run raised "missing 1 required positional
            # argument: 'prompt'" and the subconscious layer never once reasoned (found by the 2026-09-26 loop watch).
            response = await client.complete(
                prompt,
                model=CONFIG.get("models", {}).get("focus", "vector-focus"),
                max_tokens=100,
                caller_id="subconscious_loop",
                district="chief_of_staff",
            )
            decision = (response.content or "noop").strip().lower()
            self._last_report = situation
            self._last_run = datetime.now()

            logger.info("[VECTOR][subconscious] Decision: {}", decision)
            self.award_points(3, "subconscious_ran")
            return {"decision": decision, "timestamp": self._last_run.isoformat()}
        except Exception as e:
            logger.error("[VECTOR][subconscious] Error: {}", e)
            self.deduct_points(2, "subconscious_failed")
            return {"decision": "noop", "error": str(e)}

    async def loop_forever(self):
        """Run every INTERVAL_MINUTES forever."""
        while True:
            result = await self.run_once()
            logger.info("[VECTOR][subconscious] {}", result)
            await asyncio.sleep(self.INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    s = SubconsciousLoop()
    print("OK subconscious_loop OK" if s else "FAILED")
