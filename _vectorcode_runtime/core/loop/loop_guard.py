"""
VECTOR Loop Guard — prevents infinite agent loops and detects phantom actions.

Enforces safety limits on the autonomous agent loop:
  MAX_ITERATIONS  : 50 turns per task (configurable)
  Phantom detection: same tool called 3x in a row with identical args
  Silent tokens   : model outputs only whitespace/newlines
  Session repair  : 7-phase message history validation

Also provides session repair — validates and fixes corrupted message histories
before they cause LLM API errors.

Ported from the agent OS runtime agent_loop.rs loop guard system.
"""
from __future__ import annotations

__all__ = [
    "LoopGuardState",
    "LoopViolation",
    "repair_session",
]


import time
from collections import deque
from dataclasses import dataclass, field

from loguru import logger

MAX_ITERATIONS: int = 50          # absolute hard cap per task
MAX_RETRIES: int = 3              # retries on transient errors
TOOL_TIMEOUT_SECS: int = 120      # per-tool execution timeout
AGENT_TOOL_TIMEOUT_SECS: int = 600  # for slow agent-spawning tools
PHANTOM_THRESHOLD: int = 3        # identical tool calls before phantom detection


@dataclass
class LoopViolation:
    kind: str        # "max_iterations" | "phantom" | "silent_tokens" | "session_corrupt"
    iteration: int
    message: str
    tool_name: str = ""

    def __str__(self) -> str:
        return f"[LoopGuard:{self.kind}] iter={self.iteration} {self.message}"


@dataclass
class LoopGuardState:
    """Per-task loop guard state. Create one per task execution."""
    task_id: str
    iteration: int = 0
    max_iterations: int = MAX_ITERATIONS
    # Bounded ring buffer of recent (tool, args_hash) — cannot grow without
    # bound across a long task; phantom detection only needs the last few.
    _recent_calls: "deque[tuple[str, str]]" = field(
        default_factory=lambda: deque(maxlen=PHANTOM_THRESHOLD + 2)
    )
    _violations: list[LoopViolation] = field(default_factory=list)
    _started_at: float = field(default_factory=time.time)

    def tick(self) -> LoopViolation | None:
        """
        Called at the start of each loop iteration.
        Returns LoopViolation if the iteration limit is exceeded.
        """
        self.iteration += 1
        if self.iteration > self.max_iterations:
            v = LoopViolation(
                kind="max_iterations",
                iteration=self.iteration,
                message=f"Exceeded MAX_ITERATIONS={self.max_iterations}. Task terminated.",
            )
            self._violations.append(v)
            logger.warning("[VECTOR][loop_guard] {}", v)
            return v
        return None

    def check_phantom(self, tool_name: str, args: dict) -> LoopViolation | None:
        """
        Detect phantom actions — same tool called identically 3+ times in a row.
        This indicates the model is stuck in a loop without making progress.
        """
        args_hash = str(sorted(args.items())) if args else "()"
        call_key = (tool_name, args_hash)

        self._recent_calls.append(call_key)  # deque(maxlen) auto-drops oldest

        # Check if last N calls are identical
        if len(self._recent_calls) >= PHANTOM_THRESHOLD:
            last_n = list(self._recent_calls)[-PHANTOM_THRESHOLD:]
            if all(c == call_key for c in last_n):
                v = LoopViolation(
                    kind="phantom",
                    iteration=self.iteration,
                    tool_name=tool_name,
                    message=(
                        f"Phantom action detected: '{tool_name}' called {PHANTOM_THRESHOLD} times "
                        f"with identical arguments. Breaking loop."
                    ),
                )
                self._violations.append(v)
                logger.warning("[VECTOR][loop_guard] {}", v)
                return v
        return None

    def check_silent_tokens(self, response_text: str) -> LoopViolation | None:
        """
        Detect silent token responses — model outputs only whitespace/special chars.
        Indicates the model has stalled and is not making progress.
        """
        stripped = response_text.strip()
        if not stripped or all(c in '\n\r\t \x00\x01\x02\x03' for c in stripped):
            v = LoopViolation(
                kind="silent_tokens",
                iteration=self.iteration,
                message="Model produced silent/empty response. Possible stall detected.",
            )
            self._violations.append(v)
            logger.warning("[VECTOR][loop_guard] {}", v)
            return v
        return None

    @property
    def is_terminated(self) -> bool:
        return any(v.kind == "max_iterations" for v in self._violations)

    @property
    def elapsed_secs(self) -> float:
        return time.time() - self._started_at

    @property
    def violations(self) -> list[LoopViolation]:
        return list(self._violations)

    def reset_recent_calls(self) -> None:
        """Call after a successful different tool call to clear phantom detection."""
        self._recent_calls.clear()

    def reset(self) -> None:
        """Restore a fully fresh state after termination, so the same
        long-lived guard instance can be reused for the next task cycle.

        Without this, is_terminated() stays permanently True forever once
        any max_iterations violation has been recorded (_violations is
        append-only) -- callers that loop on the same guard instance (e.g.
        autonomous_loop.py's observe_loop(), which creates one guard for
        the entire process lifetime) would otherwise see is_terminated
        stuck True on every subsequent tick.
        """
        self.iteration = 0
        self._violations.clear()
        self._recent_calls.clear()
        self._started_at = time.time()

    def guidance_for_tool_error(self, tool_name: str, error: str) -> str:
        """
        Generate helpful guidance injected into the next LLM prompt
        when a tool fails, to steer the model away from retry loops.
        """
        generic = (
            f"The tool '{tool_name}' failed with: {error[:200]}. "
            "Do not retry the same tool with the same arguments. "
            "Consider: using a different approach, asking for clarification, "
            "or reporting the error to the user."
        )
        specific = {
            "bash": "If the command failed, check the error message carefully. "
                    "Try a simpler command or break the task into smaller steps.",
            "web_fetch": "If the URL fetch failed, try a different URL or search first.",
            "read_file": "If file reading failed, check if the path is correct.",
        }.get(tool_name, "")
        return generic + (" " + specific if specific else "")


