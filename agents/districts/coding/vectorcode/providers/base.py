"""Base provider interface and shared types for VectorCode."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TokenUsage:
    prompt_tokens:     int = 0
    completion_tokens: int = 0
    total_tokens:      int = 0
    cache_read_tokens: int = 0


@dataclass
class ToolCall:
    id:        str
    name:      str
    arguments: dict


@dataclass
class Message:
    role:         str
    content:      str = ""
    tool_calls:   list = field(default_factory=list)  # list[ToolCall]
    tool_call_id: str | None = None


@dataclass
class ModelCapabilities:
    context_window:     int  = 4096
    tool_use:           bool = False
    vision:             bool = False
    structured_output:  bool = False
    supports_streaming: bool = True


@dataclass
class CompletionResult:
    message:  Message
    usage:    TokenUsage
    model:    str
    cost_usd: float = 0.0


# ── Pricing table: (input $/1M tokens, output $/1M tokens) ───────────────────

PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4":       (15.0,  75.0),
    "claude-sonnet-4-6":   (3.0,   15.0),
    "claude-haiku-4-5":    (0.25,   1.25),
    "gpt-5":               (10.0,  30.0),
    "gpt-4o":              (2.5,   10.0),
    "gpt-4o-mini":         (0.15,   0.60),
    "o3":                  (10.0,  40.0),
    "gemini-2.5-pro":      (1.25,   5.0),
    "gemini-2.5-flash":    (0.075,  0.30),
    "llama-4-scout":       (0.11,   0.34),
    "llama-3.3-70b":       (0.59,   0.79),
    "mistral-large":       (2.0,    6.0),
    "codestral":           (1.0,    3.0),
    "deepseek-coder-v3":   (0.14,   0.28),
    "command-r-plus":      (2.5,   10.0),
    "grok-3":              (3.0,   15.0),
}


def estimate_cost(model: str, usage: TokenUsage) -> float:
    """Return estimated cost in USD for a completion. Returns 0.0 for local models."""
    for key, (inp_rate, out_rate) in PRICING.items():
        if key in model:
            return (usage.prompt_tokens * inp_rate + usage.completion_tokens * out_rate) / 1_000_000
    return 0.0  # local models are free


class BaseProvider(ABC):
    """All VectorCode provider adapters must implement this interface."""

    provider_name: str = "base"

    @abstractmethod
    def complete(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
        max_tokens: int = 8192,
    ) -> CompletionResult:
        """Run a completion. messages is a list of {role, content} dicts."""

    @abstractmethod
    def probe_capabilities(self, model: str) -> ModelCapabilities:
        """Probe a model to detect its capabilities."""

    def _make_result(
        self,
        content: str,
        model: str,
        usage: TokenUsage,
        tool_calls: list | None = None,
    ) -> CompletionResult:
        msg = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls or [],
        )
        return CompletionResult(
            message=msg,
            usage=usage,
            model=model,
            cost_usd=estimate_cost(model, usage),
        )
