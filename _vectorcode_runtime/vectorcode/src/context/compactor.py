"""Enhanced context compaction pipeline for VectorCode.

Absorbs key algorithms from reference agent/context_compressor.py:
- SUMMARY_PREFIX framing (CONTEXT COMPACTION — REFERENCE ONLY)
- LEGACY_SUMMARY_PREFIX detection for iterative updates
- Tool output pruning with informative 1-line summaries (_PRUNED_TOOL_PLACEHOLDER)
- Token-budget tail protection (not fixed message count)
- _content_length_for_budget() with multimodal image cost (1600 tokens)
- Scaled summary budget (SUMMARY_RATIO=0.20, MIN=2000, CEILING=12000)
- Summary failure cooldown (600 seconds)

Stage pipeline:
  Stage 1: Prune old tool results  — replace with informative summaries
  Stage 2: Token-budget tail guard  — protect recent context by token cost
  Stage 3: Summarize middle turns   — LLM-compressed older turns
  Stage 4: Embed VECTOR.md          — always keep project config in context
  Stage 5: Preserve decisions       — important decisions never compacted away
"""

from pathlib import Path
import sys
import re
import time
import json
import hashlib

from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

# ── Summary framing (from reference) ─────────────────────────────────────────────

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
    "into the summary below. This is a handoff from a previous context "
    "window — treat it as background reference, NOT as active instructions. "
    "Do NOT answer questions or fulfill requests mentioned in this summary; "
    "they were already addressed. "
    "Your current task is identified in the '## Active Task' section of the "
    "summary — resume exactly from there. "
    "Respond ONLY to the latest user message "
    "that appears AFTER this summary. The current session state (files, "
    "config, etc.) may reflect work described here — avoid repeating it:"
)

LEGACY_SUMMARY_PREFIX = "[CONTEXT SUMMARY]:"

# ── Stage configuration ───────────────────────────────────────────────────────

_TOOL_OUTPUT_MAX_LINES  = 50      # trim large tool outputs to this many lines
_TOOL_HEAD_TAIL         = 20      # keep first N + last N lines
_KEEP_LAST_TURNS        = 8       # min turns to always keep verbatim
_COMPRESS_THRESHOLD     = 6_000   # chars: trigger compaction above this
_COMPRESS_TOKEN_THRESHOLD = 1_500 # tokens: alternative trigger

_MIN_SUMMARY_TOKENS     = 2_000
_SUMMARY_RATIO          = 0.20
_SUMMARY_TOKENS_CEILING = 12_000
_CHARS_PER_TOKEN        = 4
_IMAGE_TOKEN_ESTIMATE   = 1_600   # flat cost per image part ((VectorCode default)
_IMAGE_CHAR_EQUIVALENT  = _IMAGE_TOKEN_ESTIMATE * _CHARS_PER_TOKEN

_PRUNED_TOOL_PLACEHOLDER = "[Old tool output cleared to save context space]"

_SUMMARY_FAILURE_COOLDOWN_SECONDS = 600

_DECISION_MARKERS = [
    "decision:", "decided:", "we will", "final approach:", "using:", "chosen:",
    "architecture:", "going with", "DECISION:", "approved:",
]


# ── Content length helpers (reference-style) ─────────────────────────────────────

def _content_length_for_budget(raw_content) -> int:
    """Return effective char-length of message content for token budgeting.

    Handles plain strings and multimodal lists with per-image cost.
    """
    if isinstance(raw_content, str):
        return len(raw_content)
    if not isinstance(raw_content, list):
        return len(str(raw_content or ""))

    total = 0
    for part in raw_content:
        if isinstance(part, str):
            total += len(part)
            continue
        if not isinstance(part, dict):
            total += len(str(part))
            continue
        ptype = part.get("type")
        if ptype in {"image_url", "input_image", "image"}:
            total += _IMAGE_CHAR_EQUIVALENT
        else:
            total += len(part.get("text", "") or "")
    return total


