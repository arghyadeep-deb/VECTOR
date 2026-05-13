"""Ollama transport for VectorCode.

Uses the ollama Python SDK directly for local model inference.
This transport is optimised for VECTOR's local-first rule (Rule 4 / Rule 11):
all runtime decisions use local Ollama models, never remote APIs.

Models in use: vector-focus (permanent VRAM), vector-coder, vector-reasoning,
               qwen3:14b, deepseek-r1:14b, devstral:24b, etc.
"""

# ── Guard: strip transports/ from sys.path to prevent types.py shadowing stdlib.
import sys
import os as _os
_this_dir = _os.path.dirname(_os.path.abspath(__file__))
sys.path = [p for p in sys.path if _os.path.abspath(p) != _this_dir]
del _os, _this_dir

# ── stdlib ────────────────────────────────────────────────────────────────────
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── sys.path inserts (exactly 2) ─────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))                       # vectorcode package

from loguru import logger
from transports.base import ProviderTransport            # type: ignore[import]
from transports.types import (                           # type: ignore[import]
    NormalizedResponse, ToolCall, Usage, build_tool_call,
)

try:
    from core.config import CONFIG  # type: ignore
except ImportError:
    CONFIG = {}

_OLLAMA_HOST: str = CONFIG.get("OLLAMA_HOST", "http://127.0.0.1:11434") if CONFIG else "http://127.0.0.1:11434"
_DEFAULT_CTX: int = 8192


