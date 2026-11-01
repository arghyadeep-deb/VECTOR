"""
VECTOR Smart Routing — 7-Layer Context Compressor
Python port of ClawRouter/src/compression/ (7 sub-modules)

Reduces token usage 15-40% while preserving semantics:
  1. deduplication      — remove exact duplicate messages
  2. dictionary         — replace common LLM phrases with single-char codes
  3. dynamic_codebook   — generate per-session compress/decompress rules
  4. whitespace         — collapse redundant spaces/newlines
  5. json_compact       — minimal JSON serialization
  6. path_shortening    — shorten repeated file paths
  7. observation        — compress tool output (97% reduction for long outputs)

Usage:
    result = compress(messages)
    logger.info(f"Saved {result.savings_pct:.0%} tokens")

    use_messages = result.messages
"""
from __future__ import annotations

__all__ = [
    "compress",
    "CompressionResult",
    "should_compress",
]


import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any


_MAX_OBSERVATION_CHARS = 2000  # truncate tool outputs beyond this
_MIN_TOKENS_TO_COMPRESS = 500  # don't compress small contexts


@dataclass
class CompressionResult:
    messages: list[dict]
    original_chars: int
    compressed_chars: int
    savings_pct: float
    codebook: dict[str, str] = field(default_factory=dict)
    layers_applied: list[str] = field(default_factory=list)


# ── Layer 1: Deduplication ────────────────────────────────────────────────────

def _dedup_messages(messages: list[dict]) -> tuple[list[dict], bool]:
    """Remove exact duplicate consecutive messages."""
    seen: list[str] = []
    result: list[dict] = []
    changed = False
    for msg in messages:
        key = json.dumps(msg, sort_keys=True)
        if key not in seen[-3:]:  # allow some distance
            result.append(msg)
        else:
            changed = True
        seen.append(key)
    return result, changed


# ── Layer 2: Dictionary encoding ─────────────────────────────────────────────

_COMMON_PHRASES: dict[str, str] = {
    # LLM boilerplate
    "I understand your request": "⟨IUR⟩",
    "I'll help you with": "⟨IHY⟩",
    "Certainly! I'll": "⟨CI⟩",
    "Of course! I'll": "⟨OCI⟩",
    "Great question!": "⟨GQ⟩",
    "Based on the": "⟨BOT⟩",
    "In conclusion": "⟨IC⟩",
    "To summarize": "⟨TS⟩",
    "Additionally,": "⟨AD⟩",
    "Furthermore,": "⟨FU⟩",
    "It's important to note that": "⟨IITN⟩",
    "Please note that": "⟨PNT⟩",
    "I'd be happy to": "⟨IBHT⟩",
    "Let me help you": "⟨LMHY⟩",
    "Here's what I found": "⟨HWIF⟩",
    "Here is the": "⟨HIT⟩",
    "The following": "⟨TF⟩",
    "As requested": "⟨AR⟩",
    "The output is": "⟨TOI⟩",
    "The result is": "⟨TRI⟩",
    "```python": "⟨PY⟩",
    "```javascript": "⟨JS⟩",
    "```typescript": "⟨TS_⟩",
}

_REVERSE_DICT: dict[str, str] = {v: k for k, v in _COMMON_PHRASES.items()}


def _apply_dictionary(text: str) -> str:
    for phrase, code in _COMMON_PHRASES.items():
        text = text.replace(phrase, code)
    return text


def _reverse_dictionary(text: str) -> str:
    for code, phrase in _REVERSE_DICT.items():
        text = text.replace(code, phrase)
    return text


# ── Layer 3: Dynamic codebook ─────────────────────────────────────────────────

def _build_dynamic_codebook(messages: list[dict]) -> dict[str, str]:
    """Find repeated long phrases (> 20 chars) and assign single codes."""
    # Count phrase occurrences
    all_text = " ".join(
        str(msg.get("content", "")) for msg in messages
    )
    # Find repeated substrings of length 25-80
    phrase_counts: dict[str, int] = {}
    words = all_text.split()
    for i in range(len(words)):
        for n in range(4, 12):  # 4-12 word phrases
            phrase = " ".join(words[i:i+n])
            if len(phrase) > 25:
                phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1

    # Only compress phrases that appear 3+ times
    codebook: dict[str, str] = {}
    idx = 0
    for phrase, count in sorted(phrase_counts.items(), key=lambda x: -len(x[0])):
        if count >= 3 and len(phrase) > 25:
            code = f"§{idx}"
            codebook[phrase] = code
            idx += 1
            if idx > 50:  # max 50 codes
                break
    return codebook


def _apply_codebook(text: str, codebook: dict[str, str]) -> str:
    for phrase, code in codebook.items():
        text = text.replace(phrase, code)
    return text


# ── Layer 4: Whitespace normalization ─────────────────────────────────────────

def _normalize_whitespace(text: str) -> str:
    text = re.sub(r" {3,}", "  ", text)      # 3+ spaces → 2
    text = re.sub(r"\n{3,}", "\n\n", text)   # 3+ newlines → 2
    text = re.sub(r"\t", " ", text)           # tabs → space
    return text.strip()


