"""
VECTOR Taint Tracker — data provenance and flow enforcement.

Labels data with its origin, then enforces that tainted data cannot
reach sensitive sinks (shells, network calls, agent messages) without
explicit clearance.

5 taint labels (from agent OS types/taint.rs):
  EXTERNAL_NETWORK : came from the internet (web fetch, API response)
  USER_INPUT       : came from a human user message
  PII              : personally identifiable information
  SECRET           : API keys, passwords, tokens
  UNTRUSTED_AGENT  : output from an agent without high HP

3 sinks that tainted data must not reach unchecked:
  shell_exec       : bash/shell execution
  net_fetch        : outbound HTTP requests
  agent_message    : inter-agent communication

Ported from agent OS types/taint.rs.
"""
from __future__ import annotations

__all__ = [
    "get_taint_tracker",
    "TaintedValue",
    "TaintLabel",
    "TaintSink",
    "TaintTracker",
    "TaintViolation",
]


from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


class TaintLabel(str, Enum):
    """Origin labels for data provenance tracking."""
    EXTERNAL_NETWORK = "external_network"   # from web/API
    USER_INPUT       = "user_input"         # from human
    PII              = "pii"                # personal data
    SECRET           = "secret"             # credentials/keys
    UNTRUSTED_AGENT  = "untrusted_agent"    # from low-HP agent

    @property
    def is_high_risk(self) -> bool:
        return self in (TaintLabel.SECRET, TaintLabel.PII)


class TaintSink(str, Enum):
    """Destinations where tainted data must be checked."""
    SHELL_EXEC     = "shell_exec"
    NET_FETCH      = "net_fetch"
    AGENT_MESSAGE  = "agent_message"
    FILE_WRITE     = "file_write"
    LLM_PROMPT     = "llm_prompt"


@dataclass
class TaintViolation:
    label: TaintLabel
    sink: TaintSink
    value_preview: str   # first 80 chars of the tainted value
    message: str

    def __str__(self) -> str:
        return f"TAINT VIOLATION: {self.label.value} data reached {self.sink.value} sink — {self.message}"


@dataclass
class TaintedValue:
    """
    A value with its taint labels. Propagates through operations.

    Usage:
        val = TaintedValue("user input text", {TaintLabel.USER_INPUT})
        combined = val.propagate_to("processed: " + val.value)
        # combined inherits USER_INPUT label
    """
    value: Any
    labels: set[TaintLabel] = field(default_factory=set)
    cleared_for: set[TaintSink] = field(default_factory=set)   # explicitly approved sinks

    @property
    def is_tainted(self) -> bool:
        return len(self.labels) > 0

    @property
    def is_high_risk(self) -> bool:
        return any(l.is_high_risk for l in self.labels)

    def propagate_to(self, new_value: Any) -> "TaintedValue":
        """Create a new TaintedValue inheriting this one's labels."""
        return TaintedValue(value=new_value, labels=set(self.labels))

    def merge(self, other: "TaintedValue") -> "TaintedValue":
        """Combine two tainted values (union of labels)."""
        return TaintedValue(
            value=self.value,
            labels=self.labels | other.labels,
            cleared_for=self.cleared_for & other.cleared_for,
        )

    def clear_for(self, sink: TaintSink) -> "TaintedValue":
        """Mark this value as reviewed and safe for a specific sink."""
        return TaintedValue(
            value=self.value,
            labels=self.labels,
            cleared_for=self.cleared_for | {sink},
        )

    def label_str(self) -> str:
        return ", ".join(l.value for l in self.labels) or "clean"


