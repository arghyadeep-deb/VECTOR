"""HandRunner — executes one Hand end-to-end: hydrate context, dispatch
through the governor (gated by PermissionGateway when the Hand requires
approval), close the loop (episodic memory + HP + policy reward), persist
the result. Never raises (RULE 2) — a crashing Hand returns an error
HandResult so the scheduler can keep firing the others.
"""
from __future__ import annotations

import asyncio
import inspect

from loguru import logger

from hands.registry import Hand
from hands.result import HandResult

# Per-hand timeout — model-heavy hands (cold Ollama load measured ~58-130s
# this session) need real margin; lightweight hands don't need to wait that
# long to fail.
_DEFAULT_TIMEOUT_SEC = 180


class HandRunner:
    def __init__(self):
        pass

    def _task_type_for(self, hand: Hand) -> str:
        """Task type passed to the governor. Phase 2 will map specific
        hands to specific routes (e.g. researcher -> deep_research); for
        now this defaults to the hand's own name, which is a valid
        fallback task_type the governor's route_task() can classify."""
        return hand.name

    def _hydrate(self, hand: Hand, extra_context: dict) -> str:
        try:
            from core.loop.context_engine import ContextEngine
            world = ContextEngine().session_hydration_prompt(extra_context)
        except Exception as e:
            logger.warning("[VECTOR][hands] context hydration failed for {}: {}", hand.name, e)
            world = ""
        return f"{world}\n\n{hand.system_prompt}"

    async def _dispatch(self, hand: Hand, context: str):
        """Direct governor dispatch — the real work for hands that don't
        require approval. Stubbed in unit tests to prove run_hand's
        plumbing (memory/HP/policy) without needing live districts."""
        from core.city.governor import Governor
        task = {
            "type": self._task_type_for(hand),
            "district": hand.district,
            "params": {"context": context, "hand": hand.name},
        }
        return await Governor().dispatch(task)

    async def _dispatch_via_gateway(self, hand: Hand, context: str):
        """Approval-gated path for hand.requires_approval=True hands.
        Reuses the real PermissionGateway (RED-tier classification +
        CouncilBrain deliberation + Pushover owner approval, all already
        registered for hand_<name> action types in core/config.py) instead
        of duplicating that machinery here."""
        from core.loop.permission_gateway import PermissionGateway, Action
        task = {
            "type": self._task_type_for(hand),
            "district": hand.district,
            "params": {"context": context, "hand": hand.name},
        }
        action = Action(
            action_type=f"hand_{hand.name}",
            params={"task": task},
            proposed_by="hand_runner",
        )
        gw_result = await PermissionGateway().execute(action)
        if not gw_result.approved:
            raise PermissionError(f"hand '{hand.name}' not approved: {gw_result.reason}")
        return gw_result.result.get("dispatch_result", gw_result.result)

    def _record_episodic(self, hand: Hand, result: HandResult) -> None:
        try:
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store(
                event_type="hand_execution",
                content=f"Hand '{hand.name}' ({hand.district}) -> {result.status}: {result.output[:200]}",
                tags=["hand", hand.name, hand.district, result.status],
                source=hand.name,
            )
        except Exception as e:
            logger.warning("[VECTOR][hands] episodic record failed for {}: {}", hand.name, e)
        try:
            from core.memory.reasoning_memory import ReasoningMemory
            ReasoningMemory().store_chain(
                situation=f"hand:{hand.name}",
                goal_ids=[],
                steps=[{"action": "run_hand", "district": hand.district}],
                action=hand.name,
                outcome=result.status,
                reward=1.0 if result.status == "ok" else 0.0,
            )
        except Exception as e:
            logger.debug("[VECTOR][hands] reasoning_memory record skipped for {}: {}", hand.name, e)

    def _award_hp(self, hand: Hand, result: HandResult) -> None:
        try:
            from core.city.agent_registry import get_registry
            agents = get_registry().get_by_district(hand.district)
            if not agents:
                return
            agent = max(agents, key=lambda a: a.health_points)
            if result.status == "ok":
                agent.award_points(50, f"hand_run:{hand.name}")
                result.hp_delta = 50
            else:
                agent.deduct_points(30, f"hand_run_failed:{hand.name}")
                result.hp_delta = -30
        except Exception as e:
            logger.warning("[VECTOR][hands] HP award failed for {}: {}", hand.name, e)

    def _update_policy(self, hand: Hand, result: HandResult) -> None:
        try:
            from core.memory.policy import PolicyMemory
            import hashlib
            situation_hash = hashlib.sha256(f"hand:{hand.name}".encode()).hexdigest()[:12]
            reward = 1.0 if result.status == "ok" else 0.0
            PolicyMemory().update_from_outcome(hand.name, situation_hash, reward)
        except Exception as e:
            logger.warning("[VECTOR][hands] policy update failed for {}: {}", hand.name, e)

    async def run_hand(self, hand: Hand, extra_context: dict) -> HandResult:
        result: HandResult
        try:
            context = self._hydrate(hand, extra_context or {})

            async def _do_dispatch():
                if hand.requires_approval:
                    return await self._dispatch_via_gateway(hand, context)
                raw = self._dispatch(hand, context)
                if inspect.isawaitable(raw):
                    raw = await raw
                return raw

            if hand.name in MODEL_HEAVY_HANDS:
                async with self._model_lock:
                    async with asyncio.timeout(_DEFAULT_TIMEOUT_SEC):
                        output = await _do_dispatch()
            else:
                async with asyncio.timeout(_DEFAULT_TIMEOUT_SEC):
                    output = await _do_dispatch()

            result = HandResult(
                hand=hand.name, district=hand.district,
                output=str(output), status="ok",
            )
        except Exception as e:
            logger.error("[VECTOR][hands] {} failed: {}", hand.name, e)
            result = HandResult(
                hand=hand.name, district=hand.district,
                output="", status="error", error=str(e),
            )

        self._record_episodic(hand, result)
        self._award_hp(hand, result)
        self._update_policy(hand, result)
        try:
            result.persist()
        except Exception as e:
            logger.warning("[VECTOR][hands] result.persist() failed for {}: {}", hand.name, e)

        return result


if __name__ == "__main__":
    import asyncio as _asyncio
    from hands.registry import HandRegistry

    async def _smoke():
        runner = HandRunner()
        runner._dispatch = lambda h, c: "smoke test output"
        r = await runner.run_hand(HandRegistry().get("researcher"), {})
        assert r.status == "ok"
        assert r.output
        print("OK hands/runner.py")

    _asyncio.run(_smoke())
