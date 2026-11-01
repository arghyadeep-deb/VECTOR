"""ModelRouter -- what cli.py, repl.py and engine/agent_loop.py import as ``from providers import ModelRouter``.

The class did not exist anywhere (the import raised ImportError: `vector models` crashed, the agent loop died
before its first model call). This is a small, honest implementation:

* bare names and ``ollama/<model>`` -> the local Ollama daemon, with tool calling;
* explicit cloud IDs -> the user's credential and ProviderClient coding transport;
  tool proposals return to the coding engine's existing approval/execution path.

``complete()`` returns an object shaped like the transport layer's result:
``.message.content``, ``.message.tool_calls``, ``.finish_reason``, ``.usage``.
"""
from __future__ import annotations

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
    from vectorcode.src.image_attachments import ollama_content

    out = []
    for m in messages:
        role = m.get("role", "user")
        raw_content = m.get("content") or ""
        content, images = ollama_content(raw_content) if isinstance(raw_content, list) else (str(raw_content), [])
        if images and role != "user":
            raise ValueError("Native images are supported on user turns only.")
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
            out.append({"role": "assistant", "content": content, "tool_calls": calls})
        elif role == "tool":
            out.append({"role": "tool", "content": content, "tool_name": m.get("name", "")})
        else:
            out.append({"role": role, "content": content, **({"images": images} if images else {})})
    return out


def _result(content: str, tool_calls: list, finish_reason: str, prompt: int, completion: int) -> Any:
    return SimpleNamespace(
        message=SimpleNamespace(content=content, tool_calls=tool_calls),
        finish_reason=finish_reason,
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion, cached_tokens=0),
    )


