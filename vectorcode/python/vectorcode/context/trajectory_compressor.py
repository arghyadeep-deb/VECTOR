"""VectorCode TrajectoryCompressor — compress agent message histories.

Ports the core compression algorithm from Hermes trajectory_compressor.py,
adapted to OpenAI message format ({role, content}) instead of Hermes training
format ({from, value}).

Compression pipeline:
  Stage 1: Prune tool results > 500 chars to a 1-line summary stub
  Stage 2: Group messages into logical turns
  Stage 3: Score each turn by importance
  Stage 4: Drop lowest-scoring turns until within 80% token budget
  Stage 5: Re-stitch with "[N turns omitted]" placeholder
  Stage 6: Validate — no orphaned tool_results, system message present

This module is *stateless* — every function is pure (no side effects on the
passed lists) and the TrajectoryCompressor class wraps them with config and
optional LLM-based summarization for Stage 4 dropped turns.

Token estimation:
  Uses context/engine.estimate_tokens() (char/4) for cost-free counting.
  No HuggingFace tokenizer dependency required.
"""

import sys
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

# Import token estimation from sibling module (avoids circular import)
try:
    from context.engine import estimate_tokens, get_token_budget, _CHARS_PER_TOKEN
except ImportError:
    _CHARS_PER_TOKEN = 4

    def estimate_tokens(messages: List[Dict[str, Any]]) -> int:  # type: ignore[misc]
        total = sum(len(str(m.get("content") or "")) for m in messages)
        return total // _CHARS_PER_TOKEN

    def get_token_budget(model: str) -> int:  # type: ignore[misc]
        return 32_768


# ── Configuration ──────────────────────────────────────────────────────────────

_DEFAULT_TARGET_RATIO = 0.80       # compress until within 80% of context window
_TOOL_RESULT_MAX_CHARS = 500       # prune tool results longer than this (Stage 1)
_ALWAYS_PROTECT_LAST_N = 5         # always keep the last N turns (Stage 3)
_TURN_IMPORTANCE: Dict[str, float] = {
    # Higher = more important = keep longer
    "last_5":      1.0,   # recent turns always protected
    "tool_error":  0.8,   # failed tool calls have debugging value
    "decision":    0.7,   # decision / result messages
    "tool_result": 0.5,   # successful tool results (partially pruned in stage 1)
    "user":        0.6,   # user messages
    "assistant":   0.4,   # assistant reasoning (least unique)
    "system":      1.0,   # system message always protected
}
_DECISION_MARKERS = {
    "decision:", "decided:", "final approach:", "going with", "using:",
    "architecture:", "approved:", "DECISION:", "chosen:", "we will",
}

# Placeholder inserted where dropped turns used to be
_OMITTED_PLACEHOLDER_TEMPLATE = "[{n} turns omitted during context compression]"


# ── Stage 1: Prune large tool results ─────────────────────────────────────────

def _is_tool_error(content: str) -> bool:
    """Heuristic: does a tool result look like an error?"""
    if not content:
        return False
    head = content.lstrip()
    if head.startswith("{"):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                if parsed.get("error"):
                    return True
                status = str(parsed.get("status", "")).strip().lower()
                if status in {"error", "failed", "failure", "timeout"}:
                    return True
        except Exception:
            pass
    first = (content.splitlines()[0] if content.splitlines() else "").strip().lower()
    return (
        first.startswith("error:")
        or first.startswith("failed:")
        or first.startswith("traceback ")
        or first.startswith("exception:")
    )


def _prune_tool_results(
    messages: List[Dict[str, Any]], max_chars: int = _TOOL_RESULT_MAX_CHARS
) -> List[Dict[str, Any]]:
    """Stage 1: Replace oversized tool result bodies with a 1-line summary stub.

    Errors are preserved intact — they have high debugging value.
    The tail (_ALWAYS_PROTECT_LAST_N) messages are never pruned in Stage 1.
    """
    pruned = [m.copy() for m in messages]
    protect_from = max(0, len(pruned) - _ALWAYS_PROTECT_LAST_N)

    for i, msg in enumerate(pruned):
        if i >= protect_from:
            break
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if not isinstance(content, str) or len(content) <= max_chars:
            continue
        if _is_tool_error(content):
            continue  # keep errors intact
        # Replace with summary stub
        lines = content.count("\n") + 1
        pruned[i] = {
            **msg,
            "content": (
                f"[Tool result pruned: {len(content):,} chars / {lines} lines — "
                "content cleared to save context space]"
            ),
        }

    return pruned


