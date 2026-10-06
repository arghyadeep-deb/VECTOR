"""Trajectory compressor — 6-stage token-budget-aware context compression.

Pipeline:
  Stage 1: prune_tool_results   — truncate oversized tool_result content
  Stage 2: group_into_turns     — group consecutive messages into turns
  Stage 3: score_turn           — importance score 0.0–1.0 per turn
  Stage 4: drop_turns           — drop lowest-scoring turns to hit token budget
  Stage 5: stitch_turns         — reassemble flat list with omission markers
  Stage 6: validate             — remove orphaned tool_result messages
"""


from loguru import logger

__all__ = [
    "compress_trajectory",
    "estimate_tokens",
    "prune_tool_results",
    "group_into_turns",
    "score_turn",
    "drop_turns",
    "stitch_turns",
    "validate",
    "is_context_limit_error",
    "auto_compact_on_context_limit",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Rough char/4 token estimate — always >= 1."""
    return max(1, len(text) // 4)


def _message_tokens(msg: dict) -> int:
    """Estimate tokens for a single message dict."""
    content = msg.get("content", "")
    if isinstance(content, list):
        # Structured content blocks (Anthropic format)
        total = 0
        for block in content:
            if isinstance(block, dict):
                total += estimate_tokens(block.get("text", "") or block.get("content", ""))
            else:
                total += estimate_tokens(str(block))
        return max(1, total)
    return estimate_tokens(str(content))


def _turn_tokens(turn: list[dict]) -> int:
    return sum(_message_tokens(m) for m in turn)


# ---------------------------------------------------------------------------
# Stage 1 — Prune tool results
# ---------------------------------------------------------------------------

def prune_tool_results(messages: list[dict], max_tool_chars: int = 8000) -> list[dict]:
    """Truncate tool_result content that exceeds max_tool_chars.

    Works with both plain-string content and structured content block lists.
    Appends '\\n...[truncated]' when truncation occurs.
    """
    result: list[dict] = []
    for msg in messages:
        if msg.get("role") != "tool":
            result.append(msg)
            continue

        content = msg.get("content", "")
        if isinstance(content, str):
            if len(content) > max_tool_chars:
                msg = dict(msg)  # shallow copy — never mutate original
                msg["content"] = content[:max_tool_chars] + "\n...[truncated]"
                logger.debug(
                    "[trajectory_compressor] tool_result truncated "
                    f"{len(content)} → {max_tool_chars} chars"
                )
        elif isinstance(content, list):
            new_blocks: list = []
            changed = False
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if len(text) > max_tool_chars:
                        block = dict(block)
                        block["text"] = text[:max_tool_chars] + "\n...[truncated]"
                        changed = True
                        logger.debug(
                            "[trajectory_compressor] tool_result block truncated "
                            f"{len(text)} → {max_tool_chars} chars"
                        )
                new_blocks.append(block)
            if changed:
                msg = dict(msg)
                msg["content"] = new_blocks

        result.append(msg)
    return result


# ---------------------------------------------------------------------------
# Stage 2 — Group into turns
# ---------------------------------------------------------------------------

def group_into_turns(messages: list[dict]) -> list[list[dict]]:
    """Group consecutive messages into logical turns.

    A turn starts with a user message and collects subsequent assistant/tool
    messages until the next user message begins a new turn.
    If the conversation starts with assistant/tool messages (e.g. system
    injections before the first user message) they form turn 0.
    """
    if not messages:
        return []

    turns: list[list[dict]] = []
    current_turn: list[dict] = []

    for msg in messages:
        role = msg.get("role", "")
        if role == "user":
            if current_turn:
                turns.append(current_turn)
            current_turn = [msg]
        else:
            current_turn.append(msg)

    if current_turn:
        turns.append(current_turn)

    return turns


# ---------------------------------------------------------------------------
# Stage 3 — Score turn
# ---------------------------------------------------------------------------

def score_turn(turn: list[dict], index: int, total: int) -> float:
    """Compute importance score 0.0–1.0 for a turn.

    Rules (additive, capped at 1.0):
    - First 2 turns → 1.0 (protect system context)
    - Last 20% of turns → +0.4 recency boost
    - Turn contains a user message → +0.3
    - Turn contains a tool failure (content has "error" or "failed") → +0.2
    - Base score → 0.3
    """
    if index < 2:
        return 1.0

    score = 0.3  # base

    # Recency boost — last 20 % of turns
    if total > 0 and index >= int(total * 0.8):
        score += 0.4

    # User message present
    has_user = any(m.get("role") == "user" for m in turn)
    if has_user:
        score += 0.3

    # Tool failure signal
    for msg in turn:
        content = msg.get("content", "")
        if isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            ).lower()
        else:
            text = str(content).lower()
        if "error" in text or "failed" in text:
            score += 0.2
            break

    return min(1.0, score)


# ---------------------------------------------------------------------------
# Stage 4 — Drop turns
# ---------------------------------------------------------------------------

def drop_turns(
    turns: list[list[dict]],
    scores: list[float],
    target_tokens: int,
) -> tuple[list[list[dict]], list[int]]:
    """Drop lowest-scoring turns until total estimated tokens ≤ target_tokens.

    Never drops:
    - First 2 turns (index 0, 1)
    - Last 3 turns (index -3, -2, -1)

    Returns:
        kept_turns      — list of retained turn lists
        dropped_gaps    — parallel list; dropped_gaps[i] is the number of turns
                          dropped between kept_turns[i-1] and kept_turns[i].
                          Length equals len(kept_turns).  dropped_gaps[0] is
                          always 0 (nothing before the first kept turn that
                          would be omitted).
    """
    if not turns:
        return [], []

    n = len(turns)
    total_tokens = sum(_turn_tokens(t) for t in turns)

    if total_tokens <= target_tokens:
        return list(turns), [0] * n

    # Build list of (score, original_index) for droppable turns only
    # Protected indices: first 2 and last 3
    protected: set[int] = set(range(min(2, n)))
    for i in range(max(0, n - 3), n):
        protected.add(i)

    # Sort droppable by score ascending (drop cheapest first)
    droppable = sorted(
        [(scores[i], i) for i in range(n) if i not in protected],
        key=lambda x: x[0],
    )

    kept_mask = [True] * n

    for _, idx in droppable:
        if total_tokens <= target_tokens:
            break
        total_tokens -= _turn_tokens(turns[idx])
        kept_mask[idx] = False
        logger.debug(f"[trajectory_compressor] dropped turn {idx} (score={scores[idx]:.2f})")

    # Build kept list and gap counts
    kept_turns: list[list[dict]] = []
    dropped_gaps: list[int] = []
    gap = 0

    for i, kept in enumerate(kept_mask):
        if kept:
            kept_turns.append(turns[i])
            dropped_gaps.append(gap)
            gap = 0
        else:
            gap += 1

    # Any trailing gap is silently discarded (last 3 are always kept so
    # this edge case cannot produce orphaned gaps in practice).

    return kept_turns, dropped_gaps


# ---------------------------------------------------------------------------
# Stage 5 — Stitch turns
# ---------------------------------------------------------------------------

def stitch_turns(
    kept_turns: list[list[dict]],
    dropped_gaps: list[int],
) -> list[dict]:
    """Reassemble kept turns into a flat message list.

    Inserts an omission marker before a kept turn when dropped_gaps[i] > 0.
    """
    result: list[dict] = []

    for i, turn in enumerate(kept_turns):
        gap = dropped_gaps[i] if i < len(dropped_gaps) else 0
        if gap > 0:
            result.append(
                {
                    "role": "assistant",
                    "content": f"[{gap} turn{'s' if gap != 1 else ''} omitted]",
                }
            )
        result.extend(turn)

    return result


# ---------------------------------------------------------------------------
# Stage 6 — Validate
# ---------------------------------------------------------------------------

def validate(messages: list[dict]) -> list[dict]:
    """Remove orphaned tool_result messages.

    A tool_result is orphaned if its tool_use_id does not appear in the
    immediately preceding assistant message's tool_use blocks.
    """
    result: list[dict] = []
    prev_tool_use_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role", "")

        if role == "assistant":
            prev_tool_use_ids = set()
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        bid = block.get("id")
                        if bid:
                            prev_tool_use_ids.add(bid)
            for tool_call in msg.get("tool_calls") or []:
                if isinstance(tool_call, dict) and tool_call.get("id"):
                    prev_tool_use_ids.add(tool_call["id"])
            result.append(msg)

        elif role == "tool":
            # Check if there's a matching tool_use id
            tool_use_id = (
                msg.get("tool_use_id")
                or msg.get("tool_call_id")
                or msg.get("id")
            )
            if not tool_use_id or tool_use_id not in prev_tool_use_ids:
                logger.warning(
                    f"[trajectory_compressor] dropping orphaned tool_result "
                    f"id={tool_use_id!r}"
                )
                continue  # drop orphan
            result.append(msg)
            # Don't reset — multiple tool results can follow one assistant message

        else:
            # user / system / other
            prev_tool_use_ids = set()
            result.append(msg)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compress_trajectory(
    messages: list[dict],
    target_tokens: int = 32000,
    *,
    head_protection: int = 4000,
    tail_protection: int = 2000,
) -> list[dict]:
    """Run all 6 compression stages and return a token-budget-aware message list.

    Args:
        messages:        Flat list of conversation messages.
        target_tokens:   Maximum token budget for the returned list.
        head_protection: Reserved token budget for the conversation head
                         (informational — used to tune stage 4 target).
        tail_protection: Reserved token budget for the conversation tail.

    Returns:
        Compressed (or original) message list.
    """
    if not messages:
        return messages

    original_count = len(messages)
    total = sum(_message_tokens(m) for m in messages)

    if total <= target_tokens:
        logger.debug(
            f"[trajectory_compressor] no compression needed "
            f"({total} tokens ≤ {target_tokens})"
        )
        return messages

    logger.info(
        f"[trajectory_compressor] compressing {original_count} messages "
        f"({total} tokens → target {target_tokens})"
    )

    # Stage 1
    msgs = prune_tool_results(messages)

    # Stage 2
    turns = group_into_turns(msgs)
    n = len(turns)

    # Stage 3
    scores = [score_turn(t, i, n) for i, t in enumerate(turns)]

    # Effective target: subtract protected head/tail from budget
    effective_target = max(target_tokens - head_protection - tail_protection, target_tokens // 2)

    # Stage 4
    kept_turns, dropped_gaps = drop_turns(turns, scores, effective_target)

    # Stage 5
    result = stitch_turns(kept_turns, dropped_gaps)

    # Stage 6
    result = validate(result)

    logger.info(
        f"[trajectory_compressor] compressed {original_count} → {len(result)} messages"
    )
    return result


# ---------------------------------------------------------------------------
# Auto-recovery on context limit (ported from high-performance agent harness)
# ---------------------------------------------------------------------------

_CONTEXT_LIMIT_SIGNALS = (
    "context length",
    "context window",
    "maximum context",
    "max context",
    "token limit",
    "too many tokens",
    "prompt is too long",
    "input is too long",
    "request too large",
    "length limit",
    "maximum tokens",
)


def is_context_limit_error(error: str) -> bool:
    """Return True if the error string signals a provider context-limit rejection."""
    lower = error.lower()
    if any(sig in lower for sig in _CONTEXT_LIMIT_SIGNALS):
        return True
    return "exceeded" in lower and "token" in lower


def auto_compact_on_context_limit(
    messages: list[dict],
    error: str,
    target_tokens: int = 32000,
    aggressive: bool = True,
) -> tuple[list[dict], bool]:
    """
    Emergency compaction when the provider returns a context-limit error.

    Call this when an LLM request fails, check is_context_limit_error(error)
    first, then pass messages + error here. Returns (compacted_messages, was_applied).

    If aggressive=True, uses a tighter budget (50% of target) to create headroom.
    Ported from agent/compaction.rs try_auto_compact_after_context_limit().
    """
    if not is_context_limit_error(error):
        return messages, False

    effective_target = (target_tokens // 2) if aggressive else target_tokens
    original_count = len(messages)
    compacted = compress_trajectory(messages, target_tokens=effective_target)

    if len(compacted) < original_count:
        logger.warning(
            "[VECTOR][trajectory_compressor] context-limit auto-recovery: "
            "{} → {} messages (target={})",
            original_count, len(compacted), effective_target,
        )
        return compacted, True

    logger.warning(
        "[VECTOR][trajectory_compressor] context-limit detected but compaction "
        "could not reduce message count (already minimal)"
    )
    return messages, False


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    def _make_conversation(n: int) -> list[dict]:
        msgs: list[dict] = []
        for i in range(n // 2):
            msgs.append({
                "role": "user",
                # ~250 tokens per message → 50 messages × 250 = 12500 tokens total
                "content": f"User message {i}: " + "x " * 1000,
            })
            msgs.append({
                "role": "assistant",
                "content": f"Assistant reply {i}: " + "y " * 1000,
            })
        return msgs

    conversation = _make_conversation(50)
    # 50 messages × ~500 tokens each = ~25000 tokens; target 10000 → must compress
    compressed = compress_trajectory(conversation, target_tokens=10000)

    assert len(compressed) < len(conversation), (
        f"Expected compression: {len(compressed)} should be < {len(conversation)}"
    )
    logger.info(
        f"[trajectory_compressor] smoke test: "
        f"{len(conversation)} → {len(compressed)} messages"
    )

    # Test prune_tool_results
    tool_msgs = [
        {"role": "tool", "content": "A" * 10000, "tool_use_id": "tu_1"},
        {"role": "tool", "content": "short", "tool_use_id": "tu_2"},
    ]
    pruned = prune_tool_results(tool_msgs, max_tool_chars=8000)
    assert len(pruned[0]["content"]) <= 8000 + len("\n...[truncated]")
    assert pruned[1]["content"] == "short"

    # Test validate drops orphan
    orphan_msgs = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_abc", "name": "foo", "input": {}}]},
        {"role": "tool", "content": "result", "tool_use_id": "tu_ORPHAN"},
    ]
    validated = validate(orphan_msgs)
    tool_results = [m for m in validated if m.get("role") == "tool"]
    assert len(tool_results) == 0, "Orphan tool_result should have been dropped"

    print("PASS: trajectory_compressor.py OK")