def _content_text(content) -> str:
    """Return best-effort text representation of message content."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(p for p in parts if p)
    return str(content)


def _char_count(messages: list[dict]) -> int:
    """Total char-budget size of all messages."""
    return sum(_content_length_for_budget(m.get("content")) for m in messages)


def _rough_tokens(messages: list[dict]) -> int:
    """Rough token estimate (char / 4)."""
    return _char_count(messages) // _CHARS_PER_TOKEN


# ── Tool result summarizer ────────────────────────────────────────────────────

def _summarize_tool_result(tool_name: str, tool_args: str, tool_content: str) -> str:
    """Create a 1-line informative summary of a tool call + result."""
    try:
        args = json.loads(tool_args) if tool_args else {}
    except (json.JSONDecodeError, TypeError):
        args = {}

    content = tool_content or ""
    content_len = len(content)
    line_count = content.count("\n") + 1 if content.strip() else 0

    if tool_name in ("bash", "terminal"):
        cmd = args.get("command", "")
        if len(cmd) > 80:
            cmd = cmd[:77] + "..."
        return f"[{tool_name}] ran `{cmd}` -> {line_count} lines output"

    if tool_name in ("read_file", "Read"):
        path = args.get("path", args.get("file_path", "?"))
        offset = args.get("offset", 1)
        return f"[{tool_name}] read {path} from line {offset} ({content_len:,} chars)"

    if tool_name in ("write_file", "Write"):
        path = args.get("path", args.get("file_path", "?"))
        written_lines = args.get("content", "").count("\n") + 1 if args.get("content") else "?"
        return f"[{tool_name}] wrote to {path} ({written_lines} lines)"

    if tool_name in ("search_files", "Grep"):
        pattern = args.get("pattern", "?")
        path = args.get("path", ".")
        return f"[{tool_name}] search for '{pattern}' in {path} ({content_len:,} chars result)"

    if tool_name in ("web_search", "search"):
        query = args.get("query", "?")
        return f"[{tool_name}] query='{query}' ({content_len:,} chars result)"

    # Generic fallback
    first_args = ""
    for k, v in list(args.items())[:2]:
        sv = str(v)[:40]
        first_args += f" {k}={sv}"
    return f"[{tool_name}]{first_args} ({content_len:,} chars result)"


# ── Stage 1: Prune old tool results ──────────────────────────────────────────

def _prune_old_tool_results(
    messages: list[dict],
    protect_tail_tokens: int,
    protect_tail_count: int = _KEEP_LAST_TURNS,
) -> tuple[list[dict], int]:
    """Replace old tool result contents with informative 1-line summaries.

    Walks backward from end, protecting messages within protect_tail_tokens budget.
    Also deduplicates identical tool results (keeps only newest copy).
    """
    if not messages:
        return messages, 0

    result = [m.copy() for m in messages]
    pruned = 0

    # Build index: tool_call_id -> (tool_name, arguments)
    call_id_to_tool: dict[str, tuple] = {}
    for msg in result:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    cid = tc.get("id", "")
                    fn = tc.get("function", {})
                    call_id_to_tool[cid] = (fn.get("name", "unknown"), fn.get("arguments", ""))

    # Determine prune boundary using token budget
    accumulated = 0
    boundary = len(result)
    min_protect = min(protect_tail_count, len(result) - 1)
    for i in range(len(result) - 1, -1, -1):
        msg = result[i]
        raw_content = msg.get("content") or ""
        content_len = _content_length_for_budget(raw_content)
        msg_tokens = content_len // _CHARS_PER_TOKEN + 10
        for tc in msg.get("tool_calls") or []:
            if isinstance(tc, dict):
                args = tc.get("function", {}).get("arguments", "")
                msg_tokens += len(args) // _CHARS_PER_TOKEN
        if accumulated + msg_tokens > protect_tail_tokens and (len(result) - i) >= min_protect:
            boundary = i
            break
        accumulated += msg_tokens
        boundary = i
    prune_boundary = max(boundary, len(result) - min_protect)

    # Pass 1: Deduplicate identical tool results
    content_hashes: dict[str, tuple] = {}
    for i in range(len(result) - 1, -1, -1):
        msg = result[i]
        if msg.get("role") != "tool":
            continue
        content = msg.get("content") or ""
        if isinstance(content, list) or len(content) < 200:
            continue
        h = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()[:12]
        if h in content_hashes:
            result[i] = {**msg, "content": "[Duplicate tool output — same content as a more recent call]"}
            pruned += 1
        else:
            content_hashes[h] = (i, msg.get("tool_call_id", "?"))

    # Pass 2: Replace old tool results with informative summaries
    for i in range(prune_boundary):
        msg = result[i]
        if msg.get("role") != "tool":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            continue
        if not content or content == _PRUNED_TOOL_PLACEHOLDER:
            continue
        if content.startswith("[Duplicate tool output"):
            continue
        if len(content) > 200:
            call_id = msg.get("tool_call_id", "")
            tool_name, tool_args = call_id_to_tool.get(call_id, ("unknown", ""))
            summary = _summarize_tool_result(tool_name, tool_args, content)
            result[i] = {**msg, "content": summary}
            pruned += 1

    return result, pruned


# ── Stage 2: Summarize closed topics ─────────────────────────────────────────

def _is_closed_topic(msg: dict) -> bool:
    content = _content_text(msg.get("content") or "").lower()
    closed_markers = ["done.", "complete.", "fixed.", "resolved.", "passed", "committed"]
    return any(m in content for m in closed_markers)


def _split_tool_safe_tail(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep complete assistant-call/result groups across summary boundaries."""
    owners = {
        call.get("id"): index for index, message in enumerate(messages)
        for call in message.get("tool_calls", []) if call.get("id")
    }
    boundary = max(0, len(messages) - _KEEP_LAST_TURNS)
    while True:
        previous = boundary
        for message in messages[boundary:]:
            if message.get("role") == "tool":
                owner = owners.get(message.get("tool_call_id"))
                if owner is None:
                    return [], messages
                boundary = min(boundary, owner)
        if boundary == previous:
            return messages[:boundary], messages[boundary:]