class TaintTracker:
    """
    Tracks data provenance and enforces sink policies.

    Usage:
        tracker = TaintTracker()

        # Tag incoming data
        user_msg = tracker.tag(request.body, TaintLabel.USER_INPUT)
        api_resp = tracker.tag(response.text, TaintLabel.EXTERNAL_NETWORK)

        # Before using in shell
        violation = tracker.check_sink(user_msg, TaintSink.SHELL_EXEC)
        if violation:
            raise SecurityError(str(violation))

        # Clear for known-safe use
        safe = tracker.clear(user_msg, TaintSink.SHELL_EXEC, reason="sanitized by shlex.quote")
    """

    # Which labels are blocked at which sinks by default
    _SINK_POLICY: dict[TaintSink, set[TaintLabel]] = {
        TaintSink.SHELL_EXEC: {
            TaintLabel.EXTERNAL_NETWORK,
            TaintLabel.USER_INPUT,
            TaintLabel.UNTRUSTED_AGENT,
        },
        TaintSink.NET_FETCH: {
            TaintLabel.SECRET,
            TaintLabel.PII,
        },
        TaintSink.AGENT_MESSAGE: {
            TaintLabel.SECRET,
        },
        TaintSink.FILE_WRITE: {
            TaintLabel.SECRET,
            TaintLabel.PII,
        },
        TaintSink.LLM_PROMPT: {
            TaintLabel.SECRET,
        },
    }

    def __init__(self, strict: bool = True) -> None:
        self._strict = strict
        self._violations: list[TaintViolation] = []

    def tag(self, value: Any, *labels: TaintLabel) -> TaintedValue:
        """Create a tainted value with the given labels."""
        safe_labels: set[TaintLabel] = set()
        for lbl in labels:
            if isinstance(lbl, TaintLabel):
                safe_labels.add(lbl)
            elif isinstance(lbl, str):
                try:
                    safe_labels.add(TaintLabel(lbl))
                except ValueError:
                    pass
        return TaintedValue(value=value, labels=safe_labels)

    def tag_external(self, value: Any) -> TaintedValue:
        return self.tag(value, TaintLabel.EXTERNAL_NETWORK)

    def tag_user(self, value: Any) -> TaintedValue:
        return self.tag(value, TaintLabel.USER_INPUT)

    def tag_secret(self, value: Any) -> TaintedValue:
        return self.tag(value, TaintLabel.SECRET)

    def tag_pii(self, value: Any) -> TaintedValue:
        return self.tag(value, TaintLabel.PII)

    def check_sink(
        self,
        tainted: TaintedValue,
        sink: TaintSink,
    ) -> TaintViolation | None:
        """
        Check if tainted data can reach a sink.
        Returns TaintViolation if blocked, None if safe.
        """
        if not tainted.is_tainted:
            return None

        if sink in tainted.cleared_for:
            return None   # explicitly cleared

        blocked_labels = self._SINK_POLICY.get(sink, set())
        violations = tainted.labels & blocked_labels

        if violations:
            preview = str(tainted.value)[:80]
            label = next(iter(violations))
            violation = TaintViolation(
                label=label,
                sink=sink,
                value_preview=preview,
                message=f"{label.value} data must not reach {sink.value} without explicit clearance",
            )
            self._violations.append(violation)
            if self._strict:
                logger.warning("[VECTOR][taint] {}", violation)
            return violation

        return None

    def clear(
        self,
        tainted: TaintedValue,
        sink: TaintSink,
        reason: str = "",
    ) -> TaintedValue:
        """Explicitly mark data as safe for a sink (after sanitization)."""
        if reason:
            logger.debug("[VECTOR][taint] cleared for {}: {}", sink.value, reason)
        return tainted.clear_for(sink)

    def propagate(self, source: TaintedValue, new_value: Any) -> TaintedValue:
        """Create derived value inheriting source's taint."""
        return source.propagate_to(new_value)

    def merge(self, *values: TaintedValue) -> TaintedValue:
        """Merge multiple tainted values (union of labels)."""
        if not values:
            return TaintedValue(value=None)
        result = values[0]
        for other in values[1:]:
            result = result.merge(other)
        return result

    @property
    def violation_count(self) -> int:
        return len(self._violations)

    def recent_violations(self, n: int = 10) -> list[TaintViolation]:
        return self._violations[-n:]


_tracker: TaintTracker | None = None


def get_taint_tracker() -> TaintTracker:
    global _tracker
    if _tracker is None:
        _tracker = TaintTracker()
    return _tracker


if __name__ == "__main__":
    tracker = TaintTracker()

    # Tag data from different sources
    user_input = tracker.tag_user("ls -la && cat /etc/passwd")
    api_response = tracker.tag_external('{"result": "some data"}')
    api_key = tracker.tag_secret("sk-1234567890abcdef")

    # User input should be blocked from shell
    v = tracker.check_sink(user_input, TaintSink.SHELL_EXEC)
    assert v is not None, "User input must not reach shell unchecked"

    # Secret must not reach net fetch
    v2 = tracker.check_sink(api_key, TaintSink.NET_FETCH)
    assert v2 is not None, "Secret must not be sent over network"

    # API response is ok to relay to agent
    v3 = tracker.check_sink(api_response, TaintSink.AGENT_MESSAGE)
    assert v3 is None, "External data can be relayed to agents"

    # Clear for use after sanitization
    sanitized = tracker.clear(user_input, TaintSink.SHELL_EXEC, reason="passed through shlex.quote")
    v4 = tracker.check_sink(sanitized, TaintSink.SHELL_EXEC)
    assert v4 is None, "Cleared data should pass"

    # Taint propagation
    derived = tracker.propagate(api_response, "processed: data")
    assert derived.labels == api_response.labels

    # Merge labels
    merged = tracker.merge(user_input, api_response)
    assert TaintLabel.USER_INPUT in merged.labels
    assert TaintLabel.EXTERNAL_NETWORK in merged.labels

    # Clean data passes everywhere
    clean = TaintedValue("safe string")
    assert tracker.check_sink(clean, TaintSink.SHELL_EXEC) is None

    print("OK taint_tracker.py — 5 labels, 5 sinks, propagation, clearance verified")