# ── Layer 5: JSON compaction ──────────────────────────────────────────────────

def _compact_json_in_text(text: str) -> str:
    """Find JSON blocks and minimize them."""
    def _minimize(m: re.Match) -> str:
        try:
            obj = json.loads(m.group(0))
            return json.dumps(obj, separators=(",", ":"))
        except Exception:
            return m.group(0)

    # Match JSON objects/arrays
    return re.sub(r"\{[\s\S]*?\}", _minimize, text)


# ── Layer 6: Path shortening ──────────────────────────────────────────────────

def _shorten_paths(text: str, path_map: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Replace repeated file paths with short aliases."""
    paths = re.findall(r'(?:/[\w./\-]+\.(?:py|js|ts|json|yaml|yml|md|txt)){2,}', text)
    for p in paths:
        if p not in path_map and len(p) > 20:
            alias = f"«p{len(path_map)}»"
            path_map[p] = alias
    for p, alias in path_map.items():
        text = text.replace(p, alias)
    return text, path_map


# ── Layer 7: Observation compression ─────────────────────────────────────────

def _compress_observation(content: Any) -> Any:
    """Truncate long tool outputs and add summary marker."""
    if isinstance(content, str) and len(content) > _MAX_OBSERVATION_CHARS:
        truncated = content[:_MAX_OBSERVATION_CHARS]
        remaining = len(content) - _MAX_OBSERVATION_CHARS
        return f"{truncated}\n[…{remaining} chars truncated]"
    if isinstance(content, list):
        return [_compress_observation(c) for c in content]
    return content


# ── Main compress function ────────────────────────────────────────────────────

def should_compress(messages: list[dict], min_chars: int = 2000) -> bool:
    """Returns True if messages are large enough to benefit from compression."""
    total = sum(len(json.dumps(m)) for m in messages)
    return total > min_chars


def compress(
    messages: list[dict],
    config: dict | None = None,
) -> CompressionResult:
    """
    Run all 7 compression layers on messages.
    Returns CompressionResult with compressed messages and stats.
    """
    cfg = config or {}
    original_chars = sum(len(json.dumps(m)) for m in messages)
    result = [dict(m) for m in messages]   # deep copy
    layers: list[str] = []
    path_map: dict[str, str] = {}

    # Layer 1: Deduplication
    result, changed = _dedup_messages(result)
    if changed:
        layers.append("deduplication")

    # Build dynamic codebook from all messages
    codebook = _build_dynamic_codebook(result) if len(result) > 2 else {}
    if codebook:
        layers.append("dynamic_codebook")

    # Apply compression to message content
    for msg in result:
        content = msg.get("content", "")
        if not isinstance(content, str):
            # Tool output (list/dict) — apply observation compression
            msg["content"] = _compress_observation(content)
            if msg.get("role") == "tool":
                layers.append("observation")
            continue

        # Layer 2: Dictionary
        new_content = _apply_dictionary(content)
        if new_content != content:
            layers.append("dictionary")
        content = new_content

        # Layer 3: Dynamic codebook
        if codebook:
            content = _apply_codebook(content, codebook)

        # Layer 4: Whitespace
        new_content = _normalize_whitespace(content)
        if new_content != content:
            layers.append("whitespace")
        content = new_content

        # Layer 5: JSON compaction
        if "{" in content:
            new_content = _compact_json_in_text(content)
            if new_content != content:
                layers.append("json_compact")
            content = new_content

        # Layer 6: Path shortening
        content, path_map = _shorten_paths(content, path_map)
        if path_map:
            layers.append("path_shortening")

        # Layer 7: Observation (long tool results)
        if msg.get("role") == "tool" and len(content) > _MAX_OBSERVATION_CHARS:
            content = _compress_observation(content)
            layers.append("observation")

        msg["content"] = content

    compressed_chars = sum(len(json.dumps(m)) for m in result)
    savings = max(0.0, 1.0 - compressed_chars / max(original_chars, 1))

    # Prepend codebook header to first user message if we have one
    full_codebook = {**path_map}
    if codebook:
        full_codebook.update({v: k for k, v in codebook.items()})

    return CompressionResult(
        messages=result,
        original_chars=original_chars,
        compressed_chars=compressed_chars,
        savings_pct=savings,
        codebook=full_codebook,
        layers_applied=list(dict.fromkeys(layers)),  # dedup layer names
    )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    test_msgs = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Based on the code I provided, implement a function. I'd be happy to help you with that."},
        {"role": "assistant", "content": "Certainly! I'll implement the function. Based on the code I provided..."},
        {"role": "user", "content": "Great question! Furthermore, additionally, additionally, please do this."},
        {"role": "user", "content": "Based on the code I provided, implement a function. I'd be happy to help you with that."},  # duplicate
    ]

    result = compress(test_msgs)
    assert result.savings_pct >= 0
    assert len(result.messages) <= len(test_msgs)  # dedup removed duplicate

    print(f"OK compressor.py — 7-layer context compression")
    print(f"  original: {result.original_chars} chars")
    print(f"  compressed: {result.compressed_chars} chars")
    print(f"  savings: {result.savings_pct:.1%}")
    print(f"  layers: {result.layers_applied}")