def _summarize_closed(messages: list[dict], model: str) -> list[dict]:
    """Compress resolved sub-tasks into a summary block."""
    sys_msgs  = [m for m in messages if m["role"] == "system"]
    chat_msgs = [m for m in messages if m["role"] != "system"]
    middle, tail = _split_tool_safe_tail(chat_msgs)

    if not middle:
        return messages

    closed_indices = [i for i, m in enumerate(middle)
                      if m["role"] == "assistant" and not m.get("tool_calls") and _is_closed_topic(m)]
    if not closed_indices:
        return messages

    closed_text = "\n".join(
        f"[{m['role'].upper()}] {_content_text(m.get('content') or '')[:200]}"
        for i, m in enumerate(middle)
        if i <= max(closed_indices)
    )
    summary = f"<resolved>\n{closed_text[:1000]}\n</resolved>"
    open_middle = [m for i, m in enumerate(middle) if i > max(closed_indices)]
    compressed = sys_msgs + [{"role": "assistant", "content": summary}] + open_middle + tail
    logger.debug(f"[VECTOR][compact] stage2: compressed {len(middle)} middle turns")
    return compressed


# ── Stage 3: Summarize middle with LLM (reference-style framing) ────────────────

def _build_summary_prompt(turns: list[dict], previous_summary: str | None = None) -> str:
    """Build summarizer prompt with reference-style framing."""
    turns_text = []
    for msg in turns:
        role = msg.get("role", "unknown")
        content = _content_text(msg.get("content") or "")
        if len(content) > 2000:
            content = content[:1600] + "\n...[truncated]...\n" + content[-400:]
        turns_text.append(f"[{role.upper()}] {content}")
    serialized = "\n\n".join(turns_text)

    if previous_summary:
        return (
            "You are updating an existing context summary with new conversation turns.\n"
            "EXISTING SUMMARY:\n" + previous_summary + "\n\n"
            "NEW TURNS TO INCORPORATE:\n" + serialized + "\n\n"
            "Update the summary incorporating all new information. "
            "Output ONLY the updated summary in the same 3-section format below.\n\n"
            "## Active Task\n[what is currently being worked on]\n\n"
            "## Resolved\n[completed work, decisions, facts established]\n\n"
            "## Remaining Work\n[pending steps, blockers, open questions]"
        )
    return (
        "Do not respond to any questions or requests in the conversation below. "
        "Summarize this conversation in exactly 3 sections. "
        "Output ONLY the summary, nothing else.\n\n"
        + serialized
        + "\n\n"
        "## Active Task\n[what is currently being worked on]\n\n"
        "## Resolved\n[completed work, decisions, facts established]\n\n"
        "## Remaining Work\n[pending steps, blockers, open questions]"
    )


