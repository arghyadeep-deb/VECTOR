"""Shared types for normalized provider responses.

These dataclasses define the canonical shape that all provider transports
normalize responses to. The shared surface is intentionally minimal —
only fields that every downstream consumer reads are top-level.
Protocol-specific state goes in ``provider_data`` dicts so that
protocol-aware code paths can access it without polluting the shared type.

VectorCode implementation.py.
"""

# ── stdlib first — before any sys.path manipulation ──────────────────────────
# NOTE: this file is named types.py which shadows stdlib types when the
# transports/ directory is on sys.path[0] (happens when run as a script).
# We strip the script dir from sys.path before any non-C-builtin import.
import sys
import os as _os
_this_dir = _os.path.dirname(_os.path.abspath(__file__))
sys.path = [p for p in sys.path if _os.path.abspath(p) != _this_dir]
del _os, _this_dir

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── sys.path inserts (exactly 2) ─────────────────────────────────────────────


try:
    from core.config import CONFIG  # type: ignore
except ImportError:
    CONFIG = {}


# ── Core dataclasses ─────────────────────────────────────────────────────────

@dataclass
class Usage:
    """Token usage from an API response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class ToolCall:
    """A normalized tool call from any provider.

    ``id`` is the protocol's canonical identifier used in tool_call_id /
    tool_use_id when constructing tool result messages.  May be ``None``
    when the provider omits it.

    ``provider_data`` carries per-tool-call protocol metadata that only
    protocol-aware code reads:
      - Codex:  {"call_id": "call_XXX", "response_item_id": "fc_XXX"}
      - Gemini: {"extra_content": {"google": {"thought_signature": "..."}}}
      - Others: None
    """

    id: Optional[str]
    name: str
    arguments: str  # JSON string
    provider_data: Optional[Dict[str, Any]] = field(default=None, repr=False)

    # ── Backward-compatibility properties ────────────────────────────────────
    # Callers that read tc.function.name / tc.function.arguments keep working.

    @property
    def type(self) -> str:
        """Always returns 'function' for OpenAI compat."""
        return "function"

    @property
    def function(self) -> "ToolCall":
        """Return self so tc.function.name / tc.function.arguments work."""
        return self

    @property
    def call_id(self) -> Optional[str]:
        """Codex call_id from provider_data."""
        return (self.provider_data or {}).get("call_id")

    @property
    def response_item_id(self) -> Optional[str]:
        """Codex response_item_id from provider_data."""
        return (self.provider_data or {}).get("response_item_id")

    @property
    def extra_content(self) -> Optional[Dict[str, Any]]:
        """Gemini extra_content (thought_signature) from provider_data.

        Gemini 3 thinking models attach extra_content with a thought_signature
        that must be replayed on subsequent API calls.
        """
        return (self.provider_data or {}).get("extra_content")


@dataclass
class NormalizedResponse:
    """Normalized API response from any provider.

    Shared fields are truly cross-provider. Protocol-specific state goes in
    ``provider_data`` so that only protocol-aware code paths read it.

    Response-level ``provider_data`` examples:
      - Anthropic: {"reasoning_details": [...]}
      - Codex:     {"codex_reasoning_items": [...], "codex_message_items": [...]}
      - Others:    None
    """

    content: Optional[str]
    tool_calls: Optional[List[ToolCall]]
    finish_reason: str  # "stop", "tool_calls", "length", "content_filter"
    reasoning: Optional[str] = None
    usage: Optional[Usage] = None
    provider_data: Optional[Dict[str, Any]] = field(default=None, repr=False)

    # ── Backward-compatibility properties ────────────────────────────────────

    @property
    def reasoning_content(self) -> Optional[str]:
        """DeepSeek/Moonshot reasoning_content from provider_data."""
        pd = self.provider_data or {}
        return pd.get("reasoning_content")

    @property
    def reasoning_details(self):
        """Anthropic reasoning_details blocks from provider_data."""
        pd = self.provider_data or {}
        return pd.get("reasoning_details")

    @property
    def codex_reasoning_items(self):
        """Codex reasoning items from provider_data."""
        pd = self.provider_data or {}
        return pd.get("codex_reasoning_items")

    @property
    def codex_message_items(self):
        """Codex message items from provider_data."""
        pd = self.provider_data or {}
        return pd.get("codex_message_items")


# ── Factory helpers ──────────────────────────────────────────────────────────

def build_tool_call(
    id: Optional[str],
    name: str,
    arguments: Any,
    provider_data: Optional[Dict[str, Any]] = None,
    **extra_provider_fields: Any,
) -> ToolCall:
    """Build a ToolCall, auto-serialising arguments if it is a dict.

    Extra keyword arguments are merged into provider_data.
    """
    args_str = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments)
    if extra_provider_fields:
        pd = dict(extra_provider_fields)
        if provider_data:
            pd.update(provider_data)
    else:
        pd = provider_data
    return ToolCall(id=id, name=name, arguments=args_str, provider_data=pd)


def map_finish_reason(raw: Optional[str], provider: str = "") -> str:
    """Translate a provider-specific stop reason to the normalised set.

    Falls back to "stop" for unknown or None reasons.
    Provider-specific mappings:
      - anthropic: end_turn→stop, tool_use→tool_calls, max_tokens→length
      - generic:   identity (chat_completions already canonical)
    """
    if raw is None:
        return "stop"

    _ANTHROPIC_MAP: Dict[str, str] = {
        "end_turn": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
        "stop_sequence": "stop",
        "refusal": "content_filter",
        "model_context_window_exceeded": "length",
    }

    if provider == "anthropic":
        return _ANTHROPIC_MAP.get(raw, "stop")

    # chat_completions: already OpenAI canonical — return as-is
    return raw


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    # Usage
    u = Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150, cached_tokens=20)
    assert u.total_tokens == 150
    assert u.cached_tokens == 20

    # ToolCall flat fields
    tc = build_tool_call("call_123", "search_web", {"query": "VECTOR"})
    assert tc.id == "call_123"
    assert tc.name == "search_web"
    assert '"query"' in tc.arguments
    assert tc.type == "function"
    assert tc.function is tc
    assert tc.call_id is None
    assert tc.extra_content is None

    # ToolCall with provider_data
    tc2 = build_tool_call("id_x", "tool_y", {"k": "v"}, provider_data={"call_id": "c_1", "response_item_id": "r_1"})
    assert tc2.call_id == "c_1"
    assert tc2.response_item_id == "r_1"

    # NormalizedResponse
    nr = NormalizedResponse(
        content="Hello",
        tool_calls=[tc],
        finish_reason="stop",
        reasoning="I thought...",
        usage=u,
    )
    assert nr.content == "Hello"
    assert nr.reasoning_content is None  # not in provider_data
    assert nr.reasoning_details is None

    nr2 = NormalizedResponse(
        content=None,
        tool_calls=None,
        finish_reason="tool_calls",
        provider_data={"reasoning_content": "deep thoughts", "reasoning_details": [{"type": "thinking"}]},
    )
    assert nr2.reasoning_content == "deep thoughts"
    assert nr2.reasoning_details == [{"type": "thinking"}]

    # map_finish_reason
    assert map_finish_reason("end_turn", "anthropic") == "stop"
    assert map_finish_reason("tool_use", "anthropic") == "tool_calls"
    assert map_finish_reason("max_tokens", "anthropic") == "length"
    assert map_finish_reason(None) == "stop"
    assert map_finish_reason("tool_calls") == "tool_calls"  # chat_completions identity
    assert map_finish_reason("stop") == "stop"

    print("types.py OK")

