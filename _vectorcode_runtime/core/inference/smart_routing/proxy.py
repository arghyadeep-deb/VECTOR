"""
VECTOR Smart Routing — OpenAI-Compatible Local Proxy
Python port of ClawRouter/src/proxy.ts

Runs an OpenAI-compatible HTTP proxy server that:
  1. Receives requests at http://localhost:8402/v1/chat/completions
  2. Classifies request complexity (15-dim scoring)
  3. Checks request cache (SHA-256, 30s TTL)
  4. Compresses context (7 layers, 15-40% savings)
  5. Routes to cheapest capable model
  6. Executes with fallback chain
  7. Returns OpenAI-compatible response

Any OpenAI SDK client can use this proxy with base_url="http://localhost:8402".
Use model="blockrun/auto" for smart routing, or any specific model ID.

Usage:
    server = SmartRoutingProxy()
    asyncio.run(server.start())  # starts on port 8402

    # From any client:
    # client = OpenAI(base_url="http://localhost:8402", api_key="vector")
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Optional

from core.config import CONFIG
from core.inference.smart_routing.classifier import classify, Tier
from core.inference.smart_routing.model_catalog import cheapest_for_tier, fallback_chain_for, MODEL_ALIASES
from core.inference.smart_routing.compressor import compress, should_compress
from core.inference.smart_routing.request_cache import get_cache
from core.inference.smart_routing.fallback_chain import execute_with_fallback
from core.inference.smart_routing.stats import get_journal
from loguru import logger

_DEFAULT_PORT = 8402
_AUTO_MODEL   = "blockrun/auto"


class SmartRoutingProxy:
    """
    OpenAI-compatible local proxy with smart routing.
    Uses FastAPI (if available) or built-in http.server as fallback.
    """

    def __init__(
        self,
        port: int | None = None,
        profile: str = "auto",
    ) -> None:
        cfg = CONFIG.get("smart_routing", {})
        self._port    = port or cfg.get("proxy_port", _DEFAULT_PORT)
        self._profile = profile
        self._cache   = get_cache()
        self._journal = get_journal()

    # ── Request routing logic ─────────────────────────────────────────────────

    async def handle_chat_completion(self, body: dict) -> dict:
        """Process a chat completion request with smart routing."""
        messages  = body.get("messages", [])
        model_req = body.get("model", _AUTO_MODEL)
        max_tokens = body.get("max_tokens", 2048)
        stream    = body.get("stream", False)

        # Resolve alias
        model_req = MODEL_ALIASES.get(model_req, model_req)

        # Check cache first
        cache_key = self._cache.cache_key(messages, model=model_req)
        if not stream:
            cached = await self._cache.get(cache_key)
            if cached:
                logger.debug("[VECTOR][proxy] cache hit for {}", model_req)
                return cached

        # Smart routing if model is "auto"
        selected_model = model_req
        routing_decision = None
        if model_req in (_AUTO_MODEL, "auto"):
            user_text = " ".join(
                m.get("content", "") if isinstance(m.get("content"), str) else ""
                for m in messages if m.get("role") == "user"
            )
            routing_decision = classify(user_text, max_tokens=max_tokens, profile=self._profile)
            tier = routing_decision.tier or Tier.MEDIUM
            needs_tools = bool(body.get("tools"))
            selected_model = cheapest_for_tier(tier, self._profile, needs_tools=needs_tools) or "google/gemini-2.5-flash"
            logger.info("[VECTOR][proxy] routed {} → {} ({})", model_req, selected_model, tier.value)

        # Compress context if large
        if should_compress(messages):
            compression = compress(messages)
            messages = compression.messages
            logger.debug("[VECTOR][proxy] compressed {:.0%} tokens saved", compression.savings_pct)

        # Build fallback chain
        fallbacks = fallback_chain_for(routing_decision.tier if routing_decision else Tier.MEDIUM, self._profile)[1:]

        # Execute with fallback
        start = time.time()
        try:
            response = await execute_with_fallback(
                primary_model=selected_model,
                fallback_models=fallbacks[:4],
                call_fn=lambda m: self._call_provider(m, {**body, "messages": messages, "model": m}),
            )
        except RuntimeError as e:
            return {"error": {"message": str(e), "type": "routing_error"}}

        latency_ms = int((time.time() - start) * 1000)

        # Cache successful response
        if not stream:
            await self._cache.set(cache_key, response)

        # Log stats
        usage = response.get("usage", {})
        from core.inference.smart_routing.model_catalog import estimate_cost, baseline_cost
        tokens_in  = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        cost       = estimate_cost(selected_model, tokens_in, tokens_out)
        base_cost  = baseline_cost(tokens_in, tokens_out)
        self._journal.log(
            model=selected_model,
            tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost, baseline_usd=base_cost,
            latency_ms=latency_ms,
            tier=routing_decision.tier.value if routing_decision and routing_decision.tier else "MEDIUM",
            profile=self._profile,
            method=routing_decision.method if routing_decision else "direct",
        )

        return response

    async def _call_provider(self, model: str, body: dict) -> dict:
        """Call the actual LLM provider for a given model."""
        from core.inference.provider_client import chat
        messages = body.get("messages", [])
        # Map to our internal inference format
        response_text = chat(model=model, messages=messages, timeout=60.0)
        # Return in OpenAI format
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens":     sum(len((m.get("content") or "").split()) for m in messages),
                "completion_tokens": len((response_text or "").split()),
                "total_tokens":      0,
            },
        }

    # ── HTTP server ───────────────────────────────────────────────────────────

    async def start(self, host: str = "127.0.0.1") -> None:
        """Start the proxy server. Prefers FastAPI, falls back to aiohttp."""
        try:
            await self._start_fastapi(host)
        except ImportError:
            await self._start_builtin(host)

    async def _start_fastapi(self, host: str) -> None:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        import uvicorn

        app = FastAPI(title="VECTOR Smart Routing Proxy")

        @app.post("/v1/chat/completions")
        async def chat_completions(request: Request):
            body = await request.json()
            result = await self.handle_chat_completion(body)
            return JSONResponse(result)

        @app.get("/v1/models")
        async def list_models():
            from core.inference.smart_routing.model_catalog import MODEL_CATALOG
            return JSONResponse({
                "data": [{"id": mid, "object": "model"} for mid in MODEL_CATALOG],
                "object": "list",
            })

        @app.get("/health")
        async def health():
            return JSONResponse({"status": "ok", "port": self._port})

        logger.info("[VECTOR][proxy] starting on http://{}:{}", host, self._port)
        config = uvicorn.Config(app, host=host, port=self._port, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()

    async def _start_builtin(self, host: str) -> None:
        """Minimal fallback using asyncio streams."""
        from aiohttp import web

        async def handle(request):
            body = await request.json()
            result = await self.handle_chat_completion(body)
            return web.json_response(result)

        app = web.Application()
        app.router.add_post("/v1/chat/completions", handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, self._port)
        logger.info("[VECTOR][proxy] starting (aiohttp) on http://{}:{}", host, self._port)
        await site.start()
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        proxy = SmartRoutingProxy()
        print(f"OK proxy.py — OpenAI-compatible smart routing proxy")
        print(f"  port: {proxy._port}")
        print(f"  profile: {proxy._profile}")
        print(f"  Start: await SmartRoutingProxy().start()")
        print(f"  Use:   OpenAI(base_url='http://localhost:{proxy._port}', api_key='vector')")
        print(f"  Model: 'blockrun/auto' → smart routing, or any model ID directly")

    asyncio.run(_smoke())