class OllamaTransport(ProviderTransport):
    """Transport for api_mode='ollama'.

    Uses the ollama Python SDK. Accepts OpenAI-format messages and tools
    (ollama SDK is OpenAI-compatible at the message level).
    """

    def __init__(self, host: str = "") -> None:
        self._host = host or _OLLAMA_HOST

    @property
    def api_mode(self) -> str:
        return "ollama"

    def convert_messages(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> List[Dict[str, Any]]:
        """Identity: ollama accepts OpenAI-format messages."""
        return messages

    def convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identity: ollama accepts OpenAI-format tool definitions."""
        return tools

    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """Build ollama.chat() kwargs.

        params (all optional):
            num_ctx: int         — context length (default 8192)
            stream: bool         — default True
            temperature: float
            top_p: float
            seed: int
        """
        num_ctx: int = params.get("num_ctx", _DEFAULT_CTX)
        stream: bool = params.get("stream", True)

        options: Dict[str, Any] = {"num_ctx": num_ctx}
        if "temperature" in params:
            options["temperature"] = params["temperature"]
        if "top_p" in params:
            options["top_p"] = params["top_p"]
        if "seed" in params:
            options["seed"] = params["seed"]

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "options": options,
            "stream": stream,
        }
        if tools:
            kwargs["tools"] = tools

        return kwargs

    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize ollama response dict / object to NormalizedResponse."""
        # ollama SDK returns a dict or a ChatResponse object
        if isinstance(response, dict):
            msg = response.get("message", {})
            done_reason = response.get("done_reason", "stop")
        else:
            msg = getattr(response, "message", {})
            done_reason = getattr(response, "done_reason", "stop") or "stop"

        if isinstance(msg, dict):
            content = msg.get("content", "") or None
            raw_tool_calls = msg.get("tool_calls") or []
        else:
            content = getattr(msg, "content", "") or None
            raw_tool_calls = getattr(msg, "tool_calls", None) or []

        # Map done_reason to finish_reason
        _DONE_MAP: Dict[str, str] = {
            "stop": "stop",
            "length": "length",
            "tool_calls": "tool_calls",
            "tool_use": "tool_calls",
        }
        finish_reason = _DONE_MAP.get(done_reason or "stop", "stop")

        # Tool calls
        tool_calls: Optional[List[ToolCall]] = None
        if raw_tool_calls:
            tool_calls = []
            for tc in raw_tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    tc_id = tc.get("id")
                    fn_name = fn.get("name", "") if isinstance(fn, dict) else ""
                    fn_args = fn.get("arguments", {}) if isinstance(fn, dict) else {}
                else:
                    fn = getattr(tc, "function", None)
                    tc_id = getattr(tc, "id", None)
                    fn_name = getattr(fn, "name", "") if fn else ""
                    fn_args = getattr(fn, "arguments", {}) if fn else {}

                tool_calls.append(build_tool_call(tc_id, fn_name, fn_args))

            if tool_calls:
                finish_reason = "tool_calls"

        # Usage (ollama includes prompt_eval_count / eval_count)
        if isinstance(response, dict):
            prompt_tc = response.get("prompt_eval_count", 0) or 0
            comp_tc = response.get("eval_count", 0) or 0
        else:
            prompt_tc = getattr(response, "prompt_eval_count", 0) or 0
            comp_tc = getattr(response, "eval_count", 0) or 0

        usage = Usage(
            prompt_tokens=prompt_tc,
            completion_tokens=comp_tc,
            total_tokens=prompt_tc + comp_tc,
        ) if (prompt_tc or comp_tc) else None

        return NormalizedResponse(
            content=content,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
            usage=usage,
        )

    def validate_response(self, response: Any) -> bool:
        """Check that response has a message."""
        if response is None:
            return False
        if isinstance(response, dict):
            return "message" in response
        return hasattr(response, "message")

    def complete_streaming(  # type: ignore[override]
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> NormalizedResponse:
        """Stream completion via ollama SDK, collect all tokens, return NormalizedResponse.

        This is synchronous (not async) because the ollama SDK's streaming is
        synchronous. Uses stream=True so tokens arrive progressively.

        params:
            num_ctx: int        — context length
            print_tokens: bool  — print tokens to stdout (default False)
        """
        try:
            import ollama as _ollama  # type: ignore
        except ImportError as e:
            logger.error(f"[VECTOR][ollama] ollama SDK not installed: {e}")
            return NormalizedResponse(
                content=f"[OllamaTransport error: ollama not installed]",
                tool_calls=None,
                finish_reason="stop",
            )

        kwargs = self.build_kwargs(model, messages, tools, stream=True, **params)
        print_tokens: bool = params.get("print_tokens", False)

        content_parts: List[str] = []
        last_response: Any = None

        try:
            for chunk in _ollama.chat(**kwargs):
                last_response = chunk
                if isinstance(chunk, dict):
                    token = (chunk.get("message") or {}).get("content", "") or ""
                else:
                    msg = getattr(chunk, "message", None)
                    token = getattr(msg, "content", "") or "" if msg else ""
                if token:
                    if print_tokens:
                        print(token, end="", flush=True)
                    content_parts.append(token)
            if print_tokens:
                print()
        except Exception as e:
            logger.error(f"[VECTOR][ollama] streaming failed for {model}: {e}")
            return NormalizedResponse(
                content=f"[OllamaTransport streaming error: {e}]",
                tool_calls=None,
                finish_reason="stop",
            )

        # Build a synthetic final response for normalization
        final: Dict[str, Any] = {
            "message": {"content": "".join(content_parts), "role": "assistant", "tool_calls": []},
            "done_reason": "stop",
        }
        if last_response is not None:
            if isinstance(last_response, dict):
                final["prompt_eval_count"] = last_response.get("prompt_eval_count", 0)
                final["eval_count"] = last_response.get("eval_count", 0)
                # Check for tool_calls in the last chunk
                msg_chunk = last_response.get("message") or {}
                if isinstance(msg_chunk, dict) and msg_chunk.get("tool_calls"):
                    final["message"]["tool_calls"] = msg_chunk["tool_calls"]
            else:
                final["prompt_eval_count"] = getattr(last_response, "prompt_eval_count", 0)
                final["eval_count"] = getattr(last_response, "eval_count", 0)

        return self.normalize_response(final)


# ── Auto-register on import ──────────────────────────────────────────────────
from transports import register_transport  # type: ignore[import]  # noqa: E402

register_transport("ollama", OllamaTransport)


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    t = OllamaTransport()
    assert t.api_mode == "ollama"

    # convert_messages: identity
    msgs = [{"role": "user", "content": "Hi"}]
    assert t.convert_messages(msgs) is msgs

    # convert_tools: identity
    tools = [{"type": "function", "function": {"name": "f"}}]
    assert t.convert_tools(tools) is tools

    # build_kwargs
    kwargs = t.build_kwargs("vector-focus", msgs, num_ctx=4096, stream=True)
    assert kwargs["model"] == "vector-focus"
    assert kwargs["options"]["num_ctx"] == 4096
    assert kwargs["stream"] is True

    # normalize_response: dict format
    fake_resp = {
        "message": {"role": "assistant", "content": "Hello!", "tool_calls": []},
        "done_reason": "stop",
        "prompt_eval_count": 10,
        "eval_count": 5,
    }
    nr = t.normalize_response(fake_resp)
    assert nr.content == "Hello!"
    assert nr.finish_reason == "stop"
    assert nr.usage is not None
    assert nr.usage.prompt_tokens == 10
    assert nr.usage.completion_tokens == 5

    # normalize_response: tool_calls
    fake_with_tools = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "tc_1", "function": {"name": "search", "arguments": {"query": "VECTOR"}}}
            ],
        },
        "done_reason": "tool_calls",
    }
    nr2 = t.normalize_response(fake_with_tools)
    assert nr2.finish_reason == "tool_calls"
    assert nr2.tool_calls is not None
    assert len(nr2.tool_calls) == 1
    assert nr2.tool_calls[0].name == "search"

    # validate_response
    assert t.validate_response(fake_resp) is True
    assert t.validate_response(None) is False
    assert t.validate_response({}) is False

    print("ollama.py OK")
