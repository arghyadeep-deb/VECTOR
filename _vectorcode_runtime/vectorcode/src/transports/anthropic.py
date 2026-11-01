"""Anthropic Messages API transport for VectorCode.

Owns format conversion (OpenAI → Anthropic) and response normalization.
Does NOT own: client construction, credential refresh, or retry logic.

VectorCode implementation.py.
Prompt caching logic ported from agent/prompt_caching.py.
"""

# ── Guard: strip transports/ from sys.path to prevent types.py shadowing stdlib.
import sys
import os as _os
_this_dir = _os.path.dirname(_os.path.abspath(__file__))
sys.path = [p for p in sys.path if _os.path.abspath(p) != _this_dir]
del _os, _this_dir

# ── stdlib ────────────────────────────────────────────────────────────────────
import copy
import json
from typing import Any, Dict, List, Optional

# ── sys.path inserts (exactly 2) ─────────────────────────────────────────────

from .base import ProviderTransport
from .types import (
    NormalizedResponse, ToolCall, Usage, build_tool_call,
)

try:
    from core.config import CONFIG  # type: ignore
except ImportError:
    CONFIG = {}

# ── Stop-reason mapping ──────────────────────────────────────────────────────

_STOP_REASON_MAP: Dict[str, str] = {
    "end_turn":                      "stop",
    "tool_use":                      "tool_calls",
    "max_tokens":                    "length",
    "stop_sequence":                 "stop",
    "refusal":                       "content_filter",
    "model_context_window_exceeded": "length",
}


# ── Prompt-caching helpers (from reference agent/prompt_caching.py) ─────────────

def _apply_cache_marker(msg: dict, cache_marker: dict, native_anthropic: bool = False) -> None:
    """Add cache_control to a single message, handling all format variations."""
    role = msg.get("role", "")
    content = msg.get("content")

    if role == "tool":
        if native_anthropic:
            msg["cache_control"] = cache_marker
        return

    if content is None or content == "":
        msg["cache_control"] = cache_marker
        return

    if isinstance(content, str):
        msg["content"] = [
            {"type": "text", "text": content, "cache_control": cache_marker}
        ]
        return

    if isinstance(content, list) and content:
        last = content[-1]
        if isinstance(last, dict):
            last["cache_control"] = cache_marker


def apply_anthropic_cache_control(
    api_messages: List[Dict[str, Any]],
    cache_ttl: str = "5m",
    native_anthropic: bool = False,
) -> List[Dict[str, Any]]:
    """Apply system_and_3 caching strategy to messages for Anthropic models.

    Places up to 4 cache_control breakpoints: system prompt + last 3 non-system
    messages.  Reduces input token costs ~75% on multi-turn conversations.
    Returns a deep copy with cache_control breakpoints injected.
    """
    messages = copy.deepcopy(api_messages)
    if not messages:
        return messages

    marker: Dict[str, Any] = {"type": "ephemeral"}
    if cache_ttl == "1h":
        marker["ttl"] = "1h"

    breakpoints_used = 0
    if messages[0].get("role") == "system":
        _apply_cache_marker(messages[0], marker, native_anthropic=native_anthropic)
        breakpoints_used += 1

    remaining = 4 - breakpoints_used
    non_sys = [i for i in range(len(messages)) if messages[i].get("role") != "system"]
    for idx in non_sys[-remaining:]:
        _apply_cache_marker(messages[idx], marker, native_anthropic=native_anthropic)

    return messages


# ── Message format conversion ────────────────────────────────────────────────

def _convert_messages_to_anthropic(
    messages: List[Dict[str, Any]],
) -> tuple:  # (Optional[str], List[Dict])
    """Convert OpenAI-format messages to Anthropic (system, messages) tuple.

    Anthropic separates system prompt from the message list.
    Tool results use role='user' with content blocks of type 'tool_result'.
    Tool calls use content blocks of type 'tool_use'.
    """
    system_parts: List[str] = []
    anthropic_messages: List[Dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        system_parts.append(block.get("text", ""))
            continue

        if role == "tool":
            # OpenAI tool result → Anthropic tool_result block in user turn
            tool_call_id = msg.get("tool_call_id", "")
            tool_content = content or ""
            anthropic_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": tool_content if isinstance(tool_content, str)
                                   else json.dumps(tool_content),
                    }
                ],
            })
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls") or []
            content_blocks: List[Dict[str, Any]] = []

            # Text content
            if isinstance(content, str) and content:
                content_blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        content_blocks.append(block)

            # Tool use blocks
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args_dict = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except (json.JSONDecodeError, TypeError):
                        args_dict = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": args_dict,
                    })

            anthropic_messages.append({
                "role": "assistant",
                "content": content_blocks if content_blocks else (content or ""),
            })
            continue

        # user / other roles — pass through
        if isinstance(content, list):
            anthropic_messages.append({"role": role, "content": content})
        else:
            anthropic_messages.append({"role": role, "content": content or ""})

    system_text = "\n\n".join(system_parts) if system_parts else None
    return system_text, anthropic_messages