# ── Stage 2: Group messages into logical turns ─────────────────────────────────

@dataclass
class _Turn:
    """A logical turn = one user/assistant exchange plus any tool results."""

    messages: List[Dict[str, Any]] = field(default_factory=list)
    index_start: int = 0           # index of first message in original list

    @property
    def role(self) -> str:
        """Dominant role of the turn.

        Returns 'system' for system-only turns. Otherwise returns the role
        of the first non-system message in the turn.
        """
        roles = [m.get("role", "") for m in self.messages]
        if all(r == "system" for r in roles):
            return "system"
        for r in roles:
            if r not in ("system", ""):
                return r
        return "unknown"

    @property
    def has_tool_error(self) -> bool:
        for m in self.messages:
            if m.get("role") == "tool" and _is_tool_error(
                str(m.get("content") or "")
            ):
                return True
        return False

    @property
    def has_decision(self) -> bool:
        for m in self.messages:
            text = str(m.get("content") or "").lower()
            if any(marker in text for marker in _DECISION_MARKERS):
                return True
        return False

    def token_cost(self) -> int:
        return estimate_tokens(self.messages)


def _group_into_turns(messages: List[Dict[str, Any]]) -> List[_Turn]:
    """Stage 2: Group a flat message list into logical turns.

    A turn starts on each 'user' or 'assistant' message (except tool results,
    which attach to the preceding assistant turn). System messages form their
    own single-message turn at position 0.
    """
    if not messages:
        return []

    turns: List[_Turn] = []
    current_turn: Optional[_Turn] = None

    for i, msg in enumerate(messages):
        role = msg.get("role", "")

        if role == "system":
            # System messages always get their own turn
            if current_turn:
                turns.append(current_turn)
            turns.append(_Turn(messages=[msg], index_start=i))
            current_turn = None
            continue

        if role == "tool":
            # Tool results attach to the current (assistant) turn
            if current_turn is not None:
                current_turn.messages.append(msg)
            else:
                # Orphaned tool result — create a synthetic turn for it
                current_turn = _Turn(messages=[msg], index_start=i)
            continue

        # user or assistant: starts a new turn
        if current_turn is not None:
            turns.append(current_turn)
        current_turn = _Turn(messages=[msg], index_start=i)

    if current_turn is not None:
        turns.append(current_turn)

    return turns


# ── Stage 3: Score turns by importance ─────────────────────────────────────────

def _score_turn(turn: _Turn, total_turns: int, turn_index: int) -> float:
    """Stage 3: Assign an importance score to a turn (0.0 – 1.0).

    Higher score = more important = keep when dropping turns.
    """
    # System message: always maximum score
    if turn.role == "system":
        return 1.0

    # Last N turns: always protected
    tail_threshold = max(0, total_turns - _ALWAYS_PROTECT_LAST_N)
    if turn_index >= tail_threshold:
        return _TURN_IMPORTANCE["last_5"]

    # Tool errors: high value for debugging
    if turn.has_tool_error:
        return _TURN_IMPORTANCE["tool_error"]

    # Decision turns: preserve
    if turn.has_decision:
        return _TURN_IMPORTANCE["decision"]

    # Role-based fallback
    role = turn.role
    if role == "user":
        return _TURN_IMPORTANCE["user"]
    if role == "assistant":
        # Turns with tool_calls are more valuable than pure reasoning
        for m in turn.messages:
            if m.get("tool_calls"):
                return _TURN_IMPORTANCE["tool_result"]
        return _TURN_IMPORTANCE["assistant"]

    return 0.3


# ── Stage 4: Drop lowest-scoring turns ────────────────────────────────────────

def _drop_turns_to_budget(
    turns: List[_Turn],
    token_budget: int,
) -> Tuple[List[_Turn], List[_Turn]]:
    """Stage 4: Drop lowest-scoring turns until within token budget.

    Returns (kept_turns, dropped_turns).
    System turns and the last N turns are never dropped.
    """
    total_turns = len(turns)
    scores = [_score_turn(t, total_turns, i) for i, t in enumerate(turns)]

    # Build candidates: (score, index) sorted ascending (lowest first = drop first)
    # Never drop system (role=='system') or protected tail
    tail_start = max(0, total_turns - _ALWAYS_PROTECT_LAST_N)
    candidates = sorted(
        [
            (scores[i], i)
            for i, turn in enumerate(turns)
            if turn.role != "system" and i < tail_start
        ],
        key=lambda x: (x[0], -x[1]),  # lowest score first; older before newer on tie
    )

    current_tokens = sum(t.token_cost() for t in turns)
    drop_indices: set = set()

    for _score, idx in candidates:
        if current_tokens <= token_budget:
            break
        saved = turns[idx].token_cost()
        drop_indices.add(idx)
        current_tokens -= saved

    kept = [t for i, t in enumerate(turns) if i not in drop_indices]
    dropped = [t for i, t in enumerate(turns) if i in drop_indices]
    return kept, dropped


