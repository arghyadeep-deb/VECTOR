"""5-stage context compaction pipeline for VectorCode.

Stage 1: Trim tool results  — truncate large bash outputs (keep first+last N lines)
Stage 2: Summarize closed   — compress resolved sub-tasks into a paragraph
Stage 3: Prioritize recency — keep last N turns verbatim; compress older ones
Stage 4: Embed VECTOR.md    — always keep project config in context
Stage 5: Preserve decisions — important decisions are never compacted away
"""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

from loguru import logger

# ── Stage configuration ───────────────────────────────────────────────────────

_TOOL_OUTPUT_MAX_LINES = 50     # trim bash/tool outputs to this many lines
_TOOL_HEAD_TAIL        = 20     # keep first N + last N lines of long outputs
_KEEP_LAST_TURNS       = 8      # always keep the last N conversation turns verbatim
_COMPRESS_THRESHOLD    = 8_000  # chars: trigger compaction above this
_DECISION_MARKERS      = [      # phrases that mark a decision to preserve
    "decision:", "decided:", "we will", "final approach:", "using:", "chosen:",
    "architecture:", "going with", "DECISION:", "✓", "approved:",
]


def _char_count(messages: list[dict]) -> int:
    return sum(len(m.get("content") or "") for m in messages)


# ── Stage 1: Trim tool results ────────────────────────────────────────────────

def _trim_tool_results(messages: list[dict]) -> list[dict]:
    result = []
    for msg in messages:
        content = msg.get("content") or ""
        role = msg.get("role", "")
        if role == "tool" and content.count("\n") > _TOOL_OUTPUT_MAX_LINES:
            lines = content.splitlines()
            head = lines[:_TOOL_HEAD_TAIL]
            tail = lines[-_TOOL_HEAD_TAIL:]
            omitted = len(lines) - 2 * _TOOL_HEAD_TAIL
            trimmed = "\n".join(head) + f"\n... [{omitted} lines omitted] ...\n" + "\n".join(tail)
            result.append({**msg, "content": trimmed})
            logger.debug(f"[VECTOR][compact] trimmed tool result: {len(lines)} → {_TOOL_HEAD_TAIL*2} lines")
        else:
            result.append(msg)
    return result


# ── Stage 2: Summarize closed topics ─────────────────────────────────────────

def _is_closed_topic(msg: dict) -> bool:
    content = (msg.get("content") or "").lower()
    closed_markers = ["done.", "complete.", "fixed.", "resolved.", "✓", "passed", "committed"]
    return any(m in content for m in closed_markers)


def _summarize_closed(messages: list[dict], model: str) -> list[dict]:
    sys_msgs  = [m for m in messages if m["role"] == "system"]
    chat_msgs = [m for m in messages if m["role"] != "system"]
    tail      = chat_msgs[-_KEEP_LAST_TURNS:]
    middle    = chat_msgs[:-_KEEP_LAST_TURNS]

    if not middle:
        return messages

    # Identify closed segments (assistant messages that declare completion)
    closed_indices = [i for i, m in enumerate(middle)
                      if m["role"] == "assistant" and _is_closed_topic(m)]
    if not closed_indices:
        return messages

    # Build a summary of the closed portion
    closed_text = "\n".join(
        f"[{m['role'].upper()}] {(m.get('content') or '')[:200]}"
        for m in middle
        if middle.index(m) <= max(closed_indices)
    )
    summary = f"<resolved>\n{closed_text[:1000]}\n</resolved>"

    open_middle = [m for i, m in enumerate(middle) if i > max(closed_indices)]
    compressed = sys_msgs + [{"role": "assistant", "content": summary}] + open_middle + tail
    logger.debug(f"[VECTOR][compact] stage2: compressed {len(middle)} middle turns")
    return compressed


# ── Stage 3: Prioritize recency ───────────────────────────────────────────────