def _convert_tools_to_anthropic(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI tool schemas to Anthropic input_schema format."""
    anthropic_tools: List[Dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        fn = tool.get("function", {})
        anthropic_tools.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return anthropic_tools


# ── Transport class ──────────────────────────────────────────────────────────

class AnthropicTransport(ProviderTransport):
    """Transport for api_mode='anthropic_messages'.

    Handles OpenAI → Anthropic format conversion and response normalization.
    """

    @property
    def api_mode(self) -> str:
        return "anthropic_messages"

    def convert_messages(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> tuple:
        """Convert OpenAI messages to Anthropic (system_text, messages) tuple."""
        return _convert_messages_to_anthropic(messages)

    def convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI tool schemas to Anthropic input_schema format."""
        return _convert_tools_to_anthropic(tools)

    def build_kwargs(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **params,
    ) -> Dict[str, Any]:
        """Build anthropic.messages.create() kwargs.

        params (all optional):
            max_tokens: int            — default 8192
            tool_choice: str | None    — "auto" | "any" | tool name
            apply_cache: bool          — inject cache_control breakpoints
            cache_ttl: str             — "5m" (default) or "1h"
            stream: bool               — default False
        """
        apply_cache: bool = params.get("apply_cache", False)
        cache_ttl: str = params.get("cache_ttl", "5m")
        max_tokens: int = params.get("max_tokens", 8192)
        stream: bool = params.get("stream", False)
        tool_choice_raw = params.get("tool_choice")

        working_messages = messages
        if apply_cache:
            working_messages = apply_anthropic_cache_control(messages, cache_ttl=cache_ttl)

        system_text, anthropic_msgs = _convert_messages_to_anthropic(working_messages)

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if system_text:
            kwargs["system"] = system_text

        if tools:
            kwargs["tools"] = _convert_tools_to_anthropic(tools)
            if tool_choice_raw:
                if tool_choice_raw in ("auto", "any"):
                    kwargs["tool_choice"] = {"type": tool_choice_raw}
                else:
                    kwargs["tool_choice"] = {"type": "tool", "name": tool_choice_raw}

        return kwargs

    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize Anthropic response to NormalizedResponse.

        Parses content blocks (text, thinking, tool_use), maps stop_reason
        to OpenAI finish_reason, and collects reasoning_details in provider_data.
        """
        strip_tool_prefix: bool = kwargs.get("strip_tool_prefix", False)
        _MCP_PREFIX = "mcp_"

        text_parts: List[str] = []
        reasoning_parts: List[str] = []
        reasoning_details: List[Dict[str, Any]] = []
        tool_calls: List[ToolCall] = []

        content_blocks = getattr(response, "content", None) or []
        for block in content_blocks:
            block_type = getattr(block, "type", None) or (
                block.get("type") if isinstance(block, dict) else None
            )

            if block_type == "text":
                text = getattr(block, "text", None) or (
                    block.get("text", "") if isinstance(block, dict) else ""
                )
                text_parts.append(text)

            elif block_type == "thinking":
                thinking = getattr(block, "thinking", None) or (
                    block.get("thinking", "") if isinstance(block, dict) else ""
                )
                reasoning_parts.append(thinking)
                # Serialize block for reasoning_details
                if hasattr(block, "__dict__"):
                    reasoning_details.append({"type": "thinking", "thinking": thinking})
                elif isinstance(block, dict):
                    reasoning_details.append(block)

            elif block_type == "tool_use":
                name = getattr(block, "name", None) or (
                    block.get("name", "") if isinstance(block, dict) else ""
                )
                if strip_tool_prefix and name.startswith(_MCP_PREFIX):
                    name = name[len(_MCP_PREFIX):]

                block_id = getattr(block, "id", None) or (
                    block.get("id") if isinstance(block, dict) else None
                )
                raw_input = getattr(block, "input", None) or (
                    block.get("input", {}) if isinstance(block, dict) else {}
                )
                tool_calls.append(
                    ToolCall(
                        id=block_id,
                        name=name,
                        arguments=json.dumps(raw_input) if isinstance(raw_input, dict)
                                  else str(raw_input),
                    )
                )

        stop_reason = getattr(response, "stop_reason", None) or (
            response.get("stop_reason") if isinstance(response, dict) else None
        )
        finish_reason = _STOP_REASON_MAP.get(stop_reason or "", "stop")

        # Usage
        usage_obj = getattr(response, "usage", None)
        usage: Optional[Usage] = None
        if usage_obj is not None:
            usage = Usage(
                prompt_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
                completion_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
                total_tokens=(
                    (getattr(usage_obj, "input_tokens", 0) or 0)
                    + (getattr(usage_obj, "output_tokens", 0) or 0)
                ),
                cached_tokens=getattr(usage_obj, "cache_read_input_tokens", 0) or 0,
            )

        provider_data: Dict[str, Any] = {}
        if reasoning_details:
            provider_data["reasoning_details"] = reasoning_details

        return NormalizedResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
            reasoning="\n\n".join(reasoning_parts) if reasoning_parts else None,
            usage=usage,
            provider_data=provider_data or None,
        )

    def validate_response(self, response: Any) -> bool:
        """Check Anthropic response structure is valid.

        An empty content list is legitimate when stop_reason == 'end_turn'
        (model's canonical way of signalling 'nothing more to add').
        Treating it as invalid would falsely retry a completed response.
        """
        if response is None:
            return False
        content_blocks = getattr(response, "content", None)
        if not isinstance(content_blocks, list):
            return False
        if not content_blocks:
            return getattr(response, "stop_reason", None) == "end_turn"
        return True

    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
        """Extract Anthropic cache_read and cache_creation token counts."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0
        written = getattr(usage, "cache_creation_input_tokens", 0) or 0
        if cached or written:
            return {"cached_tokens": cached, "creation_tokens": written}
        return None

    def map_finish_reason(self, raw_reason: str) -> str:
        """Map Anthropic stop_reason to OpenAI finish_reason."""
        return _STOP_REASON_MAP.get(raw_reason, "stop")

    def apply_cache_control(
        self,
        messages: List[Dict[str, Any]],
        cache_ttl: str = "5m",
    ) -> List[Dict[str, Any]]:
        """Inject cache_control=ephemeral on system + last 3 user messages."""
        return apply_anthropic_cache_control(messages, cache_ttl=cache_ttl)


# ── Auto-register on import ──────────────────────────────────────────────────
from . import register_transport  # noqa: E402

register_transport("anthropic_messages", AnthropicTransport)


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    t = AnthropicTransport()
    assert t.api_mode == "anthropic_messages"

    # convert_messages: system extraction
    msgs = [
        {"role": "system", "content": "You are VECTOR."},
        {"role": "user", "content": "Hello"},
    ]
    sys_text, ant_msgs = t.convert_messages(msgs)
    assert sys_text == "You are VECTOR."
    assert ant_msgs[0]["role"] == "user"
    assert ant_msgs[0]["content"] == "Hello"

    # convert_tools: OpenAI → Anthropic input_schema
    tools_oai = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search the web",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    ]
    ant_tools = t.convert_tools(tools_oai)
    assert ant_tools[0]["name"] == "search"
    assert "input_schema" in ant_tools[0]
    assert ant_tools[0]["input_schema"]["properties"]["query"]["type"] == "string"

    # build_kwargs
    kwargs = t.build_kwargs("claude-sonnet-4-6", msgs, tools_oai, max_tokens=1024)
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["system"] == "You are VECTOR."
    assert "tools" in kwargs
    assert kwargs["max_tokens"] == 1024

    # map_finish_reason
    assert t.map_finish_reason("end_turn") == "stop"
    assert t.map_finish_reason("tool_use") == "tool_calls"
    assert t.map_finish_reason("max_tokens") == "length"
    assert t.map_finish_reason("unknown_reason") == "stop"

    # apply_cache_control
    cached = t.apply_cache_control(msgs)
    assert isinstance(cached, list)

    # validate_response
    class _FakeResp:
        content = [{"type": "text", "text": "hi"}]
        stop_reason = "end_turn"
        usage = None

    assert t.validate_response(_FakeResp()) is True
    assert t.validate_response(None) is False

    print("anthropic.py OK")