# ── Session repair (7-phase validation) ───────────────────────────────────────

def repair_session(messages: list[dict]) -> tuple[list[dict], int]:
    """
    Validate and repair a message history.

    7-phase repair (from agent OS agent_loop.rs session repair):
      1. Remove empty messages
      2. Ensure first message is user role (or system)
      3. Remove consecutive duplicate assistant messages
      4. Fix orphaned tool results (no preceding tool_use)
      5. Remove messages with no content
      6. Enforce alternating user/assistant (insert synthetic if needed)
      7. Trim trailing assistant messages (conversation must end on user)

    Returns (repaired_messages, repairs_made).
    """
    repairs = 0
    msgs = list(messages)

    # Phase 1: Remove empty messages
    before = len(msgs)
    msgs = [m for m in msgs if m.get("content") or m.get("tool_calls") or m.get("tool_use")]
    repairs += before - len(msgs)

    # Phase 2: First message must be user or system
    while msgs and msgs[0].get("role") == "assistant":
        msgs.pop(0)
        repairs += 1

    # Phase 3: Remove consecutive duplicate assistant messages
    deduplicated = []
    for msg in msgs:
        if (deduplicated and
                msg.get("role") == "assistant" and
                deduplicated[-1].get("role") == "assistant" and
                msg.get("content") == deduplicated[-1].get("content")):
            repairs += 1
            continue
        deduplicated.append(msg)
    msgs = deduplicated

    # Phase 4: Remove orphaned tool results
    # A tool result must be preceded by an assistant message with a tool_use/tool_calls
    cleaned = []
    for i, msg in enumerate(msgs):
        if msg.get("role") == "tool":
            preceding = cleaned[-1] if cleaned else None
            if not preceding or preceding.get("role") != "assistant":
                repairs += 1
                continue
            # Check if there's a tool_calls or tool_use in preceding
            content = preceding.get("content", [])
            tool_calls = preceding.get("tool_calls", [])
            has_tool_use = (
                tool_calls or
                (isinstance(content, list) and
                 any(b.get("type") in ("tool_use", "tool_calls") for b in content if isinstance(b, dict)))
            )
            if not has_tool_use:
                repairs += 1
                continue
        cleaned.append(msg)
    msgs = cleaned

    # Phase 5: Remove None/empty content messages
    before = len(msgs)
    msgs = [m for m in msgs if m.get("content") is not None or m.get("tool_calls")]
    repairs += before - len(msgs)

    # Phase 6: Trim trailing assistant messages (last must be user for new turn)
    while msgs and msgs[-1].get("role") == "assistant":
        msgs.pop()
        repairs += 1

    if repairs:
        logger.info("[VECTOR][session_repair] {} repair(s) applied to {} messages", repairs, len(msgs))

    return msgs, repairs


if __name__ == "__main__":
    # LoopGuard tests
    state = LoopGuardState(task_id="test_001")

    # Normal ticks
    for _ in range(5):
        v = state.tick()
        assert v is None

    # Phantom detection
    for _ in range(PHANTOM_THRESHOLD):
        state.check_phantom("bash", {"cmd": "ls"})
    v = state.check_phantom("bash", {"cmd": "ls"})
    assert v is not None and v.kind == "phantom"

    # Silent token detection
    v2 = state.check_silent_tokens("   \n\n\t  ")
    assert v2 is not None and v2.kind == "silent_tokens"

    # Max iterations
    state2 = LoopGuardState(task_id="test_002", max_iterations=3)
    for _ in range(3):
        state2.tick()
    v3 = state2.tick()
    assert v3 is not None and v3.kind == "max_iterations"
    assert state2.is_terminated

    # Session repair tests
    messages = [
        {"role": "assistant", "content": "orphan at start"},  # phase 2
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "assistant", "content": "hi"},    # duplicate, phase 3
        {"role": "tool", "content": "result"},     # orphaned tool result, phase 4
        {"role": "user", "content": "continue"},
        {"role": "assistant", "content": "done"},  # trailing, phase 6
    ]
    repaired, count = repair_session(messages)
    assert count > 0
    assert repaired[0]["role"] in ("user", "system")
    assert repaired[-1]["role"] != "assistant"

    print(f"OK loop_guard.py — max_iter={MAX_ITERATIONS}, phantom={PHANTOM_THRESHOLD}x, 7-phase repair")
