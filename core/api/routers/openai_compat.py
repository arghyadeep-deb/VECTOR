"""Minimal OpenAI-compatible VECTOR gateway."""
from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

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


@router.post("/chat/completions")
async def chat_completions(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("stream"):
        raise HTTPException(status_code=400, detail="streaming is not enabled on this compatibility endpoint yet")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list")
    model = payload.get("model")
    client = ProviderClient()
    result = await client.chat(
        messages=messages,
        model=model,
        temperature=float(payload.get("temperature", 0.7)),
        max_tokens=int(payload.get("max_tokens", 4096)),
        caller_id="openai_compat",
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
