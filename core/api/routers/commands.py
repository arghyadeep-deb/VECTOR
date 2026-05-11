"""Command router — routes through full intelligence stack.

Pipeline (wired per Architecture.md Rule 1, 3, 6, 7, 8):
1. ContextEngine.session_hydration_prompt()   (RULE 1)
2. GoalSystem.generate_immediate_actions()     (RULE 6)
3. DecisionEngine.evaluate(candidates)         (5-factor formula)
4. PermissionGateway.execute(action)          (RULE 3)
5. PolicyMemory.update_from_outcome()        (RULE 7)
6. ReasoningMemory.store_chain()             (RULE 8)
7. EpisodicMemory.store()                     (episode log)
"""

import sys
import asyncio
import time
import hashlib
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from core.config import CONFIG

from core.api.schemas import CommandRequest, CommandResponse
from core.api.dependencies import (
    get_context_engine, get_decision_engine,
    get_permission_gateway, get_episodic_memory,
)
from core.api.crud import store_episode, update_policy, store_reasoning_chain

router = APIRouter(prefix="/command", tags=["commands"])

START_TIME_DICT = {"time": None}


def _make_situation_hash(params: dict) -> str:
    key = json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _init_start_time():
    import datetime
    if START_TIME_DICT["time"] is None:
        START_TIME_DICT["time"] = datetime.datetime.now(datetime.timezone.utc)
    return START_TIME_DICT["time"]


@router.post("", response_model=CommandResponse)
async def command_endpoint(
    body: CommandRequest,
    ctx_engine=Depends(get_context_engine),
    decision_engine=Depends(get_decision_engine),
    perm_gateway=Depends(get_permission_gateway),
    episodic_mem=Depends(get_episodic_memory),
):
    """Process a command through the full intelligence stack."""
    start = time.perf_counter()

    try:
        # Step 1: Get session hydration context (RULE 1)
        hydration = ctx_engine.session_hydration_prompt()

        # Step 2: Generate candidate actions from goal system (RULE 6)
        from core.brain.goal_system import GoalSystem
        goal_system = GoalSystem()
        raw_actions = goal_system.generate_immediate_actions(limit=4)

        # Step 3: Check for user intent from their text
        intent_action = _detect_intent_action(body.text)

        # Build decision candidates
        from core.loop.decision_engine import Candidate
        candidates = []

        # Add goal-driven candidates
        for a in raw_actions:
            candidates.append(Candidate(
                action_type=a["action"],
                params={"goal_id": a["goal_id"], "title": a.get("title", "")},
                goal_ids=[a["goal_id"]],
                urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(a.get("urgency", "medium"), 0.5),
                confidence=0.7,
                source="goal_system",
            ))

        # Add user intent as highest-priority candidate
        if intent_action:
            candidates.insert(0, Candidate(
                action_type=intent_action["action_type"],
                params=intent_action.get("params", {"query": body.text}),
                goal_ids=[],
                urgency=0.9,
                confidence=0.85,
                source="user_intent",
            ))

        if not candidates:
            return CommandResponse(
                response="I don't have any actions to take right now.",
                candidates_evaluated=0,
                memory_updated=False,
                processing_ms=int((time.perf_counter() - start) * 1000),
            )

        # Step 4: Evaluate candidates through decision engine
        decision = await decision_engine.evaluate(candidates)

        # Step 5: Route through permission gateway (RULE 3)
        from core.loop.permission_gateway import Action
        action = Action(
            action_type=decision.winner.action_type,
            params=decision.winner.params,
            proposed_by="api_command",
        )
        gateway_result = await perm_gateway.execute(action)

        # Step 6: Update policy from outcome (RULE 7)
        situation_hash = _make_situation_hash(decision.winner.params)
        reward = 0.8 if gateway_result.approved else 0.2
        policy_mem.update_from_outcome(decision.winner.action_type, situation_hash, reward)

        # Step 7: Store reasoning chain (RULE 8)
        chain_id = store_reasoning_chain(
            situation=body.text[:100],
            goal_ids=decision.winner.goal_ids,
            steps=[
                f"user_input: {body.text[:50]}",
                f"candidates: {len(candidates)} evaluated",
                f"winner: {decision.winner.action_type}",
                f"gateway: {gateway_result.level} {'approved' if gateway_result.approved else 'denied'}",
            ],
            action=decision.winner.action_type,
            outcome=gateway_result.result.get("status", "completed"),
            reward=reward,
        )

        # Step 8: Store the episode in memory
        episodic_mem.store(
            event_type="api_command",
            content=f"command: {body.text[:80]} -> winner: {decision.winner.action_type} "
                    f"score={decision.winner.total_score:.3f} gateway={gateway_result.level}",
            tags=["command", decision.winner.action_type, gateway_result.level],
            context={
                "user_text": body.text,
                "winner_score": decision.winner.total_score,
                "candidates_count": decision.evaluated,
                "gateway_level": gateway_result.level,
                "chain_id": chain_id,
            },
            source="api_command",
        )

        # Build response
        response_text = _build_response_text(gateway_result, decision.winner, body.text)

        return CommandResponse(
            response=response_text,
            action_taken=decision.winner.action_type if gateway_result.executed else None,
            candidates_evaluated=decision.evaluated,
            winner_score=decision.winner.total_score,
            memory_updated=True,
            processing_ms=int((time.perf_counter() - start) * 1000),
        )

    except Exception as e:
        logger.error(f"[VECTOR][api][command] error: {e}")
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return CommandResponse(
            response="An error occurred processing your command.",
            candidates_evaluated=0,
            memory_updated=False,
            processing_ms=elapsed_ms,
        )


def _detect_intent_action(text: str) -> dict | None:
    """Detect user intent from text and map to action."""
    text_lower = text.lower()

    intent_map = [
        (["check", "attendance", "kiit"], "check_attendance", {}),
        (["weather", "temperature"], "check_weather", {}),
        (["remind", "reminder", "set alarm"], "set_reminder", {}),
        (["search", "find", "look up"], "search_web", {"query": text_lower}),
        (["commit", "git commit"], "commit_code", {}),
        (["schedule", "calendar", "class"], "read_calendar", {}),
        (["timer", "countdown"], "set_timer", {}),
        (["screenshot", "capture screen"], "take_screenshot", {}),
        (["music", "play"], "play_music", {}),
    ]

    for keywords, action, params in intent_map:
        if any(kw in text_lower for kw in keywords):
            return {"action_type": action, "params": params}

    return {"action_type": "respond", "params": {"message": text}}


def _build_response_text(gw_result, winner, original_text: str) -> str:
    """Build human-readable response text."""
    if gw_result.level == "FORBIDDEN":
        return "That action is permanently blocked."

    if gw_result.level == "GREEN" and gw_result.executed:
        return f"Done. {winner.action_type} executed successfully."

    if gw_result.level == "YELLOW" and gw_result.executed:
        return f"Executed: {winner.action_type}. You'll be notified."

    if gw_result.level == "RED":
        if gw_result.approved:
            return f"Confirmed and executed: {winner.action_type}."
        else:
            return f"Waiting for your confirmation on: {winner.action_type}."

    if gw_result.level == "UNKNOWN":
        return f"I couldn't determine the action type for: {original_text[:50]}"

    return f"Processed: {winner.action_type}"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
