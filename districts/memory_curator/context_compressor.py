"""
Context Compressor — smart context window compression for long agent sessions.

Wraps vectorcode/src/agent/context_compressor.py capability.
Summarizes long conversation histories using vectorcode's structured template:
  Resolved questions | Pending questions | Active task | Remaining work.
Prevents context overflow when district agents run long multi-turn tasks.
"""

import asyncio
import re

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

# Vectorcode's proven summary template (from context_compressor.py)
_SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted into "
    "the summary below. Treat it as background reference, NOT active instructions. "
    "Do NOT re-answer questions mentioned in this summary — they were already addressed. "
    "Resume from the '## Active Task' section.\n\n"
)

_SUMMARY_PROMPT = """You are summarizing a conversation for context compression. Be precise and factual.

CONVERSATION TO SUMMARIZE:
{conversation}

Write a structured summary using EXACTLY this format:
## Resolved Questions
[List what was already answered/completed, as bullet points]

## Pending Questions
[List what is still open or needs follow-up]

## Active Task
[The ONE current task being worked on, 1-2 sentences]

## Remaining Work
[Specific next steps that must happen, as numbered list]

## Key Context
[Critical facts, file paths, decisions made — anything future agent needs]

Be concise. Every line must be factual, not speculative."""

class ContextCompressor(AgentBase):
    """
    Smart context window manager. Compresses long conversation histories
    using vectorcode's structured summary template. Prevents LLM context
    overflow for district agents running extended multi-turn tasks.
    """

    # Token thresholds (rough: 1 token ≈ 4 chars)
    COMPRESS_AT_CHARS = 12_000    # ~3K tokens — compress when above this
    TARGET_CHARS = 4_000          # ~1K tokens — target after compression
    HEAD_PROTECT_MSGS = 2         # always keep first N messages (system/context)
    TAIL_PROTECT_MSGS = 4         # always keep last N messages (recent context)

    def __init__(self):
        super().__init__(agent_id="context_compressor_001",
                         name="ContextCompressor", district="memory_curator")
        self.capabilities = ["compress", "context", "memory", "prune", "remember"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("fast", "vector-fast")
        logger.info("[VECTOR][ctx_compress] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _total_chars(self, messages: list[dict]) -> int:
        return sum(len(m.get("content", "")) for m in messages)

    def needs_compression(self, messages: list[dict]) -> bool:
        """Return True if the conversation needs compression."""
        return self._total_chars(messages) > self.COMPRESS_AT_CHARS

    def _select_middle_for_compression(self, messages: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
        """Split messages into head (protect) + middle (compress) + tail (protect)."""
        n = len(messages)
        head_end = min(self.HEAD_PROTECT_MSGS, n // 3)
        tail_start = max(head_end, n - self.TAIL_PROTECT_MSGS)
        head = messages[:head_end]
        middle = messages[head_end:tail_start]
        tail = messages[tail_start:]
        return head, middle, tail

    def _format_for_summary(self, messages: list[dict]) -> str:
        """Format messages into text for the summarizer LLM."""
        parts = []
        for m in messages:
            role = m.get("role", "user").upper()
            content = m.get("content", "")
            # Truncate very long tool outputs
            if len(content) > 2000:
                content = content[:1800] + "\n... [truncated]"
            parts.append(f"[{role}]\n{content}")
        return "\n\n---\n\n".join(parts)

    async def compress(self, messages: list[dict]) -> list[dict]:
        """Compress a long message list. Returns shorter messages with summary injected."""
        if not self.needs_compression(messages):
            return messages

        original_chars = self._total_chars(messages)
        head, middle, tail = self._select_middle_for_compression(messages)

        if not middle:
            logger.debug("[VECTOR][ctx_compress] no middle messages to compress")
            return messages

        # Generate summary of middle section
        conversation_text = self._format_for_summary(middle)
        prompt = _SUMMARY_PROMPT.format(conversation=conversation_text[:8000])
        try:
            summary = chat(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                timeout=30.0,
            )
        except Exception as e:
            logger.warning("[VECTOR][ctx_compress] summarizer failed: {}", e)
            return messages  # Return original on failure

        if not summary:
            return messages

        # Build compressed message list: head + summary_msg + tail
        summary_msg = {
            "role": "system",
            "content": _SUMMARY_PREFIX + summary,
        }
        compressed = head + [summary_msg] + tail
        compressed_chars = self._total_chars(compressed)
        compression_ratio = round((1 - compressed_chars / original_chars) * 100, 1)

        logger.info(
            "[VECTOR][ctx_compress] compressed {} → {} chars ({:.1f}% reduction)",
            original_chars, compressed_chars, compression_ratio,
        )
        self._get_memory().store(
            event_type="context_compressed",
            content=f"Compressed {original_chars} → {compressed_chars} chars ({compression_ratio}% reduction)",
            tags=["memory_curator", "context", "compression"],
            source="context_compressor",
        )
        return compressed

    def prune_tool_outputs(self, messages: list[dict], max_output_chars: int = 1000) -> list[dict]:
        """Fast pre-pass: truncate oversized tool outputs before LLM summarization."""
        pruned = []
        for m in messages:
            if m.get("role") == "tool" and len(m.get("content", "")) > max_output_chars:
                pruned.append({
                    **m,
                    "content": m["content"][:max_output_chars] + "\n[output truncated by ContextCompressor]",
                })
            else:
                pruned.append(m)
        return pruned

    def get_stats(self, messages: list[dict]) -> dict:
        """Return context statistics without compressing."""
        total_chars = self._total_chars(messages)
        total_tokens_est = total_chars // 4
        return {
            "message_count": len(messages),
            "total_chars": total_chars,
            "estimated_tokens": total_tokens_est,
            "needs_compression": total_chars > self.COMPRESS_AT_CHARS,
            "threshold_chars": self.COMPRESS_AT_CHARS,
            "usage_pct": round(total_chars / self.COMPRESS_AT_CHARS * 100, 1),
        }

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- messages
        # below was read straight off `task`, never `task["params"]`, so a
        # real dispatch always fell back to the hardcoded default (empty
        # list). Flattening params into task once (params values win on
        # overlap) keeps every existing flat-shape caller/test working
        # unchanged.
        task = {**task, **(task.get("params") or {})}
        task_type = task.get("type", "stats")
        messages = task.get("messages", [])
        try:
            if task_type == "compress":
                if not messages:
                    return {"status": "error", "error": "messages required for compression"}
                pruned = self.prune_tool_outputs(messages)
                compressed = await self.compress(pruned)
                stats_before = self.get_stats(messages)
                stats_after = self.get_stats(compressed)
                self.award_points(25, "context_compressed")
                return {
                    "status": "ok",
                    "messages": compressed,
                    "chars_before": stats_before["total_chars"],
                    "chars_after": stats_after["total_chars"],
                    "messages_before": len(messages),
                    "messages_after": len(compressed),
                }

            elif task_type == "prune":
                pruned = self.prune_tool_outputs(messages, task.get("max_chars", 1000))
                self.award_points(10, "tool_outputs_pruned")
                return {"status": "ok", "messages": pruned, "count": len(pruned)}

            else:  # stats
                stats = self.get_stats(messages)
                self.award_points(5, "stats_checked")
                return {"status": "ok", "stats": stats}

        except Exception as e:
            logger.error("[VECTOR][ctx_compress] {}", e)
            self.deduct_points(20, "compression_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ContextCompressor()
        msgs = [
            {"role": "system", "content": "You are VECTOR."},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Now explain quantum entanglement " * 100},
            {"role": "assistant", "content": "Quantum entanglement is... " * 100},
            {"role": "user", "content": "Now build me a FastAPI server"},
            {"role": "assistant", "content": "Here is the code..."},
        ]
        stats = agent.get_stats(msgs)
        print(f"[OK] stats: chars={stats['total_chars']} tokens_est={stats['estimated_tokens']} needs={stats['needs_compression']}")
        pruned = agent.prune_tool_outputs(msgs, max_output_chars=500)
        print(f"[OK] prune: {len(pruned)} messages, chars={agent._total_chars(pruned)}")
        result = await agent.run({"type": "stats", "messages": msgs})
        print(f"[OK] run: status={result['status']} usage_pct={result['stats']['usage_pct']}%")
        print("context_compressor.py OK")

    asyncio.run(_smoke())