def _prioritize_recency(messages: list[dict], model: str) -> list[dict]:
    sys_msgs  = [m for m in messages if m["role"] == "system"]
    chat_msgs = [m for m in messages if m["role"] != "system"]

    if len(chat_msgs) <= _KEEP_LAST_TURNS:
        return messages

    tail   = chat_msgs[-_KEEP_LAST_TURNS:]
    older  = chat_msgs[:-_KEEP_LAST_TURNS]

    # Compress older portion via local model if available
    old_text = "\n".join(
        f"[{m['role'].upper()}] {(m.get('content') or '')[:300]}"
        for m in older
    )
    summary_content = f"<context-summary>\n{old_text[:1500]}\n</context-summary>"

    try:
        import ollama
        prompt = (
            "Summarize this conversation history in 3 sections:\n"
            "## Active Task\n## Resolved\n## Pending\n\n"
            f"{old_text[:2000]}"
        )
        resp = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        summary_content = f"<context-summary>\n{resp['message']['content']}\n</context-summary>"
    except Exception:
        pass

    compressed = sys_msgs + [{"role": "assistant", "content": summary_content}] + tail
    logger.debug(f"[VECTOR][compact] stage3: {len(older)} older turns → 1 summary")
    return compressed


# ── Stage 4: Embed VECTOR.md ──────────────────────────────────────────────────

def _embed_vectormd(messages: list[dict], project_dir: Path | None) -> list[dict]:
    if not project_dir:
        return messages
    try:
        from agents.districts.coding.vectorcode.context.vectormd import VectorMD
        vmd = VectorMD(project_dir)
        return vmd.inject_into_messages(messages)
    except Exception as e:
        logger.debug(f"[VECTOR][compact] stage4 vectormd inject failed: {e}")
        return messages


# ── Stage 5: Preserve decisions ───────────────────────────────────────────────

def _extract_decisions(messages: list[dict]) -> list[str]:
    decisions = []
    for msg in messages:
        content = msg.get("content") or ""
        for line in content.splitlines():
            if any(marker.lower() in line.lower() for marker in _DECISION_MARKERS):
                decisions.append(line.strip())
    return decisions[:10]


def _preserve_decisions(messages: list[dict], decisions: list[str]) -> list[dict]:
    if not decisions:
        return messages
    decision_block = "<decisions>\n" + "\n".join(f"• {d}" for d in decisions) + "\n</decisions>"
    result = list(messages)
    for i, msg in enumerate(result):
        if msg["role"] == "system":
            if "<decisions>" not in msg["content"]:
                result[i] = {**msg, "content": msg["content"] + "\n\n" + decision_block}
            return result
    result.insert(0, {"role": "system", "content": decision_block})
    return result


# ── Public API ────────────────────────────────────────────────────────────────

class ContextCompactor:
    """
    Runs the 5-stage compaction pipeline on a message list.
    Call when context usage exceeds the configured threshold.
    """

    def __init__(self, model: str = "vector-focus", project_dir: Path | None = None) -> None:
        self.model = model
        self.project_dir = project_dir

    def needs_compaction(self, messages: list[dict], threshold_chars: int = _COMPRESS_THRESHOLD) -> bool:
        return _char_count(messages) > threshold_chars

    def compact(self, messages: list[dict]) -> list[dict]:
        """Run all 5 stages. Returns compacted message list."""
        before = _char_count(messages)

        # Collect decisions before compacting (stage 5 uses them)
        decisions = _extract_decisions(messages)

        # Stage 1
        messages = _trim_tool_results(messages)
        # Stage 2
        messages = _summarize_closed(messages, self.model)
        # Stage 3
        messages = _prioritize_recency(messages, self.model)
        # Stage 4
        messages = _embed_vectormd(messages, self.project_dir)
        # Stage 5
        messages = _preserve_decisions(messages, decisions)

        after = _char_count(messages)
        logger.info(f"[VECTOR][compact] {before} → {after} chars ({100*(1-after/max(before,1)):.0f}% reduction)")
        return messages


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    msgs = [
        {"role": "system", "content": "You are VECTOR."},
        {"role": "user",   "content": "run the tests"},
        {"role": "tool",   "content": "\n".join(f"line {i}" for i in range(200))},
        {"role": "assistant", "content": "All tests passed. done."},
        {"role": "user",   "content": "now fix the bug"},
        {"role": "assistant", "content": "Decision: use the factory pattern"},
        {"role": "user",   "content": "looks good"},
    ]
    compactor = ContextCompactor(model="vector-focus")
    result = compactor.compact(msgs)
    assert any(m["role"] == "system" for m in result)
    # Stage 1: tool output should be trimmed
    tool_msgs = [m for m in result if m.get("role") == "tool"]
    for tm in tool_msgs:
        assert tm["content"].count("\n") <= _TOOL_HEAD_TAIL * 2 + 5
    print(f"compactor.py OK — {len(msgs)} → {len(result)} messages")
