"""Context engine — token-aware conversation compression.

Abstract base for pluggable context engines. Built-in ContextCompressor
is the default. Controls when compaction fires, performs summarization,
and tracks token usage.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from abc import ABC, abstractmethod
from typing import Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough char/4 token estimate — always >= 1."""
    return max(1, len(text) // 4)


def _message_tokens(msg: dict) -> int:
    """Estimate tokens for a single message dict."""
    content = msg.get("content", "")
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                total += _estimate_tokens(
                    block.get("text", "") or block.get("content", "")
                )
            else:
                total += _estimate_tokens(str(block))
        return max(1, total)
    return _estimate_tokens(str(content))


# ---------------------------------------------------------------------------
# Priority constants — lower number = higher priority (never drop)
# ---------------------------------------------------------------------------
_PRIORITY_SYSTEM = 1
_PRIORITY_RECENT = 2
_PRIORITY_TOOL_RESULT = 3
_PRIORITY_USER = 4
_PRIORITY_ASSISTANT = 5


def priority_retain(
    messages: list[dict],
    budget_tokens: int,
    model_context_length: int,
    tail_n: int = 6,
) -> list[dict]:
    """Retain messages within budget_tokens by dropping lowest-priority ones first.

    Priority categories (1 = most important, never dropped):
      1  system messages
      2  last `tail_n` messages (recency protection)
      3  tool_result (role == "tool") messages
      4  user messages
      5  assistant messages

    Rules:
    - Never drops system messages.
    - Never drops the last `tail_n` messages.
    - Drops higher-priority numbers first (assistant before user before tool).
    - Stops as soon as total tokens ≤ budget_tokens.

    Args:
        messages:             Full conversation message list.
        budget_tokens:        Target token budget.
        model_context_length: Maximum context length (informational guard).
        tail_n:               Number of recent messages to always protect.

    Returns:
        Filtered message list preserving original order.
    """
    if not messages:
        return messages

    total = sum(_message_tokens(m) for m in messages)
    if total <= budget_tokens:
        return messages

    n = len(messages)
    tail_indices: set[int] = set(range(max(0, n - tail_n), n))

    def _priority(idx: int, msg: dict) -> int:
        if msg.get("role") == "system":
            return _PRIORITY_SYSTEM
        if idx in tail_indices:
            return _PRIORITY_RECENT
        role = msg.get("role", "")
        if role == "tool":
            return _PRIORITY_TOOL_RESULT
        if role == "user":
            return _PRIORITY_USER
        return _PRIORITY_ASSISTANT  # assistant or unknown

    # Build list of (priority, index) sorted: highest priority number first
    # (i.e. drop assistants before users before tool_results)
    candidates = sorted(
        [
            (_priority(i, m), i)
            for i, m in enumerate(messages)
            if _priority(i, m) > _PRIORITY_RECENT  # never touch system or tail
        ],
        key=lambda x: (-x[0], -x[1]),  # highest priority-number first, then latest first
    )

    drop_set: set[int] = set()
    for pri, idx in candidates:
        if total <= budget_tokens:
            break
        total -= _message_tokens(messages[idx])
        drop_set.add(idx)
        logger.debug(
            f"[context_engine] priority_retain: dropping idx={idx} "
            f"role={messages[idx].get('role')} priority={pri}"
        )

    retained = [m for i, m in enumerate(messages) if i not in drop_set]
    logger.info(
        f"[context_engine] priority_retain: {n} → {len(retained)} messages"
    )
    return retained


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class ContextEngine(ABC):
    """Base class for context management strategies."""

    last_prompt_tokens: int = 0
    last_completion_tokens: int = 0
    last_total_tokens: int = 0
    threshold_tokens: int = 0
    context_length: int = 0
    compression_count: int = 0
    threshold_percent: float = 0.75
    protect_first_n: int = 3
    protect_last_n: int = 6

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def update_from_response(self, usage: dict) -> None: ...

    @abstractmethod
    def should_compress(self, prompt_tokens: Optional[int] = None) -> bool: ...

    @abstractmethod
    def compress(
        self,
        messages: list,
        current_tokens: Optional[int] = None,
        focus_topic: Optional[str] = None,
    ) -> list: ...

    def has_content_to_compress(self, messages: list) -> bool:
        return True

    def on_session_start(self, session_id: str, **kwargs) -> None: ...

    def on_session_end(self, session_id: str, messages: list) -> None: ...

    def on_session_reset(self) -> None:
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self.compression_count = 0

    def update_model(self, model: str, context_length: int, **kwargs) -> None:
        self.context_length = context_length
        self.threshold_tokens = int(context_length * self.threshold_percent)

    def get_status(self) -> dict:
        return {
            "last_prompt_tokens": self.last_prompt_tokens,
            "threshold_tokens": self.threshold_tokens,
            "context_length": self.context_length,
            "usage_percent": (
                min(100, self.last_prompt_tokens / self.context_length * 100)
                if self.context_length
                else 0
            ),
            "compression_count": self.compression_count,
        }


# ---------------------------------------------------------------------------
# Default implementation
# ---------------------------------------------------------------------------

class ContextCompressor(ContextEngine):
    """Default compressor — priority-based retention with summary injection."""

    @property
    def name(self) -> str:
        return "compressor"

    def __init__(
        self,
        context_length: int = 128000,
        threshold_percent: float = 0.75,
        protect_first_n: int = 3,
        protect_last_n: int = 6,
    ):
        self.context_length = context_length
        self.threshold_percent = threshold_percent
        self.threshold_tokens = int(context_length * threshold_percent)
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self.last_prompt_tokens = 0
        self.last_completion_tokens = 0
        self.last_total_tokens = 0
        self.compression_count = 0

    def update_from_response(self, usage: dict) -> None:
        self.last_prompt_tokens = usage.get(
            "input_tokens", usage.get("prompt_tokens", 0)
        )
        self.last_completion_tokens = usage.get(
            "output_tokens", usage.get("completion_tokens", 0)
        )
        self.last_total_tokens = self.last_prompt_tokens + self.last_completion_tokens

    def should_compress(self, prompt_tokens: Optional[int] = None) -> bool:
        check = prompt_tokens if prompt_tokens is not None else self.last_prompt_tokens
        return check > self.threshold_tokens

    def compress(
        self,
        messages: list,
        current_tokens: Optional[int] = None,
        focus_topic: Optional[str] = None,
    ) -> list:
        """Compress messages using priority_retain + summary injection.

        Steps:
        1. Check should_compress — return early if not needed.
        2. Call priority_retain to fit within threshold_tokens.
        3. Insert a summary marker so downstream code knows compression occurred.
        4. Increment compression_count.
        5. Return compressed list.
        """
        if len(messages) < 6:
            return messages

        check_tokens = current_tokens if current_tokens is not None else self.last_prompt_tokens
        if not self.should_compress(check_tokens):
            return messages

        budget = self.threshold_tokens
        retained = priority_retain(
            messages,
            budget_tokens=budget,
            model_context_length=self.context_length,
            tail_n=self.protect_last_n,
        )

        n_dropped = len(messages) - len(retained)
        if n_dropped == 0:
            return messages

        topic = focus_topic or "ongoing task"
        summary_msg: dict = {
            "role": "assistant",
            "content": (
                f"<compressed>Compressed {n_dropped} messages to fit context window. "
                f"Focus: {topic}</compressed>"
            ),
        }

        # Insert summary after protected head, before the retained body
        head = [m for m in retained[:self.protect_first_n]]
        body = retained[self.protect_first_n:]
        result = head + [summary_msg] + body

        self.compression_count += 1
        logger.info(
            f"[context_engine] compressed {len(messages)} → {len(result)} messages "
            f"(compression #{self.compression_count})"
        )
        return result


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_context_engine(
    model_id: str,
    context_length: int,
) -> ContextCompressor:
    """Return a pre-configured ContextCompressor for the given model.

    Args:
        model_id:       Model identifier string (used for threshold tuning).
        context_length: Maximum context window in tokens.

    Returns:
        ContextCompressor ready to use.
    """
    # Tune threshold based on known model families
    if "opus" in model_id.lower():
        threshold_percent = 0.80
    elif "sonnet" in model_id.lower():
        threshold_percent = 0.75
    elif "haiku" in model_id.lower():
        threshold_percent = 0.70
    else:
        threshold_percent = 0.75

    engine = ContextCompressor(
        context_length=context_length,
        threshold_percent=threshold_percent,
    )
    logger.debug(
        f"[context_engine] created engine for model={model_id!r} "
        f"context={context_length} threshold={engine.threshold_tokens}"
    )
    return engine


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # --- priority_retain ---
    # Each message is ~500 tokens (2000 chars / 4); 21 messages × 500 = ~10500 tokens total
    # budget_tokens=3000 forces drops
    msgs: list[dict] = (
        [{"role": "system", "content": "You are VECTOR. " * 50}]
        + [
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}: " + "word " * 500,
            }
            for i in range(20)
        ]
    )
    retained = priority_retain(msgs, budget_tokens=3000, model_context_length=128000)
    assert retained[0]["role"] == "system", "System message must always be retained"
    # Last 6 must be kept
    assert msgs[-1] in retained, "Last message must be retained"
    assert len(retained) < len(msgs), "Some messages should have been dropped"

    # --- ContextCompressor.compress ---
    # Use a small context engine so the threshold is easily exceeded.
    # context_length=10000 → threshold=7500 tokens
    # 31 messages × ~700 tokens each = ~21700 tokens → should_compress triggers
    engine = get_context_engine("claude-sonnet-4-6", 10000)
    engine.update_from_response({"input_tokens": 9_000, "output_tokens": 200})

    long_messages: list[dict] = [
        {"role": "system", "content": "System prompt. " * 20}
    ] + [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            # ~700 tokens per message
            "content": "Content line. " * 200,
        }
        for i in range(30)
    ]

    compressed = engine.compress(long_messages, focus_topic="VECTOR build")
    assert len(compressed) < len(long_messages), (
        f"Expected compression but got same length: {len(compressed)}"
    )
    assert engine.compression_count == 1

    # Summary marker present
    contents = [m.get("content", "") for m in compressed]
    assert any("<compressed>" in str(c) for c in contents), (
        "Expected <compressed> summary marker in output"
    )

    # --- factory ---
    e2 = get_context_engine("claude-haiku-3-5", 200000)
    assert e2.threshold_tokens == int(200000 * 0.70)

    print("PASS: engine.py OK")
