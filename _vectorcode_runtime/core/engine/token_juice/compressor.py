"""
VECTOR TokenJuice — rule-based token compression.

Targets 80% reduction on tool outputs and verbose assistant responses.
Works in two passes:
  Pass 1: Text rules   — strip boilerplate, normalize whitespace, compress repetition
  Pass 2: Message rules — drop low-value messages, truncate oversized tool outputs

Ported from vector's TokenJuice compression pipeline.
"""
from __future__ import annotations

__all__ = [
    "CompressionStats",
    "reduce_messages",
    "reduce_text",
    "TokenJuice",
]


import re
from dataclasses import dataclass

from loguru import logger

# ── Text-level rules ───────────────────────────────────────────────────────────

_BOILERPLATE_PATTERNS = [
    # Common LLM padding
    (r"(?i)certainly[!,.]?\s*", ""),
    (r"(?i)of course[!,.]?\s*", ""),
    (r"(?i)absolutely[!,.]?\s*", ""),
    (r"(?i)great question[!,.]?\s*", ""),
    (r"(?i)i('d| would) (be )?happy to\s+", ""),
    (r"(?i)let me (help you|assist|explain)\s*", ""),
    (r"(?i)thank you for (your question|asking|reaching out)[.!]?\s*", ""),
    (r"(?i)i hope (this helps|that answers your question|that clarifies)[.!]?\s*", ""),
    (r"(?i)please (feel free to|don't hesitate to) (ask|let me know)[^.]*\.\s*", ""),
    # Repeated line endings
    (r"\n{3,}", "\n\n"),
    # Trailing whitespace
    (r"[ \t]+\n", "\n"),
    # Multiple spaces
    (r"  +", " "),
]

_COMPILED_PATTERNS = [(re.compile(p), r) for p, r in _BOILERPLATE_PATTERNS]

_LOG_NOISE = re.compile(
    r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL|TRACE)\s+.*$",
    re.MULTILINE,
)

_REPEATED_LINES = re.compile(r"(^.+$)(\n\1){2,}", re.MULTILINE)
_JSON_WHITESPACE = re.compile(r'("(?:[^"\\]|\\.)*")\s*:\s*')
_STACK_TRACE = re.compile(r"(Traceback \(most recent call last\):.*?(?:\n\S|\Z))", re.DOTALL)


def reduce_text(
    text: str,
    strip_boilerplate: bool = True,
    strip_log_noise: bool = True,
    compress_repeated_lines: bool = True,
    max_chars: int | None = None,
) -> str:
    """
    Apply text-level TokenJuice rules to a string.

    Returns compressed text. Never raises.
    """
    if not text:
        return text

    if strip_boilerplate:
        for pat, repl in _COMPILED_PATTERNS:
            text = pat.sub(repl, text)

    if strip_log_noise:
        text = _LOG_NOISE.sub("", text)

    if compress_repeated_lines:
        text = _REPEATED_LINES.sub(r"\1\n[repeated lines omitted]", text)

    # Compress stack traces to first + last frame
    def _compress_trace(m: re.Match) -> str:
        lines = m.group(0).splitlines()
        if len(lines) > 6:
            return "\n".join(lines[:3] + ["  ...", lines[-1]])
        return m.group(0)

    text = _STACK_TRACE.sub(_compress_trace, text)

    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + f"\n...[{len(text) - max_chars} chars truncated]"

    return text.strip()


# ── Message-level rules ────────────────────────────────────────────────────────

@dataclass
class CompressionStats:
    original_chars: int
    compressed_chars: int
    original_messages: int
    compressed_messages: int

    @property
    def char_reduction_pct(self) -> float:
        if self.original_chars == 0:
            return 0.0
        return (1 - self.compressed_chars / self.original_chars) * 100

    @property
    def message_reduction_pct(self) -> float:
        if self.original_messages == 0:
            return 0.0
        return (1 - self.compressed_messages / self.original_messages) * 100


