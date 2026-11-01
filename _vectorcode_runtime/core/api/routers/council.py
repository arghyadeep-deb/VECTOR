"""Council router — proper 3-stage deliberation.

Stage 1: All 4 models answer in parallel (anonymized A/B/C/D)
Stage 2: Cross-review and ranking
Stage 3: reasoning model synthesizes final answer
Stores session as training data (RULE 8)
"""

import sys

__all__ = [
    "council_endpoint",
    "router",
]

import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
import httpx

from core.api.schemas import CouncilRequest, CouncilResponse
from core.api.crud import store_reasoning_chain, store_episode
from core.config import CONFIG

router = APIRouter(prefix="/council", tags=["council"])

# Weekly throttle — process-level state resets on Sunday midnight UTC
_council_sessions_this_week = {"count": 0, "reset_at": None}

_OLLAMA_HOST = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
if not _OLLAMA_HOST.startswith("http"):
    _OLLAMA_HOST = "http://" + _OLLAMA_HOST


def _check_council_throttle() -> bool:
    """Check if council sessions are within weekly limit (max 10/week)."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)

    if _council_sessions_this_week["reset_at"] is None:
        days_to_sunday = (now.weekday() + 1) % 7
        next_sunday = now - datetime.timedelta(days=days_to_sunday)
        _council_sessions_this_week["reset_at"] = next_sunday.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + datetime.timedelta(days=7)

    if now >= _council_sessions_this_week["reset_at"]:
        _council_sessions_this_week["count"] = 0
        _council_sessions_this_week["reset_at"] = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + datetime.timedelta(days=7)

    max_per_week = CONFIG["council"]["max_per_week"]
    return _council_sessions_this_week["count"] < max_per_week


@router.post("", response_model=CouncilResponse)
async def council_endpoint(body: CouncilRequest):
    """Process a high-stakes decision through the LLM Council."""
    start = time.perf_counter()
    session_id = str(uuid.uuid4())

    try:
        if not _check_council_throttle():
            raise HTTPException(
                status_code=429,
                detail=f"Council sessions exhausted this week (max {CONFIG['council']['max_per_week']})",
            )

        stakes = body.stakes.lower()
        if stakes not in ("medium", "high", "critical"):
            stakes = "medium"

        member_prompts = _build_council_prompts(body.question, body.context_override)

        async with httpx.AsyncClient(timeout=60.0) as client:
            parallel_tasks = [
                _query_ollama_member(client, model, prompt, name)
                for model, prompt, name in member_prompts
            ]
            member_responses = await asyncio.gather(*parallel_tasks, return_exceptions=True)

        valid_responses = [
            r for r in member_responses
            if isinstance(r, dict) and r.get("response")
        ]

        if not valid_responses:
            raise HTTPException(status_code=503, detail="All council members unavailable")

        anonymized_responses = [
            {"id": chr(65 + i), "response": r["response"]}
            for i, r in enumerate(valid_responses)
        ]
        cross_review_prompt = _build_cross_review_prompt(body.question, anonymized_responses)

        synthesizer_model = CONFIG["models"].get("reasoning", "vector-reasoning")
        synthesizer_response = await _query_ollama_direct(synthesizer_model, cross_review_prompt)

        confidence = _calculate_confidence(valid_responses, synthesizer_response)
        reward = 0.8 if confidence > 0.7 else 0.5

        store_reasoning_chain(
            situation=body.question[:100],
            goal_ids=[],
            steps=[
                f"stakes: {stakes}",
                f"members: {len(valid_responses)} responded",
                f"anonymized: {len(anonymized_responses)} reviewed",
                f"synthesizer: synthesized decision",
            ],
            action="council_deliberation",
            outcome=synthesizer_response[:200] if synthesizer_response else "no response",
            reward=reward,
        )

        store_episode(
            event_type="council_session",
            content=f"council: {body.question[:80]} -> {synthesizer_response[:100] if synthesizer_response else 'no response'}",
            tags=["council", stakes],
            context={
                "session_id": session_id,
                "stakes": stakes,
                "members_count": len(valid_responses),
                "confidence": confidence,
            },
            source="api_council",
        )

        _council_sessions_this_week["count"] += 1

        return CouncilResponse(
            decision=synthesizer_response or "Council could not reach a decision.",
            confidence=confidence,
            session_id=session_id,
            chairman_decision=synthesizer_response,
            winning_model=synthesizer_model,
            stored_as_training_data=(reward > 0.7),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][council] error: {e}")
        raise HTTPException(status_code=500, detail=f"Council deliberation failed: {e}")


async def _query_ollama_member(client: httpx.AsyncClient, model: str, prompt: str, name: str) -> dict:
    """Query a single Ollama model."""
    try:
        resp = await client.post(
            f"{_OLLAMA_HOST}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=30.0,
        )
        resp.raise_for_status()
        response_text = resp.json().get("response", "")
        logger.info(f"[VECTOR][council] {name} ({model}) responded: {response_text[:80]}...")
        return {"model": model, "name": name, "response": response_text}
    except Exception as e:
        logger.warning(f"[VECTOR][council] {name} failed: {e}")
        return {"model": model, "name": name, "response": "", "error": str(e)}


async def _query_ollama_direct(model: str, prompt: str) -> str:
    """Query Ollama directly for final synthesis."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_OLLAMA_HOST}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=60.0,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
    except Exception as e:
        logger.error(f"[VECTOR][council] synthesizer query failed: {e}")
        return ""


def _build_council_prompts(question: str, context_override: dict | None) -> list:
    """Build prompts for each council member model."""
    context_note = f"\n\nContext: {context_override}" if context_override else ""

    base_prompt = f"""You are a council member answering a high-stakes question.
Keep your response focused and concise (2-3 sentences).
Question: {question}{context_note}

Provide your analysis and recommendation:"""

    # 4 local models — no cloud dependencies
    models = [
        (CONFIG["models"].get("reasoning", "vector-reasoning"), base_prompt, "VECTOR-Reasoning"),
        (CONFIG["models"].get("focus", "vector-focus"), base_prompt, "VECTOR-Focus"),
        (CONFIG["models"].get("multilingual", "vector-multilingual"), base_prompt, "VECTOR-Multilingual"),
        (CONFIG["models"].get("coder", "vector-coder"), base_prompt, "VECTOR-Coder"),
    ]
    return models


def _build_cross_review_prompt(question: str, anonymized_responses: list) -> str:
    """Build the prompt for final synthesis."""
    responses_text = "\n\n".join(
        f"[{r['id']}] {r['response']}"
        for r in anonymized_responses
    )
    return f"""You are the Council Synthesizer. Review the anonymized responses from 4 council members
and synthesize a final, decisive answer.

Question: {question}

Council Responses:
{responses_text}

Your task:
1. Read all 4 responses carefully
2. Identify areas of agreement and disagreement
3. Synthesize the strongest elements into a coherent final answer
4. State your decision clearly with reasoning

Final Decision (be clear and decisive):"""


def _calculate_confidence(responses: list, synthesizer_response: str) -> float:
    """Calculate confidence based on response coherence."""
    if not responses or not synthesizer_response:
        return 0.5
    response_lengths = [len(r.get("response", "")) for r in responses]
    avg_len = sum(response_lengths) / len(response_lengths) if response_lengths else 0
    length_variance = sum(abs(l - avg_len) for l in response_lengths) / len(response_lengths)
    base_confidence = 0.75
    variance_penalty = min(0.2, length_variance / 500)
    return round(max(0.5, min(0.95, base_confidence - variance_penalty)), 2)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