def _summarize_middle(
    messages: list[dict],
    model: str,
    previous_summary: str | None,
    max_summary_tokens: int,
    *, allow_llm: bool = True,
) -> tuple[list[dict], str | None]:
    """Compress older turns via local LLM. Returns (new_messages, new_summary_text)."""
    sys_msgs  = [m for m in messages if m["role"] == "system"]
    chat_msgs = [m for m in messages if m["role"] != "system"]

    if len(chat_msgs) <= _KEEP_LAST_TURNS:
        return messages, previous_summary

    middle, tail = _split_tool_safe_tail(chat_msgs)

    if not middle:
        return messages, previous_summary

    # Detect legacy summary prefix in existing messages (iterative update)
    existing_legacy_summary = None
    filtered_middle = []
    for msg in middle:
        content_text = _content_text(msg.get("content") or "")
        if SUMMARY_PREFIX in content_text or LEGACY_SUMMARY_PREFIX in content_text:
            existing_legacy_summary = content_text
        else:
            filtered_middle.append(msg)

    turns_to_summarize = filtered_middle if filtered_middle else middle
    prompt = _build_summary_prompt(
        turns_to_summarize,
        previous_summary or existing_legacy_summary,
    )

    summary_text = None
    try:
        if allow_llm:
            import ollama
            resp = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": max_summary_tokens},
            )
            summary_text = resp["message"]["content"]
    except Exception as e:
        logger.warning(f"[VECTOR][compact] LLM summary failed: {e} — using static fallback")

    if not summary_text:
        # Static fallback: plain text summary
        lines = [f"[{m['role'].upper()}] {_content_text(m.get('content') or '')[:150]}"
                 for m in turns_to_summarize]
        summary_text = "## Active Task\n(see below)\n\n## Resolved\n" + "\n".join(lines[:10])

    summary_block = f"{SUMMARY_PREFIX}\n\n{summary_text}"
    compressed = sys_msgs + [{"role": "assistant", "content": summary_block}] + tail
    logger.debug(f"[VECTOR][compact] stage3: {len(middle)} middle turns → 1 summary block")
    return compressed, summary_text


# ── Stage 4: Embed VECTOR.md ──────────────────────────────────────────────────

def _embed_vectormd(messages: list[dict], project_dir: Path | None) -> list[dict]:
    """Inject VECTOR.md content into system message."""
    if not project_dir:
        return messages
    try:
        from vectorcode.src.context.vectormd import VectorMD
        vmd = VectorMD(project_dir)
        return vmd.inject_into_messages(messages)
    except Exception as e:
        logger.debug(f"[VECTOR][compact] stage4 vectormd inject failed: {e}")
        return messages


# ── Stage 5: Preserve decisions ───────────────────────────────────────────────

def _extract_decisions(messages: list[dict]) -> list[str]:
    """Extract lines that look like decisions from all messages."""
    decisions = []
    for msg in messages:
        content = _content_text(msg.get("content") or "")
        for line in content.splitlines():
            if any(marker.lower() in line.lower() for marker in _DECISION_MARKERS):
                decisions.append(line.strip())
    return decisions[:10]


def _preserve_decisions(messages: list[dict], decisions: list[str]) -> list[dict]:
    """Inject decision block into system message so decisions survive compaction."""
    if not decisions:
        return messages
    decision_block = "<decisions>\n" + "\n".join(f"* {d}" for d in decisions) + "\n</decisions>"
    result = list(messages)
    for i, msg in enumerate(result):
        if msg["role"] == "system":
            content_text = _content_text(msg.get("content") or "")
            if "<decisions>" not in content_text:
                existing = msg["content"] or ""
                result[i] = {**msg, "content": existing + "\n\n" + decision_block}
            return result
    result.insert(0, {"role": "system", "content": decision_block})
    return result


# ── Public API ────────────────────────────────────────────────────────────────

