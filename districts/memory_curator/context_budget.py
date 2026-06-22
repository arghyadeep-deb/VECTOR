"""Deterministic context budget manager inspired by Headroom.

Stores original oversized chunks behind retrieval handles and passes compact
placeholders to LLM prompts. This is intentionally dependency-free and safe to
use before any model call.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class ContextHandle:
    handle: str
    original_chars: int
    compact_chars: int
    content_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContextBudgetManager:
    def __init__(self, *, max_message_chars: int = 4000, head_chars: int = 1200, tail_chars: int = 800):
        self.max_message_chars = max_message_chars
        self.head_chars = head_chars
        self.tail_chars = tail_chars
        self._store: dict[str, str] = {}
        self._handles: dict[str, ContextHandle] = {}

    def compact_text(self, text: str, *, label: str = "context") -> tuple[str, ContextHandle | None]:
        if len(text) <= self.max_message_chars:
            return text, None
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        handle_id = f"ctx:{digest[:16]}"
        self._store[handle_id] = text
        compact = (
            f"[{label} compacted; retrieval_handle={handle_id}; "
            f"original_chars={len(text)}; sha256={digest}]\n\n"
            f"{text[:self.head_chars]}\n\n"
            "[... middle omitted by VECTOR context budget ...]\n\n"
            f"{text[-self.tail_chars:]}"
        )
        handle = ContextHandle(
            handle=handle_id,
            original_chars=len(text),
            compact_chars=len(compact),
            content_hash=digest,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._handles[handle_id] = handle
        return compact, handle

    def compact_messages(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        compacted: list[dict[str, Any]] = []
        handles: list[dict[str, Any]] = []
        for index, msg in enumerate(messages):
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, default=str)
            new_content, handle = self.compact_text(content, label=f"message:{index}:{msg.get('role', 'unknown')}")
            updated = dict(msg)
            updated["content"] = new_content
            compacted.append(updated)
            if handle:
                handles.append(handle.to_dict())
        return compacted, handles

    def retrieve(self, handle: str) -> str | None:
        return self._store.get(handle)

    def stats(self) -> dict[str, Any]:
        original = sum(h.original_chars for h in self._handles.values())
        compact = sum(h.compact_chars for h in self._handles.values())
        return {
            "handles": len(self._handles),
            "original_chars": original,
            "compact_chars": compact,
            "estimated_saved_chars": max(0, original - compact),
        }

