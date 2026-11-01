"""Minimal OpenAI-compatible VECTOR gateway."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.inference.llm_providers import PROVIDERS
from core.inference.provider_client import ProviderClient

router = APIRouter(prefix="/v1", tags=["openai-compatible"])


@router.get("/models")
async def list_models() -> dict[str, Any]:
    data = []
    for provider in PROVIDERS.values():
        for model in provider.models or [provider.default_model]:
            data.append({
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": provider.slug,
            })
    return {"object": "list", "data": data}


async def _sse_chunks(result, completion_id: str, created: int) -> AsyncIterator[str]:
    """Frame an already-fetched ProviderClient result as OpenAI-compatible
    SSE chunks. Buffered, not token-by-token — VECTOR's provider layer
    (core/inference/provider_client.py) has no per-provider streaming
    support across its ~27 backends; rewiring all of them is real, separate,
    much larger work (see docs/repo_analysis/_MASTER_TODO.md). This still
    satisfies the actual goal — "so Open WebUI... can talk to VECTOR" — by
    emitting valid SSE framing a real streaming client can consume, just
    delivered as one content chunk instead of incremental token deltas.
    """
    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": result.model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": result.content},
            "finish_reason": None,
        }],
    }
    yield f"data: {json.dumps(chunk)}\n\n"

    final_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": result.model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": result.finish_reason,
        }],
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(payload: dict[str, Any]):
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list")
    from core.loop.context_engine import ContextEngine
    hydration = ContextEngine().session_hydration_prompt()
    hydrated_messages = [
        {"role": "system", "content": hydration},
        *messages,
    ]
    model = payload.get("model")
    client = ProviderClient()
    result = await client.chat(
        messages=hydrated_messages,
        model=model,
        temperature=float(payload.get("temperature", 0.7)),
        max_tokens=int(payload.get("max_tokens", 4096)),
        caller_id="openai_compat",
    )

    if payload.get("stream"):
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        return StreamingResponse(
            _sse_chunks(result, completion_id, created),
            media_type="text/event-stream",
        )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": result.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result.content},
            "finish_reason": result.finish_reason,
        }],
        "usage": {
            "prompt_tokens": result.input_tokens,
            "completion_tokens": result.output_tokens,
            "total_tokens": result.input_tokens + result.output_tokens,
        },
        "vector_provider": result.provider,
    }