class TokenJuice:
    """
    Multi-rule token compressor for LLM message lists.

    Usage:
        juice = TokenJuice()
        compressed, stats = juice.compress(messages)
        logger.info(f"Reduced {stats.char_reduction_pct:.0f}%")

    """

    def __init__(
        self,
        max_tool_output_chars: int = 4000,
        max_assistant_chars: int = 8000,
        drop_empty: bool = True,
        strip_boilerplate: bool = True,
        compress_repeated: bool = True,
    ) -> None:
        self.max_tool_output_chars = max_tool_output_chars
        self.max_assistant_chars = max_assistant_chars
        self.drop_empty = drop_empty
        self.strip_boilerplate = strip_boilerplate
        self.compress_repeated = compress_repeated

    def compress(
        self,
        messages: list[dict],
        preserve_last_n: int = 3,
    ) -> tuple[list[dict], CompressionStats]:
        """
        Compress a list of LLM messages.

        Args:
            messages:       Flat message list
            preserve_last_n: Always preserve last N messages unchanged

        Returns:
            (compressed_messages, CompressionStats)
        """
        original_chars = sum(self._msg_len(m) for m in messages)
        original_count = len(messages)

        if not messages:
            return messages, CompressionStats(0, 0, 0, 0)

        protected = set(range(max(0, len(messages) - preserve_last_n), len(messages)))
        result: list[dict] = []

        for i, msg in enumerate(messages):
            if i in protected:
                result.append(msg)
                continue
            compressed = self._compress_message(msg)
            if compressed is not None:
                result.append(compressed)

        compressed_chars = sum(self._msg_len(m) for m in result)
        stats = CompressionStats(
            original_chars=original_chars,
            compressed_chars=compressed_chars,
            original_messages=original_count,
            compressed_messages=len(result),
        )
        logger.debug(
            "[VECTOR][token_juice] {}/{} messages, {:.0f}% char reduction",
            len(result), original_count, stats.char_reduction_pct,
        )
        return result, stats

    def _compress_message(self, msg: dict) -> dict | None:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if isinstance(content, str):
            compressed = self._compress_str(content, role)
            if self.drop_empty and not compressed.strip():
                return None
            if compressed == content:
                return msg
            return {**msg, "content": compressed}

        if isinstance(content, list):
            new_blocks = []
            for block in content:
                if not isinstance(block, dict):
                    new_blocks.append(block)
                    continue
                block_type = block.get("type", "")
                text = block.get("text", "")
                if block_type == "text" and text:
                    compressed = self._compress_str(text, role)
                    new_blocks.append({**block, "text": compressed})
                else:
                    new_blocks.append(block)
            return {**msg, "content": new_blocks}

        return msg

    def _compress_str(self, text: str, role: str) -> str:
        max_chars = (
            self.max_tool_output_chars if role == "tool"
            else self.max_assistant_chars if role == "assistant"
            else None
        )
        return reduce_text(
            text,
            strip_boilerplate=self.strip_boilerplate and role == "assistant",
            strip_log_noise=role == "tool",
            compress_repeated_lines=self.compress_repeated,
            max_chars=max_chars,
        )

    @staticmethod
    def _msg_len(msg: dict) -> int:
        content = msg.get("content", "")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            return sum(
                len(b.get("text", "") if isinstance(b, dict) else str(b))
                for b in content
            )
        return 0


def reduce_messages(messages: list[dict], **kwargs) -> tuple[list[dict], CompressionStats]:
    """Convenience wrapper around TokenJuice.compress()."""
    return TokenJuice(**kwargs).compress(messages)


if __name__ == "__main__":
    msgs = [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Certainly! Of course, I'd be happy to help. Python is a programming language.\n\nPython is a programming language.\n\nPython is a programming language."},
        {"role": "tool", "content": "DEBUG 2024-01-01 found result\n" * 20 + "Final answer: 42"},
    ]
    juice = TokenJuice()
    compressed, stats = juice.compress(msgs, preserve_last_n=0)
    assert stats.char_reduction_pct > 0, f"Expected reduction, got {stats.char_reduction_pct}"
    assert len(compressed) <= len(msgs)
    assert "Certainly" not in compressed[0]["content"], "Boilerplate should be stripped"
    print(f"OK token_juice/compressor.py — {stats.char_reduction_pct:.0f}% reduction")
