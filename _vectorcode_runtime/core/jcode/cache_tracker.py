"""
KV cache append-only violation detector.

When providers don't report cache tokens (e.g. OpenRouter/Fireworks),
we track message prefix hashes ourselves. If the prefix changes between
requests the KV cache was invalidated — surfaces a CacheViolation.

Ported from the high-performance agent harness cache_tracker.rs.
"""
from __future__ import annotations

__all__ = [
    "CacheTracker",
    "CacheViolation",
    "MAX_HISTORY",
]


import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any


from loguru import logger

MAX_HISTORY = 10


def _stable_message_hash(message: dict) -> int:
    """Deterministic hash of a message dict (role + content)."""
    role = message.get("role", "")
    content = message.get("content", "")
    if isinstance(content, list):
        content = str(content)
    raw = f"{role}:{content}".encode()
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def _extend_hash(prev: int, next_hash: int) -> int:
    """Combine two hashes into a rolling prefix hash."""
    combined = f"{prev}:{next_hash}".encode()
    return int(hashlib.sha256(combined).hexdigest()[:16], 16)


@dataclass
class CacheViolation:
    turn: int
    message_count: int
    expected_hash: str
    actual_hash: str
    reason: str

    def __str__(self) -> str:
        return f"[Turn {self.turn}] {self.reason}"


@dataclass
class CacheTracker:
    """
    Tracks message prefix hashes to detect KV cache violations.

    Usage:
        tracker = CacheTracker()
        violation = tracker.record_request(messages)
        if violation:
            logger.warning(f"[VECTOR][cache] {violation}")
        # On compaction or model switch:
        tracker.reset()
    """
    _previous_prefix_hash: int | None = field(default=None, repr=False)
    _previous_message_count: int = field(default=0, repr=False)
    _turn_count: int = field(default=0, repr=False)
    _hash_history: deque = field(default_factory=lambda: deque(maxlen=MAX_HISTORY), repr=False)
    _last_violation: CacheViolation | None = field(default=None, repr=False)

    @staticmethod
    def _hash_label(h: int) -> str:
        return f"{h:016x}"

    @staticmethod
    def _prefix_hashes(messages: list[dict]) -> list[int]:
        hashes: list[int] = []
        for msg in messages:
            mh = _stable_message_hash(msg)
            prev = hashes[-1] if hashes else None
            ph = _extend_hash(prev, mh) if prev is not None else mh
            hashes.append(ph)
        return hashes

    def record_request(self, messages: list[dict]) -> CacheViolation | None:
        """
        Call BEFORE sending each request to the provider.
        Returns CacheViolation if the append-only property was violated.
        """
        prefix_hashes = self._prefix_hashes(messages)
        return self._record_prefix_hashes(prefix_hashes)

    def _record_prefix_hashes(self, prefix_hashes: list[int]) -> CacheViolation | None:
        current_count = len(prefix_hashes)
        current_full_hash = prefix_hashes[-1] if prefix_hashes else None
        previous_count = self._previous_message_count

        prefix_hash_at_prev = (
            prefix_hashes[previous_count - 1]
            if previous_count > 0 and previous_count <= current_count
            else None
        )

        return self._record_snapshot(current_count, prefix_hash_at_prev, current_full_hash)

    def _record_snapshot(
        self,
        current_count: int,
        prefix_hash_at_previous_count: int | None,
        current_full_hash: int | None,
    ) -> CacheViolation | None:
        self._turn_count += 1

        if self._turn_count == 1 or self._previous_prefix_hash is None:
            h = current_full_hash or 0
            self._previous_prefix_hash = h
            self._previous_message_count = current_count
            self._hash_history.append(h)
            self._last_violation = None
            return None

        previous_hash = self._previous_prefix_hash
        previous_count = self._previous_message_count

        if current_count < previous_count:
            current_hash = current_full_hash or 0
            violation = CacheViolation(
                turn=self._turn_count,
                message_count=current_count,
                expected_hash=self._hash_label(previous_hash),
                actual_hash=self._hash_label(current_hash),
                reason=f"Messages removed: had {previous_count} messages, now have {current_count}",
            )
            self._update_state(current_hash, current_count)
            self._last_violation = violation
            logger.warning(f"[VECTOR][cache_tracker] {violation}")
            return violation

        prefix_hash = prefix_hash_at_previous_count or 0
        if prefix_hash != previous_hash:
            current_hash = current_full_hash or 0
            violation = CacheViolation(
                turn=self._turn_count,
                message_count=current_count,
                expected_hash=self._hash_label(previous_hash),
                actual_hash=self._hash_label(prefix_hash),
                reason=(
                    f"Prefix modified: first {previous_count} messages changed "
                    f"(hash {self._hash_label(previous_hash)} -> {self._hash_label(prefix_hash)})"
                ),
            )
            self._update_state(current_hash, current_count)
            self._last_violation = violation
            logger.warning(f"[VECTOR][cache_tracker] {violation}")
            return violation

        full_hash = current_full_hash or 0
        self._update_state(full_hash, current_count)
        self._last_violation = None
        return None

    def _update_state(self, full_hash: int, count: int) -> None:
        self._previous_prefix_hash = full_hash
        self._previous_message_count = count
        self._hash_history.append(full_hash)

    def reset(self) -> None:
        """Reset after compaction or model switch."""
        self._previous_prefix_hash = None
        self._previous_message_count = 0
        self._turn_count = 0
        self._hash_history.clear()
        self._last_violation = None

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def had_violation(self) -> bool:
        return self._last_violation is not None

    @property
    def last_violation(self) -> CacheViolation | None:
        return self._last_violation


if __name__ == "__main__":
    tracker = CacheTracker()

    # Turn 1: baseline
    msgs1 = [{"role": "user", "content": "Hello"}]
    assert tracker.record_request(msgs1) is None

    # Turn 2: normal growth — no violation
    msgs2 = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
    ]
    assert tracker.record_request(msgs2) is None

    # Turn 3: prefix changed (first message modified) — violation
    msgs3_modified = [
        {"role": "user", "content": "Hello MODIFIED"},
        {"role": "assistant", "content": "Hi!"},
        {"role": "user", "content": "new turn"},
    ]
    v = tracker.record_request(msgs3_modified)
    assert v is not None, "Expected violation"
    assert "Prefix modified" in v.reason, f"Unexpected: {v.reason}"

    # Test messages removed
    tracker2 = CacheTracker()
    tracker2.record_request([{"role": "user", "content": "A"},
                              {"role": "assistant", "content": "B"},
                              {"role": "user", "content": "C"}])
    v2 = tracker2.record_request([{"role": "user", "content": "A"}])
    assert v2 is not None and "Messages removed" in v2.reason

    # Reset clears state
    tracker.reset()
    assert tracker.record_request(msgs1) is None

    print("OK cache_tracker.py")