class ContextCompactor:
    """VectorCode context compaction pipeline.

    Runs tool-pruning + LLM summarization + VECTOR.md injection + decision preservation.
    Call when context usage exceeds the configured threshold.
    """

    def __init__(
        self,
        model: str = "vector-focus",
        project_dir: Path | None = None,
        threshold_chars: int = _COMPRESS_THRESHOLD,
        summary_target_ratio: float = _SUMMARY_RATIO,
    ) -> None:
        self.model = model
        self.project_dir = project_dir
        self.threshold_chars = threshold_chars
        self.summary_target_ratio = max(0.10, min(summary_target_ratio, 0.80))
        self._previous_summary: str | None = None
        self._last_summary_failure_time: float = 0.0
        self.compression_count: int = 0

    def _max_summary_tokens(self, context_chars: int) -> int:
        content_tokens = context_chars // _CHARS_PER_TOKEN
        budget = int(content_tokens * _SUMMARY_RATIO)
        return max(_MIN_SUMMARY_TOKENS, min(budget, _SUMMARY_TOKENS_CEILING))

    def needs_compaction(self, messages: list[dict]) -> bool:
        """Return True when context exceeds the threshold."""
        return _char_count(messages) > self.threshold_chars

    def compact(self, messages: list[dict], *, allow_llm: bool = True) -> list[dict]:
        """Run full compaction pipeline. Returns compacted message list."""
        before = _char_count(messages)
        logger.info(f"[VECTOR][compact] starting compaction: {before} chars, "
                    f"{len(messages)} messages, model={self.model}")

        # Check cooldown on summary failures
        cooldown_active = (
            self._last_summary_failure_time > 0
            and (time.time() - self._last_summary_failure_time) < _SUMMARY_FAILURE_COOLDOWN_SECONDS
        )

        # Stage 5 prep: extract decisions before we lose them
        decisions = _extract_decisions(messages)

        # Stage 1: Prune old tool results
        tail_token_budget = int((before // _CHARS_PER_TOKEN) * self.summary_target_ratio)
        messages, pruned_count = _prune_old_tool_results(
            messages,
            protect_tail_tokens=tail_token_budget,
            protect_tail_count=_KEEP_LAST_TURNS,
        )
        if pruned_count:
            logger.debug(f"[VECTOR][compact] stage1: pruned {pruned_count} tool outputs")

        # Stage 2: Summarize closed topics
        messages = _summarize_closed(messages, self.model)

        # Stage 3: LLM summarization of middle turns (skip if in cooldown)
        if not cooldown_active and _char_count(messages) > self.threshold_chars:
            max_summary_tokens = self._max_summary_tokens(_char_count(messages))
            try:
                messages, new_summary = _summarize_middle(
                    messages, self.model, self._previous_summary, max_summary_tokens, allow_llm=allow_llm
                )
                self._previous_summary = new_summary
            except Exception as e:
                logger.warning(f"[VECTOR][compact] stage3 failed: {e}")
                self._last_summary_failure_time = time.time()

        # Stage 4: Embed VECTOR.md
        messages = _embed_vectormd(messages, self.project_dir)

        # Stage 5: Preserve decisions
        messages = _preserve_decisions(messages, decisions)

        self.compression_count += 1
        after = _char_count(messages)
        reduction = 100 * (1 - after / max(before, 1))
        logger.info(f"[VECTOR][compact] done: {before} -> {after} chars "
                    f"({reduction:.0f}% reduction, pass #{self.compression_count})")
        return messages


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    msgs = [
        {"role": "system", "content": "You are VECTOR."},
        {"role": "user",   "content": "run the tests"},
        {"role": "tool",   "content": "\n".join(f"line {i}" for i in range(200)),
         "tool_call_id": "tc1"},
        {"role": "assistant", "content": "All tests passed. done."},
        {"role": "user",   "content": "now fix the bug"},
        {"role": "assistant", "content": "Decision: use the factory pattern"},
        {"role": "user",   "content": "looks good"},
    ]
    compactor = ContextCompactor(model="vector-focus")

    # Test needs_compaction
    assert compactor.needs_compaction(msgs) == (_char_count(msgs) > compactor.threshold_chars)

    # Test compact runs without error
    result = compactor.compact(msgs)
    assert any(m["role"] == "system" for m in result), "system message must survive"

    # Test SUMMARY_PREFIX exported
    assert SUMMARY_PREFIX.startswith("[CONTEXT COMPACTION")

    # Test _content_length_for_budget with image
    multimodal = [{"type": "image_url", "url": "..."}, {"type": "text", "text": "hello"}]
    assert _content_length_for_budget(multimodal) == _IMAGE_CHAR_EQUIVALENT + len("hello")

    print(f"compactor.py OK — {len(msgs)} -> {len(result)} messages")