# ── Stage 5: Re-stitch with placeholder ──────────────────────────────────────

def _stitch_turns(
    original_turns: List[_Turn],
    kept_turns: List[_Turn],
) -> List[Dict[str, Any]]:
    """Stage 5: Flatten kept turns back to a message list with omission placeholders.

    When a contiguous block of turns was dropped, injects a single user
    message: "[N turns omitted during context compression]".
    """
    kept_set = {id(t) for t in kept_turns}
    result: List[Dict[str, Any]] = []
    omitted_count = 0

    for turn in original_turns:
        if id(turn) in kept_set:
            # Flush any pending omission placeholder before adding kept turn
            if omitted_count > 0:
                result.append({
                    "role": "user",
                    "content": _OMITTED_PLACEHOLDER_TEMPLATE.format(n=omitted_count),
                })
                omitted_count = 0
            result.extend(turn.messages)
        else:
            omitted_count += len(turn.messages)

    if omitted_count > 0:
        result.append({
            "role": "user",
            "content": _OMITTED_PLACEHOLDER_TEMPLATE.format(n=omitted_count),
        })

    return result


# ── Stage 6: Validate ─────────────────────────────────────────────────────────

def _validate_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stage 6: Remove orphaned tool_results (no matching assistant tool_call).

    An orphaned tool_result occurs when its parent assistant message was
    dropped during Stage 4. Keeping it would cause API errors.
    """
    # Build set of all tool_call IDs present in assistant messages
    valid_tool_call_ids: set = set()
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    cid = tc.get("id", "")
                    if cid:
                        valid_tool_call_ids.add(cid)

    cleaned: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "tool":
            cid = msg.get("tool_call_id", "")
            if cid and cid not in valid_tool_call_ids:
                logger.debug(
                    f"[VECTOR][traj_compress] dropping orphaned tool_result "
                    f"tool_call_id={cid}"
                )
                continue
        cleaned.append(msg)

    return cleaned


# ── Public API: functional ────────────────────────────────────────────────────

def estimate_trajectory_tokens(messages: List[Dict[str, Any]]) -> int:
    """Return rough token estimate for a message list. Module-level alias."""
    return estimate_tokens(messages)


def compress_trajectory(
    messages: List[Dict[str, Any]],
    model: str = "vector-focus",
    target_ratio: float = _DEFAULT_TARGET_RATIO,
) -> List[Dict[str, Any]]:
    """Full 6-stage compression pipeline. Returns a shorter message list.

    Args:
        messages: OpenAI-format conversation list.
        model: Model name used to determine context window.
        target_ratio: Target fraction of context window (default 0.80).

    Returns:
        Compressed message list. May be identical to input if already within budget.
    """
    if not messages:
        return messages

    context_window = get_token_budget(model)
    token_budget = int(context_window * max(0.10, min(target_ratio, 0.99)))
    current_tokens = estimate_tokens(messages)

    if current_tokens <= token_budget:
        logger.debug(
            f"[VECTOR][traj_compress] no compression needed "
            f"({current_tokens} / {token_budget} tokens)"
        )
        return messages

    logger.info(
        f"[VECTOR][traj_compress] compressing: {current_tokens} → {token_budget} tokens "
        f"({len(messages)} messages, model={model})"
    )

    # Stage 1: Prune oversized tool results
    pruned = _prune_tool_results(messages)

    # Stage 2: Group into turns
    turns = _group_into_turns(pruned)

    # Stage 3 + 4: Score and drop
    kept_turns, dropped_turns = _drop_turns_to_budget(turns, token_budget)

    # Stage 5: Re-stitch
    stitched = _stitch_turns(turns, kept_turns)

    # Stage 6: Validate
    validated = _validate_messages(stitched)

    after_tokens = estimate_tokens(validated)
    reduction_pct = 100 * (1 - after_tokens / max(current_tokens, 1))
    logger.info(
        f"[VECTOR][traj_compress] done: {current_tokens} → {after_tokens} tokens "
        f"({reduction_pct:.0f}% reduction, {len(messages)} → {len(validated)} messages, "
        f"{len(dropped_turns)} turns dropped)"
    )

    return validated


# ── TrajectoryCompressor class ────────────────────────────────────────────────

class TrajectoryCompressor:
    """Class wrapper around the compression pipeline with optional LLM summarization.

    Without a summarization model configured, Stage 4 dropped turns are
    replaced by a placeholder string. When a model is configured (via
    CONFIG['model'] or constructor argument), dropped turns are summarized
    by an Ollama call before being replaced.
    """

    def __init__(
        self,
        model: str = "vector-focus",
        target_ratio: float = _DEFAULT_TARGET_RATIO,
        summarize_dropped: bool = False,
        summary_model: Optional[str] = None,
    ) -> None:
        self.model = model
        self.target_ratio = target_ratio
        self.summarize_dropped = summarize_dropped
        self.summary_model: str = (
            summary_model
            or CONFIG.get("model", model)
            or model
        )
        self.compression_count: int = 0

    def needs_compression(self, messages: List[Dict[str, Any]]) -> bool:
        """Return True when the message list exceeds the target token budget."""
        context_window = get_token_budget(self.model)
        budget = int(context_window * self.target_ratio)
        return estimate_tokens(messages) > budget

    def compress(
        self, messages: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Compress the message list and return (compressed_messages, stats_dict).

        stats_dict keys: original_tokens, compressed_tokens, original_count,
        compressed_count, reduction_pct, dropped_turns.
        """
        original_tokens = estimate_tokens(messages)
        original_count = len(messages)

        if not self.needs_compression(messages):
            return messages, {
                "original_tokens": original_tokens,
                "compressed_tokens": original_tokens,
                "original_count": original_count,
                "compressed_count": original_count,
                "reduction_pct": 0.0,
                "dropped_turns": 0,
                "was_compressed": False,
            }

        context_window = get_token_budget(self.model)
        token_budget = int(context_window * self.target_ratio)

        # Stage 1
        pruned = _prune_tool_results(messages)
        # Stage 2
        turns = _group_into_turns(pruned)
        # Stage 3 + 4
        kept_turns, dropped_turns = _drop_turns_to_budget(turns, token_budget)

        # Optional LLM summarization of dropped turns
        if self.summarize_dropped and dropped_turns:
            dropped_messages = [m for t in dropped_turns for m in t.messages]
            summary = self._summarize_dropped(dropped_messages)
            if summary:
                # Insert summary as a user message before the first kept turn
                # that follows the dropped region. Handled by _stitch_turns
                # via the placeholder mechanism — we replace the placeholder text.
                for t in dropped_turns:
                    t.messages = [{"role": "user", "content": summary}]

        # Stage 5
        stitched = _stitch_turns(turns, kept_turns)
        # Stage 6
        validated = _validate_messages(stitched)

        self.compression_count += 1
        compressed_tokens = estimate_tokens(validated)
        reduction_pct = 100 * (1 - compressed_tokens / max(original_tokens, 1))

        stats = {
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "original_count": original_count,
            "compressed_count": len(validated),
            "reduction_pct": round(reduction_pct, 1),
            "dropped_turns": len(dropped_turns),
            "was_compressed": True,
        }
        return validated, stats

    def _summarize_dropped(self, dropped_messages: List[Dict[str, Any]]) -> Optional[str]:
        """Call Ollama to summarize the dropped messages.

        Returns a summary string, or None on failure (caller falls back to
        the omission placeholder).
        """
        try:
            import ollama

            turns_text = []
            for msg in dropped_messages[:20]:  # cap prompt size
                role = msg.get("role", "unknown")
                content = str(msg.get("content") or "")[:500]
                turns_text.append(f"[{role.upper()}] {content}")

            prompt = (
                "Summarize the following conversation turns concisely. "
                "Write only the summary starting with '[CONTEXT SUMMARY]:'.\n\n"
                + "\n\n".join(turns_text)
            )
            resp = ollama.chat(
                model=self.summary_model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 300},
            )
            text = resp["message"]["content"].strip()
            if not text.startswith("[CONTEXT SUMMARY]:"):
                text = "[CONTEXT SUMMARY]: " + text
            return text
        except Exception as exc:
            logger.debug(
                f"[VECTOR][traj_compress] LLM summarization failed: {exc}"
            )
            return None


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    # Helpers
    def _make_msgs(n_pairs: int, content_size: int = 100) -> List[Dict[str, Any]]:
        msgs = [{"role": "system", "content": "You are VECTOR."}]
        for i in range(n_pairs):
            msgs.append({"role": "user", "content": f"user turn {i} " + "x" * content_size})
            msgs.append({"role": "assistant", "content": f"asst turn {i} " + "x" * content_size})
        return msgs

    # Test 1: estimate_trajectory_tokens returns positive int
    msgs = _make_msgs(5)
    tokens = estimate_trajectory_tokens(msgs)
    assert tokens > 0, f"Expected >0 tokens, got {tokens}"

    # Test 2: No compression when under budget
    small = [{"role": "system", "content": "hi"}]
    result = compress_trajectory(small, model="vector-focus")
    assert result == small, "Short message should not be compressed"

    # Test 3: compress_trajectory reduces a large message list
    large = _make_msgs(n_pairs=200, content_size=200)
    original_tokens = estimate_trajectory_tokens(large)
    compressed = compress_trajectory(large, model="vector-focus", target_ratio=0.80)
    compressed_tokens = estimate_trajectory_tokens(compressed)
    assert compressed_tokens < original_tokens, (
        f"Compression should reduce tokens: {original_tokens} -> {compressed_tokens}"
    )

    # Test 4: System message always survives
    assert any(m["role"] == "system" for m in compressed), "system must survive compression"

    # Test 5: No orphaned tool_results
    tool_msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "run something"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "bash", "arguments": "{}"}}],
        },
        {"role": "tool", "content": "output here " * 50, "tool_call_id": "tc1"},
        {"role": "user", "content": "ok"},
        {"role": "assistant", "content": "done"},
    ]
    validated = _validate_messages(tool_msgs)
    tool_call_ids = {
        tc.get("id")
        for m in validated if m.get("role") == "assistant"
        for tc in (m.get("tool_calls") or [])
        if isinstance(tc, dict)
    }
    for m in validated:
        if m.get("role") == "tool":
            cid = m.get("tool_call_id", "")
            assert not cid or cid in tool_call_ids, f"Orphaned tool_result: {cid}"

    # Test 6: _prune_tool_results trims large non-error results
    # Put the big tool result early (index 0) so it is NOT in the tail window
    big_tool_msgs = (
        [{"role": "tool", "content": "x" * 2000, "tool_call_id": "tc2"}]
        + [{"role": "assistant", "content": f"msg {i}"} for i in range(10)]
    )
    pruned = _prune_tool_results(big_tool_msgs, max_chars=500)
    assert len(pruned[0]["content"]) < 2000, "Should have pruned large tool result"

    # Test 7: _prune_tool_results keeps errors intact
    error_tool_msgs = (
        [{"role": "tool", "content": "Error: something went wrong\n" + "x" * 2000, "tool_call_id": "tc3"}]
        + [{"role": "assistant", "content": f"msg {i}"} for i in range(10)]
    )
    pruned_err = _prune_tool_results(error_tool_msgs)
    assert "Error:" in pruned_err[0]["content"], "Error tool results must be preserved"

    # Test 8: TrajectoryCompressor class
    tc = TrajectoryCompressor(model="vector-focus", target_ratio=0.80)
    large2 = _make_msgs(n_pairs=200, content_size=200)
    compressed2, stats = tc.compress(large2)
    assert isinstance(compressed2, list), "compress must return list"
    assert "original_tokens" in stats
    assert "reduction_pct" in stats
    assert stats["was_compressed"] is True

    # Test 9: needs_compression returns False for small messages
    tiny = [{"role": "user", "content": "hi"}]
    assert tc.needs_compression(tiny) is False

    # Test 10: _group_into_turns groups correctly
    # system=1 turn, user=1 turn, assistant+tool=1 turn, user=1 turn → 4 turns
    turns = _group_into_turns([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "x"}]},
        {"role": "tool", "content": "result", "tool_call_id": "x"},
        {"role": "user", "content": "ok"},
    ])
    assert len(turns) == 4, f"Expected 4 turns (sys, user, asst+tool, user), got {len(turns)}"
    assert turns[0].role == "system", f"First turn should be system, got {turns[0].role}"
    assert turns[2].role == "assistant", f"Third turn should be assistant, got {turns[2].role}"
    assert len(turns[2].messages) == 2, f"Assistant turn should have 2 msgs (asst+tool)"

    # Test 11: stitch produces omission placeholders
    all_turns = _group_into_turns(_make_msgs(10))
    kept, dropped = _drop_turns_to_budget(all_turns, token_budget=100)
    stitched = _stitch_turns(all_turns, kept)
    placeholder_found = any(
        "turns omitted" in str(m.get("content", "")) for m in stitched
    )
    if dropped:
        assert placeholder_found, "Dropped turns must produce a placeholder"

    print("OK")
