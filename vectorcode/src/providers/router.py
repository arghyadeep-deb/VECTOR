"""ModelRouter -- what cli.py, repl.py and engine/agent_loop.py import as ``from providers import ModelRouter``.

The class did not exist anywhere (the import raised ImportError: `vector models` crashed, the agent loop died
before its first model call). This is a small, honest implementation:

* bare names and ``ollama/<model>`` -> the local Ollama daemon, with tool calling;
* ``<provider>/<model>`` for any other provider -> VECTOR's real multi-provider client
  (``core.inference.provider_client``). That path returns plain text only: tool calls are NOT supported
  there yet, so asking for tools raises instead of quietly dropping them.

``complete()`` returns an object shaped like the transport layer's result:
``.message.content``, ``.message.tool_calls``, ``.finish_reason``, ``.usage``.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from types import SimpleNamespace
from typing import Any, Optional


def split_model_id(model_id: str) -> tuple[str, str]:
    """'groq/llama-3' -> ('groq', 'llama-3'); 'vector-focus' -> ('ollama', 'vector-focus')."""
    if "/" not in model_id:
        return "ollama", model_id
    provider, _, model = model_id.partition("/")
    return provider.lower(), model


def _to_ollama_messages(messages: list) -> list:
    out = []
    for m in messages:
        role = m.get("role", "user")
        if role == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                fn = tc.get("function") or {}
                name = fn.get("name") or tc.get("name", "")
                args = fn.get("arguments", tc.get("arguments", {}))
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                calls.append({"function": {"name": name, "arguments": args or {}}})
            out.append({"role": "assistant", "content": m.get("content", "") or "", "tool_calls": calls})
        elif role == "tool":
            out.append({"role": "tool", "content": str(m.get("content", "")), "tool_name": m.get("name", "")})
        else:
            out.append({"role": role, "content": str(m.get("content", "") or "")})
    return out


def _result(content: str, tool_calls: list, finish_reason: str, prompt: int, completion: int) -> Any:
    return SimpleNamespace(
        message=SimpleNamespace(content=content, tool_calls=tool_calls),
        finish_reason=finish_reason,
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion, cached_tokens=0),
    )


class ModelRouter:
    def __init__(self, project_dir: Optional[Any] = None) -> None:
        self.project_dir = project_dir

    # -- completion -------------------------------------------------------------------------
    def complete(self, model_id: str, messages: list, tools: Optional[list] = None,
                 stream: bool = False, max_tokens: Optional[int] = None) -> Any:
        provider, model = split_model_id(model_id)
        if provider == "ollama":
            return self._complete_ollama(model, messages, tools)
        return self._complete_provider(provider, model, messages, tools, max_tokens)

    def _complete_ollama(self, model: str, messages: list, tools: Optional[list]) -> Any:
        import ollama

        kwargs: dict = {"model": model, "messages": _to_ollama_messages(messages), "stream": False}
        if tools:
            kwargs["tools"] = tools
        resp = ollama.chat(**kwargs)
        msg = resp.get("message", {}) if isinstance(resp, dict) else getattr(resp, "message", {})
        get = msg.get if isinstance(msg, dict) else (lambda k, d=None: getattr(msg, k, d))
        calls = []
        for tc in (get("tool_calls") or []):
            fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", {})
            fget = fn.get if isinstance(fn, dict) else (lambda k, d=None: getattr(fn, k, d))
            args = fget("arguments", {})
            calls.append({"id": uuid.uuid4().hex[:8], "name": fget("name", ""),
                          "arguments": json.dumps(args) if isinstance(args, dict) else str(args or "{}")})
        rget = resp.get if isinstance(resp, dict) else (lambda k, d=None: getattr(resp, k, d))
        return _result(get("content", "") or "", calls, "tool_calls" if calls else "stop",
                       rget("prompt_eval_count", 0) or 0, rget("eval_count", 0) or 0)

    def _complete_provider(self, provider: str, model: str, messages: list,
                           tools: Optional[list], max_tokens: Optional[int]) -> Any:
        if tools:
            raise NotImplementedError(
                f"provider '{provider}' is reached through VECTOR's multi-provider client, which returns text "
                "only; tool calling is only available on local Ollama models for now"
            )
        from core.inference.provider_client import get_client

        async def _call():
            return await get_client().chat(messages=messages, provider=provider, model=model,
                                           max_tokens=max_tokens or 4096)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            r = asyncio.run(_call())
        else:
            raise RuntimeError(
                "ModelRouter.complete() is synchronous and cannot be called from "
                "a running event loop"
            )
        return _result(getattr(r, "content", "") or "", [], getattr(r, "finish_reason", "stop"),
                       getattr(r, "input_tokens", 0), getattr(r, "output_tokens", 0))

    # -- diagnostics ------------------------------------------------------------------------
    def test_connection(self, model_id: str) -> dict:
        """{'ok': bool, 'latency_ms': int, 'response'|'error': str} -- used by `vector models test`."""
        t0 = time.perf_counter()
        try:
            r = self.complete(model_id, [{"role": "user", "content": "Reply with exactly: OK"}])
            ms = int((time.perf_counter() - t0) * 1000)
            text = (r.message.content or "").strip()
            return {"ok": bool(text), "latency_ms": ms, "response": text[:80]}
        except Exception as exc:
            return {"ok": False, "latency_ms": int((time.perf_counter() - t0) * 1000), "error": str(exc)[:200]}
