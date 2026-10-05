"""OpenAI Chat Completions transport for VectorCode.

Handles the default api_mode ('chat_completions') used by OpenAI-compatible
providers: OpenRouter, Ollama, DeepSeek, Kimi, Mistral, xAI, etc.

Messages and tools are already in OpenAI format — convert_messages and
convert_tools are near-identity. The complexity lives in build_kwargs which
has provider-specific conditionals for max_tokens defaults, reasoning
configuration, temperature handling, and extra_body assembly.

VectorCode implementation.py.
"""

# ── Guard: strip transports/ from sys.path to prevent types.py shadowing stdlib.
import sys
import os as _os
_this_dir = _os.path.dirname(_os.path.abspath(__file__))
sys.path = [p for p in sys.path if _os.path.abspath(p) != _this_dir]
del _os, _this_dir

# ── stdlib ────────────────────────────────────────────────────────────────────
import copy
from typing import Any, Dict, List, Optional

# ── sys.path inserts (exactly 2) ─────────────────────────────────────────────

from loguru import logger
from .base import ProviderTransport
from .types import (
    NormalizedResponse, ToolCall, Usage,
)

try:
    from core.config import CONFIG  # type: ignore
except ImportError:
    CONFIG = {}


class ChatCompletionsTransport(ProviderTransport):
    """Transport for api_mode='chat_completions'.

    The default path for OpenAI-compatible providers.
    """

    @property
    def api_mode(self) -> str:
        return "chat_completions"

    def convert_messages(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> List[Dict[str, Any]]:
        """Messages are already in OpenAI format — sanitize Codex leak fields only.

        Strips Codex Responses API fields (codex_reasoning_items /
        codex_message_items on the message, call_id / response_item_id
        on tool_calls) that strict chat-completions providers reject with 400/422.
        """
        needs_sanitize = False
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            if "codex_reasoning_items" in msg or "codex_message_items" in msg:
                needs_sanitize = True
                break
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict) and ("call_id" in tc or "response_item_id" in tc):
                        needs_sanitize = True
                        break
                if needs_sanitize:
                    break

        if not needs_sanitize:
            return messages

        sanitized = copy.deepcopy(messages)
        for msg in sanitized:
            if not isinstance(msg, dict):
                continue
            msg.pop("codex_reasoning_items", None)
            msg.pop("codex_message_items", None)
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc.pop("call_id", None)
                        tc.pop("response_item_id", None)
        return sanitized

    def convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Tools are already in OpenAI format — identity."""
        return tools

    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """Build chat.completions.create() kwargs.

        Handles multiple providers via params rather than subclasses.

        params (all optional):
            max_tokens: int | None
            temperature: float | None
            stream: bool
            timeout: float
            # Provider flags
            is_openrouter: bool
            is_kimi: bool
            is_qwen_portal: bool
            is_nous: bool
            is_nvidia_nim: bool
            is_custom_provider: bool
            # Ollama
            ollama_num_ctx: int | None
            # Provider routing (OpenRouter)
            provider_preferences: dict | None
            # Reasoning
            reasoning_config: dict | None
            supports_reasoning: bool
            # Extra
            request_overrides: dict | None
            extra_body_additions: dict | None
        """
        # Codex sanitization first
        sanitized = self.convert_messages(messages)

        api_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": sanitized,
        }

        # Timeout
        timeout = params.get("timeout")
        if timeout is not None:
            api_kwargs["timeout"] = timeout

        # Stream
        stream = params.get("stream", False)
        api_kwargs["stream"] = stream

        # Temperature
        temperature = params.get("temperature")
        omit_temperature = params.get("omit_temperature", False)
        fixed_temperature = params.get("fixed_temperature")
        if omit_temperature:
            pass  # do not include temperature
        elif fixed_temperature is not None:
            api_kwargs["temperature"] = fixed_temperature
        elif temperature is not None:
            api_kwargs["temperature"] = temperature

        # Tools
        if tools:
            api_kwargs["tools"] = tools

        # max_tokens resolution — priority: ephemeral > user > provider default
        max_tokens: Optional[int] = params.get("max_tokens")
        ephemeral: Optional[int] = params.get("ephemeral_max_output_tokens")
        is_nvidia_nim: bool = params.get("is_nvidia_nim", False)
        is_qwen: bool = params.get("is_qwen_portal", False)
        is_kimi: bool = params.get("is_kimi", False)
        anthropic_max_out: Optional[int] = params.get("anthropic_max_output")

        if ephemeral is not None:
            api_kwargs["max_tokens"] = ephemeral
        elif max_tokens is not None:
            api_kwargs["max_tokens"] = max_tokens
        elif is_nvidia_nim:
            api_kwargs["max_tokens"] = 16384
        elif is_qwen:
            api_kwargs["max_tokens"] = 65536
        elif is_kimi:
            api_kwargs["max_tokens"] = 32000
        elif anthropic_max_out is not None:
            api_kwargs["max_tokens"] = anthropic_max_out

        # Kimi: top-level reasoning_effort
        reasoning_config = params.get("reasoning_config")
        if is_kimi:
            _kimi_thinking_off = bool(
                reasoning_config
                and isinstance(reasoning_config, dict)
                and reasoning_config.get("enabled") is False
            )
            if not _kimi_thinking_off:
                _kimi_effort = "medium"
                if reasoning_config and isinstance(reasoning_config, dict):
                    _e = (reasoning_config.get("effort") or "").strip().lower()
                    if _e in ("low", "medium", "high"):
                        _kimi_effort = _e
                api_kwargs["reasoning_effort"] = _kimi_effort

        # extra_body assembly
        extra_body: Dict[str, Any] = {}

        is_openrouter: bool = params.get("is_openrouter", False)
        is_nous: bool = params.get("is_nous", False)

        provider_prefs = params.get("provider_preferences")
        if provider_prefs and is_openrouter:
            extra_body["provider"] = provider_prefs

        # Kimi extra_body.thinking
        if is_kimi:
            _kimi_thinking_enabled = True
            if reasoning_config and isinstance(reasoning_config, dict):
                if reasoning_config.get("enabled") is False:
                    _kimi_thinking_enabled = False
            extra_body["thinking"] = {
                "type": "enabled" if _kimi_thinking_enabled else "disabled",
            }

        # Reasoning config for providers that support it
        if params.get("supports_reasoning", False):
            if reasoning_config is not None:
                rc = dict(reasoning_config)
                if is_nous and rc.get("enabled") is False:
                    pass  # omit for Nous when disabled
                else:
                    extra_body["reasoning"] = rc
            else:
                extra_body["reasoning"] = {"enabled": True, "effort": "medium"}

        if is_nous:
            extra_body["tags"] = ["product=vectorcode"]

        # Ollama num_ctx
        ollama_ctx = params.get("ollama_num_ctx")
        if ollama_ctx:
            options = extra_body.get("options", {})
            options["num_ctx"] = ollama_ctx
            extra_body["options"] = options

        # Custom provider think=false (Ollama reasoning disable)
        if params.get("is_custom_provider", False):
            if reasoning_config and isinstance(reasoning_config, dict):
                _effort = (reasoning_config.get("effort") or "").strip().lower()
                _enabled = reasoning_config.get("enabled", True)
                if _effort == "none" or _enabled is False:
                    extra_body["think"] = False

        # Merge pre-built extra_body additions
        additions = params.get("extra_body_additions")
        if additions:
            extra_body.update(additions)

        if extra_body:
            api_kwargs["extra_body"] = extra_body

        # Request overrides last (service_tier etc.)
        overrides = params.get("request_overrides")
        if overrides:
            api_kwargs.update(overrides)

        return api_kwargs

    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize OpenAI ChatCompletion to NormalizedResponse.

        Near-identity for chat_completions. Preserves extra_content on tool_calls
        (Gemini thought_signature) and reasoning fields (DeepSeek/Moonshot).
        """
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices", [])

        if not choices:
            logger.warning(f"[VECTOR][chat_completions] normalize_response: no choices in response")
            return NormalizedResponse(content=None, tool_calls=None, finish_reason="stop")

        choice = choices[0]
        msg = getattr(choice, "message", None)
        if msg is None and isinstance(choice, dict):
            msg = choice.get("message", {})

        finish_reason = (
            getattr(choice, "finish_reason", None)
            or (choice.get("finish_reason") if isinstance(choice, dict) else None)
            or "stop"
        )

        # Extract content
        content = (
            getattr(msg, "content", None)
            if not isinstance(msg, dict)
            else msg.get("content")
        )

        # Tool calls
        raw_tool_calls = (
            getattr(msg, "tool_calls", None)
            if not isinstance(msg, dict)
            else msg.get("tool_calls")
        )
        tool_calls: Optional[List[ToolCall]] = None
        if raw_tool_calls:
            tool_calls = []
            for tc in raw_tool_calls:
                tc_provider_data: Dict[str, Any] = {}

                # Gemini extra_content (thought_signature)
                extra = getattr(tc, "extra_content", None)
                if extra is None and hasattr(tc, "model_extra"):
                    extra = (tc.model_extra or {}).get("extra_content")
                if extra is None and isinstance(tc, dict):
                    extra = tc.get("extra_content")
                if extra is not None:
                    if hasattr(extra, "model_dump"):
                        try:
                            extra = extra.model_dump()
                        except Exception as _sve:
                            logger.debug(
                                "[VECTOR][transports.chat_completions] "
                                "failed to serialize tool metadata: {}",
                                _sve,
                            )
                    tc_provider_data["extra_content"] = extra

                # Extract id / name / arguments
                tc_id = getattr(tc, "id", None) or (tc.get("id") if isinstance(tc, dict) else None)
                fn = getattr(tc, "function", None) or (tc.get("function", {}) if isinstance(tc, dict) else {})
                fn_name = (
                    getattr(fn, "name", None) or (fn.get("name", "") if isinstance(fn, dict) else "")
                )
                fn_args = (
                    getattr(fn, "arguments", "{}") or (fn.get("arguments", "{}") if isinstance(fn, dict) else "{}")
                )

                tool_calls.append(ToolCall(
                    id=tc_id,
                    name=fn_name,
                    arguments=fn_args,
                    provider_data=tc_provider_data or None,
                ))

        # Usage
        usage_obj = getattr(response, "usage", None) if not isinstance(response, dict) else response.get("usage")
        usage: Optional[Usage] = None
        if usage_obj is not None:
            def usage_value(name: str) -> int:
                if isinstance(usage_obj, dict):
                    return usage_obj.get(name, 0) or 0
                return getattr(usage_obj, name, 0) or 0

            usage = Usage(
                prompt_tokens=usage_value("prompt_tokens"),
                completion_tokens=usage_value("completion_tokens"),
                total_tokens=usage_value("total_tokens"),
            )

        # Reasoning fields (DeepSeek / Moonshot / OpenRouter unified format)
        reasoning = getattr(msg, "reasoning", None) if not isinstance(msg, dict) else msg.get("reasoning")
        reasoning_content = getattr(msg, "reasoning_content", None) if not isinstance(msg, dict) else msg.get("reasoning_content")

        provider_data: Dict[str, Any] = {}
        if reasoning_content:
            provider_data["reasoning_content"] = reasoning_content
        rd = getattr(msg, "reasoning_details", None) if not isinstance(msg, dict) else msg.get("reasoning_details")
        if rd:
            provider_data["reasoning_details"] = rd

        return NormalizedResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            reasoning=reasoning,
            usage=usage,
            provider_data=provider_data or None,
        )

    def validate_response(self, response: Any) -> bool:
        """Check that response has valid choices."""
        if response is None:
            return False
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        if choices is None:
            return False
        if not choices:
            return False
        return True

    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
        """Extract OpenRouter/OpenAI cache stats from prompt_tokens_details."""
        usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
        if usage is None:
            return None
        details = (
            usage.get("prompt_tokens_details")
            if isinstance(usage, dict)
            else getattr(usage, "prompt_tokens_details", None)
        )
        if details is None:
            return None
        if isinstance(details, dict):
            cached = details.get("cached_tokens", 0) or 0
            written = details.get("cache_write_tokens", 0) or 0
        else:
            cached = getattr(details, "cached_tokens", 0) or 0
            written = getattr(details, "cache_write_tokens", 0) or 0
        if cached or written:
            return {"cached_tokens": cached, "creation_tokens": written}
        return None