class ModelRouter:
    def __init__(self, project_dir: Optional[Any] = None, *, timeout_sec: Optional[float] = None,
                 local_only: bool = False) -> None:
        self.project_dir = project_dir
        self.timeout_sec = timeout_sec
        self.local_only = local_only
        self.local_host = None
        if local_only:
            from ipaddress import ip_address
            from urllib.parse import urlsplit
            from core.config import CONFIG
            host = CONFIG["ollama_host"]
            try:
                url = urlsplit(host)
                loopback = url.hostname == "localhost" or ip_address(url.hostname).is_loopback
                if (not loopback or url.scheme not in {"http", "https"} or url.username or url.password
                        or url.path not in {"", "/"} or url.query or url.fragment):
                    raise ValueError
                if url.port is not None and not 1 <= url.port <= 65535:
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError("Predictive completion requires a loopback Ollama endpoint.") from None
            self.local_host = host

    # -- completion -------------------------------------------------------------------------
    def complete(self, model_id: str, messages: list, tools: Optional[list] = None,
                 stream: bool = False, max_tokens: Optional[int] = None, on_delta=None,
                 response_schema: Optional[dict] = None) -> Any:
        provider, model = split_model_id(model_id)
        if not provider or not model.strip():
            raise ValueError('Select a non-empty provider/model ID.')
        from vectorcode.src.image_attachments import content_has_images, image_context_bytes
        if any(content_has_images(message.get("content")) for message in messages):
            if provider != "ollama":
                raise ValueError("Image conversations require a local Ollama model.")
            if not self.local_only:
                return ModelRouter(project_dir=self.project_dir, timeout_sec=self.timeout_sec, local_only=True).complete(
                    model_id, messages, tools, stream=stream, max_tokens=max_tokens, on_delta=on_delta,
                    response_schema=response_schema)
            image_context_bytes(messages)
        if self.local_only and provider != "ollama":
            raise ValueError("This request permits local Ollama transport only.")
        if provider == "ollama":
            return self._complete_ollama(model, messages, tools, on_delta, max_tokens=max_tokens,
                                         response_schema=response_schema)
        if response_schema is not None:
            raise ValueError("Structured coding suggestions currently require Ollama.")
        return self._complete_provider(provider, model, messages, tools, max_tokens, on_delta)

    def _ollama_client_options(self):
        from core.config import CONFIG
        options = {"timeout": self.timeout_sec if self.timeout_sec is not None
                   else CONFIG["vectorcode"]["timeout_sec"]}
        if self.local_only:
            options.update(host=self.local_host, trust_env=False, follow_redirects=False)
        return options

    def local_capabilities(self, model_id: str):
        """Read local daemon metadata, without prompts, images, credentials or inference."""
        provider, model = split_model_id(model_id)
        if provider != "ollama":
            raise ValueError("Local model metadata requires an Ollama model.")
        if not self.local_only:
            return ModelRouter(project_dir=self.project_dir, timeout_sec=self.timeout_sec,
                               local_only=True).local_capabilities(model_id)
        import ollama
        with ollama.Client(**self._ollama_client_options()) as client:
            response = client.show(model=model)
        capabilities = response.get("capabilities") if hasattr(response, "get") else getattr(response, "capabilities", None)
        return frozenset(capabilities) if isinstance(capabilities, list) and all(
            isinstance(item, str) for item in capabilities) else None

    def _complete_ollama(self, model: str, messages: list, tools: Optional[list], on_delta=None,
                         max_tokens: Optional[int] = None, response_schema: Optional[dict] = None) -> Any:
        import ollama
        from core.config import CONFIG

        kwargs: dict = {"model": model, "messages": _to_ollama_messages(messages), "stream": False}
        kwargs["options"] = {"num_ctx": CONFIG["vectorcode"]["local_context_tokens"]}
        if max_tokens is not None:
            kwargs["options"]["num_predict"] = max_tokens
        if response_schema is not None:
            kwargs["format"] = response_schema
        kwargs["think"] = CONFIG["vectorcode"]["local_thinking"]
        if tools:
            kwargs["tools"] = tools
        with ollama.Client(**self._ollama_client_options()) as client:
            if on_delta:
                from vectorcode.src.transports.streaming import ollama_response
                resp = ollama_response(client, kwargs, on_delta)
            else:
                resp = client.chat(**kwargs)
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
        return _result(get("content", "") or "", calls, rget("done_reason", "tool_calls" if calls else "stop"),
                       rget("prompt_eval_count", 0) or 0, rget("eval_count", 0) or 0)

    def _complete_provider(self, provider: str, model: str, messages: list,
                           tools: Optional[list], max_tokens: Optional[int], on_delta=None) -> Any:
        from core.config import CONFIG
        from core.inference.provider_client import ProviderClient
        from vectorcode.src.providers.coding_catalog import get_coding_provider
        from vectorcode.src.providers.user_keys import resolve_user_key

        definition = get_coding_provider(provider)
        if definition is None:
            raise ValueError(f"Unknown provider '{provider}'.")
        result = ProviderClient(timeout=CONFIG['vectorcode']['timeout_sec']).coding_chat(
            definition, model, messages, tools, api_key=resolve_user_key(provider),
            max_tokens=max_tokens or 4096, **({'on_delta': on_delta} if on_delta else {}),
        )
        calls = [{'id': tc.id, 'name': tc.name, 'arguments': tc.arguments,
                  **({'provider_data': tc.provider_data} if tc.provider_data else {})}
                 for tc in result.tool_calls or []]
        usage = result.usage
        return _result(result.content or '', calls, result.finish_reason,
                       usage.prompt_tokens if usage else 0, usage.completion_tokens if usage else 0)

    # -- diagnostics ------------------------------------------------------------------------
    def test_connection(self, model_id: str) -> dict:
        """{'ok': bool, 'latency_ms': int, 'response'|'error': str} -- used by `vector models test`."""
        t0 = time.perf_counter()
        try:
            from core.loop.context_engine import ContextEngine
            hydration = ContextEngine().session_hydration_prompt({'model': model_id})
            r = self.complete(model_id, [{'role': 'system', 'content': hydration},
                                         {"role": "user", "content": "Reply with exactly: OK"}])
            ms = int((time.perf_counter() - t0) * 1000)
            text = (r.message.content or "").strip()
            return {"ok": bool(text), "latency_ms": ms, "response": text[:80]}
        except Exception as exc:
            return {"ok": False, "latency_ms": int((time.perf_counter() - t0) * 1000), "error": str(exc)[:200]}
