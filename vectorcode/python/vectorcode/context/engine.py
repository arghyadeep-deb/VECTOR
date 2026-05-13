"""VectorCode ContextEngine — token budget manager for conversations.

Ports the abstract ContextEngine base from Hermes agent/context_engine.py and
implements a concrete VectorContextEngine that:
  - Tracks token usage from API responses
  - Decides when to compact based on a configurable threshold (default 85%)
  - Trims message lists to a token budget while protecting important messages
  - Exposes the same interface that VectorCode's compactor.py expects

This is the decision layer — the actual compaction work is done by
context/compactor.py (ContextCompactor) and context/trajectory_compressor.py
(TrajectoryCompressor). ContextEngine decides *when* to compact and *what*
to retain; the compactors decide *how* to summarise.

Model context windows (get_token_budget):
  Uses providers/capability_probe.py when available, falls back to a built-in
  lookup table for common Ollama models.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}


# ── Token budget constants ────────────────────────────────────────────────────

_DEFAULT_THRESHOLD = 0.85          # compact when > 85% of context used
_CHARS_PER_TOKEN = 4               # rough estimate for cost-free token counting
_ALWAYS_KEEP_LAST_N = 8            # always preserve this many tail messages
_PROTECT_TOOL_RESULTS = True       # tool result messages have priority over plain assistant turns
_IMAGE_TOKEN_ESTIMATE = 1_600      # flat token cost per image content block

# Built-in context window fallback table (tokens) for common models.
# capability_probe.py's MODEL_CONTEXT_LENGTHS is preferred when importable.
_BUILTIN_CONTEXT_WINDOWS: Dict[str, int] = {
    # Ollama custom models
    "vector-focus":        8_192,
    "vector-ambient":      8_192,
    "vector-reasoning":   32_768,
    "vector-coder":       32_768,
    "vector-multilingual": 32_768,
    "vector-deep":        65_536,
    "vector-chairman":    131_072,
    # Base Ollama models
    "gemma4:e2b":          8_192,
    "gemma4:e4b":          8_192,
    "gemma4:26b":         65_536,
    "gemma4:31b":         131_072,
    "qwen3:8b":           32_768,
    "qwen3:14b":          32_768,
    "qwen3:30b-a3b":      131_072,
    "deepseek-r1:14b":    32_768,
    "devstral:24b":       32_768,
    "mistral-small3.1":   32_768,
    "nomic-embed-text":   8_192,
    # Cloud / API models
    "claude-sonnet-4-6":  200_000,
    "claude-opus-4":      200_000,
    "gpt-4o":             128_000,
    "gpt-4-turbo":        128_000,
    "gpt-3.5-turbo":      16_385,
    "gemini-1.5-pro":     1_000_000,
    "gemini-2.5-pro":     1_000_000,
}

_DEFAULT_CONTEXT_WINDOW = 32_768   # fallback when model unknown


# ── Token estimation helpers ──────────────────────────────────────────────────

def _content_char_cost(content: Any) -> int:
    """Return character-equivalent cost of a message's 'content' field.

    Handles plain strings and multimodal lists with per-image cost.
    Mirrors _content_length_for_budget() from compactor.py.
    """
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, str):
                total += len(part)
            elif isinstance(part, dict):
                ptype = part.get("type", "")
                if ptype in {"image_url", "input_image", "image"}:
                    total += _IMAGE_TOKEN_ESTIMATE * _CHARS_PER_TOKEN
                else:
                    total += len(part.get("text", "") or "")
        return total
    return len(str(content))


def estimate_tokens(messages: List[Dict[str, Any]]) -> int:
    """Rough token estimate for a message list (char / 4).

    Module-level function exposed for use by the compactor and trajectory
    compressor without needing a ContextEngine instance.
    """
    total_chars = sum(_content_char_cost(m.get("content")) for m in messages)
    # Add overhead for tool_calls argument strings
    for msg in messages:
        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict):
                args = tc.get("function", {}).get("arguments", "") or ""
                total_chars += len(args)
    return total_chars // _CHARS_PER_TOKEN


def get_token_budget(model: str) -> int:
    """Return context window (token budget) for a model.

    Priority: capability_probe.py MODEL_CONTEXT_LENGTHS > built-in table >
    CONFIG['context_window'] default > hard fallback.
    """
    try:
        from providers.capability_probe import MODEL_CONTEXT_LENGTHS
        if model in MODEL_CONTEXT_LENGTHS:
            return MODEL_CONTEXT_LENGTHS[model]
    except Exception:
        pass

    # Strip provider prefixes like "ollama:qwen3:14b"
    bare = model.split(":")[-1] if ":" in model else model
    if model in _BUILTIN_CONTEXT_WINDOWS:
        return _BUILTIN_CONTEXT_WINDOWS[model]
    if bare in _BUILTIN_CONTEXT_WINDOWS:
        return _BUILTIN_CONTEXT_WINDOWS[bare]

    # CONFIG override
    cfg_window = CONFIG.get("context_window")
    if cfg_window:
        try:
            return int(cfg_window)
        except (TypeError, ValueError):
            pass

    logger.debug(
        f"[VECTOR][context_engine] unknown model '{model}' — "
        f"defaulting to {_DEFAULT_CONTEXT_WINDOW} tokens"
    )
    return _DEFAULT_CONTEXT_WINDOW


# ── priority_retain ───────────────────────────────────────────────────────────

def priority_retain(messages: List[Dict[str, Any]], budget: int) -> List[Dict[str, Any]]:
    """Trim a message list to fit within a token budget.

    Retention priority (highest to lowest):
      1. System message (always kept)
      2. Last _ALWAYS_KEEP_LAST_N messages (always kept)
      3. Tool result messages (keep over plain assistant turns)
      4. User messages (keep over assistant turns)
      5. Assistant turns (dropped first when over budget)

    The returned list is always a valid OpenAI-format conversation —
    orphaned tool_result messages whose tool_call_id has no preceding
    assistant tool_call are dropped automatically.
    """
    if not messages:
        return messages

    n = len(messages)
    always_last = min(_ALWAYS_KEEP_LAST_N, n)
    tail_indices = set(range(n - always_last, n))

    # System messages
    sys_indices = {i for i, m in enumerate(messages) if m.get("role") == "system"}

    # Classify remaining messages by priority score
    # 3 = tool result, 2 = user, 1 = assistant, 0 = unknown
    def _priority(msg: Dict[str, Any]) -> int:
        role = msg.get("role", "")
        if role == "tool":
            return 3
        if role == "user":
            return 2
        if role == "assistant":
            return 1
        return 0

    # Build keep set: system + tail always in
    keep = set(sys_indices) | tail_indices

    # Add middle messages by priority until budget exhausted
    current_tokens = estimate_tokens([messages[i] for i in keep])
    if current_tokens <= budget:
        # We have budget remaining — try to add middle messages
        middle_sorted = sorted(
            [i for i in range(n) if i not in keep],
            key=lambda i: (_priority(messages[i]), i),
            reverse=True,  # highest priority and latest first
        )
        for i in middle_sorted:
            msg_tokens = _content_char_cost(messages[i].get("content")) // _CHARS_PER_TOKEN + 5
            if current_tokens + msg_tokens <= budget:
                keep.add(i)
                current_tokens += msg_tokens

    # Build retained list in original order
    retained = [messages[i] for i in sorted(keep)]

    # Remove orphaned tool results (tool_call_id with no matching assistant call)
    tool_call_ids: set[str] = set()
    for msg in retained:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    cid = tc.get("id", "")
                    if cid:
                        tool_call_ids.add(cid)

    cleaned = []
    for msg in retained:
        if msg.get("role") == "tool":
            cid = msg.get("tool_call_id", "")
            if cid and cid not in tool_call_ids:
                continue  # orphaned — skip
        cleaned.append(msg)

    return cleaned


# ── ContextEngine class ───────────────────────────────────────────────────────

class ContextEngine:
    """Token budget manager for VectorCode conversations.

    Tracks actual token usage reported by the LLM API (via update_from_response)
    and triggers compaction when usage exceeds the configured threshold.

    Mirrors the Hermes ContextEngine abstract base but as a concrete
    implementation that VectorCode's agent loop can use directly.
    """

    def __init__(
        self,
        model: str = "vector-focus",
        threshold: float = _DEFAULT_THRESHOLD,
    ) -> None:
        self.model = model
        self.threshold_percent: float = max(0.50, min(threshold, 0.99))

        # Token accounting
        self.context_length: int = get_token_budget(model)
        self.threshold_tokens: int = int(self.context_length * self.threshold_percent)
        self.last_prompt_tokens: int = 0
        self.last_completion_tokens: int = 0
        self.last_total_tokens: int = 0
        self.compression_count: int = 0

    # ── Token tracking ───────────────────────────────────────────────────────

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        """Update token state from an API response usage dict.

        Accepts both OpenAI style (prompt_tokens / completion_tokens) and
        Anthropic style (input_tokens / output_tokens).
        """
        if not usage:
            return
        prompt = int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or 0
        )
        completion = int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        )
        self.last_prompt_tokens = prompt
        self.last_completion_tokens = completion
        self.last_total_tokens = prompt + completion
        logger.debug(
            f"[VECTOR][context_engine] usage: prompt={prompt} "
            f"completion={completion} threshold={self.threshold_tokens}"
        )

    # ── Compaction decision ──────────────────────────────────────────────────

    def should_compact(self, messages: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Return True when context usage exceeds the threshold.

        When API token counts are available (last_prompt_tokens > 0) they are
        used. Otherwise falls back to a rough char-based estimate of the
        provided message list.
        """
        if self.last_prompt_tokens > 0:
            return self.last_prompt_tokens >= self.threshold_tokens

        if messages:
            estimated = estimate_tokens(messages)
            return estimated >= self.threshold_tokens

        return False

    def should_compact_preflight(self, messages: List[Dict[str, Any]]) -> bool:
        """Quick pre-flight check using char estimate — no real token count needed."""
        if not messages:
            return False
        estimated = estimate_tokens(messages)
        return estimated >= self.threshold_tokens

    # ── Budget management ────────────────────────────────────────────────────

    def get_token_budget(self, model: Optional[str] = None) -> int:
        """Return the context window for this engine's model (or a given model)."""
        return get_token_budget(model or self.model)

    def get_budget_remaining(self) -> int:
        """Tokens remaining before compaction threshold is hit."""
        if self.last_prompt_tokens > 0:
            return max(0, self.threshold_tokens - self.last_prompt_tokens)
        return self.threshold_tokens

    def trim_to_budget(
        self,
        messages: List[Dict[str, Any]],
        budget_ratio: float = 0.80,
    ) -> List[Dict[str, Any]]:
        """Trim messages to fit within budget_ratio of the context window.

        Uses priority_retain() internally. budget_ratio=0.80 means trim to
        80% of the context window to leave headroom for the next response.
        """
        budget = int(self.context_length * max(0.10, min(budget_ratio, 0.99)))
        return priority_retain(messages, budget=budget)

    # ── Model switching ──────────────────────────────────────────────────────

    def update_model(self, model: str) -> None:
        """Recalculate context window and threshold after a model switch."""
        self.model = model
        self.context_length = get_token_budget(model)
        self.threshold_tokens = int(self.context_length * self.threshold_percent)
        logger.info(
            f"[VECTOR][context_engine] model → '{model}' "
            f"(context={self.context_length}, threshold={self.threshold_tokens})"
        )

    # ── Session lifecycle ────────────────────────────────────────────────────

    def on_session_reset(self) -> None:
        """Reset per-session counters (call on /new or /reset)."""
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self.compression_count = 0

    # ── Status ───────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Return current token state dict for display / logging."""
        usage_pct = (
            min(100.0, self.last_prompt_tokens / self.context_length * 100)
            if self.context_length and self.last_prompt_tokens
            else 0.0
        )
        return {
            "model": self.model,
            "context_length": self.context_length,
            "threshold_tokens": self.threshold_tokens,
            "last_prompt_tokens": self.last_prompt_tokens,
            "last_completion_tokens": self.last_completion_tokens,
            "usage_percent": round(usage_pct, 1),
            "compression_count": self.compression_count,
        }


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Test 1: Basic instantiation
    engine = ContextEngine(model="vector-focus", threshold=0.85)
    assert engine.context_length == _BUILTIN_CONTEXT_WINDOWS["vector-focus"]
    assert engine.threshold_tokens == int(engine.context_length * 0.85)

    # Test 2: update_from_response (OpenAI format)
    engine.update_from_response({"prompt_tokens": 100, "completion_tokens": 50})
    assert engine.last_prompt_tokens == 100
    assert engine.last_completion_tokens == 50
    assert engine.last_total_tokens == 150

    # Test 3: update_from_response (Anthropic format)
    engine2 = ContextEngine(model="vector-focus")
    engine2.update_from_response({"input_tokens": 200, "output_tokens": 80})
    assert engine2.last_prompt_tokens == 200

    # Test 4: should_compact — false when under threshold
    engine3 = ContextEngine(model="vector-focus", threshold=0.85)
    engine3.update_from_response({"prompt_tokens": 100, "completion_tokens": 10})
    assert engine3.should_compact() is False

    # Test 5: should_compact — true when over threshold
    engine4 = ContextEngine(model="vector-focus", threshold=0.85)
    engine4.update_from_response({"prompt_tokens": 8000, "completion_tokens": 0})
    assert engine4.should_compact() is True

    # Test 6: estimate_tokens module-level function
    msgs = [
        {"role": "system", "content": "You are VECTOR."},
        {"role": "user",   "content": "hello world"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    tokens = estimate_tokens(msgs)
    assert tokens > 0

    # Test 7: should_compact_preflight with message list
    tiny_msgs = [{"role": "user", "content": "hi"}]
    assert engine.should_compact_preflight(tiny_msgs) is False

    # Test 8: get_token_budget returns known value
    assert get_token_budget("vector-chairman") == 131_072
    assert get_token_budget("unknown-model-xyz") == _DEFAULT_CONTEXT_WINDOW

    # Test 9: priority_retain keeps system and tail
    long_msgs = [{"role": "system", "content": "sys"}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}" * 50}
        for i in range(20)
    ]
    retained = priority_retain(long_msgs, budget=500)
    assert any(m["role"] == "system" for m in retained), "system must survive"
    assert len(retained) <= len(long_msgs)

    # Test 10: trim_to_budget returns list
    trimmed = engine.trim_to_budget(msgs, budget_ratio=0.80)
    assert isinstance(trimmed, list)

    # Test 11: on_session_reset clears counters
    engine.compression_count = 5
    engine.last_prompt_tokens = 100
    engine.on_session_reset()
    assert engine.last_prompt_tokens == 0
    assert engine.compression_count == 0

    # Test 12: update_model recalculates threshold
    engine.update_model("vector-chairman")
    assert engine.context_length == 131_072

    # Test 13: get_status returns dict with required keys
    status = engine.get_status()
    for key in ("model", "context_length", "threshold_tokens", "usage_percent"):
        assert key in status, f"Missing key: {key}"

    print("OK")