# ── Auto-register on import ──────────────────────────────────────────────────
from . import register_transport  # noqa: E402

register_transport("chat_completions", ChatCompletionsTransport)


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    t = ChatCompletionsTransport()
    assert t.api_mode == "chat_completions"

    # convert_messages: identity for clean messages
    msgs = [{"role": "user", "content": "Hello"}]
    result = t.convert_messages(msgs)
    assert result is msgs  # no copy when no Codex fields

    # convert_messages: strips Codex fields
    dirty = [
        {
            "role": "assistant",
            "content": "hi",
            "codex_reasoning_items": ["r1"],
            "tool_calls": [{"id": "tc1", "call_id": "c1", "response_item_id": "r1", "function": {"name": "f", "arguments": "{}"}}],
        }
    ]
    cleaned = t.convert_messages(dirty)
    assert "codex_reasoning_items" not in cleaned[0]
    assert "call_id" not in cleaned[0]["tool_calls"][0]
    assert "response_item_id" not in cleaned[0]["tool_calls"][0]

    # build_kwargs: basic
    kwargs = t.build_kwargs("qwen3:14b", msgs, max_tokens=4096, stream=False)
    assert kwargs["model"] == "qwen3:14b"
    assert kwargs["max_tokens"] == 4096

    # build_kwargs: ollama num_ctx
    kwargs2 = t.build_kwargs("vector-focus", msgs, ollama_num_ctx=32768)
    assert kwargs2.get("extra_body", {}).get("options", {}).get("num_ctx") == 32768

    # normalize_response: basic dict-style
    class _Choice:
        finish_reason = "stop"
        class message:
            content = "Answer"
            tool_calls = None
            reasoning = None
            reasoning_content = None
            reasoning_details = None

    class _Resp:
        choices = [_Choice()]
        usage = None

    nr = t.normalize_response(_Resp())
    assert nr.content == "Answer"
    assert nr.finish_reason == "stop"
    assert nr.tool_calls is None

    # validate_response
    assert t.validate_response(_Resp()) is True
    assert t.validate_response(None) is False

    print("chat_completions.py OK")

