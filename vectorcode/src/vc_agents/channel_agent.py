# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""ChannelAgent — bridge between messaging channels and AI agents.

Routes incoming :class:`~vector.channels._abc.ChannelMessage` objects
to an agent, classifies queries as "quick" or "deep", and delivers responses
either inline or as a preview with an escalation link to a full report.
"""

from __future__ import annotations

import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from loguru import logger

from vectorcode.src.channels._abc import BaseChannel, ChannelMessage

# ---------------------------------------------------------------------------
# Query classifier
# ---------------------------------------------------------------------------

_QUICK_PREFIXES = re.compile(
    r"^(when\b|where\b|find\b|who\b|what's\b)",
    re.IGNORECASE,
)

_DEEP_KEYWORDS = re.compile(
    r"\b(summarize|research|context|compare|analyze|overview|timeline|history)\b",
    re.IGNORECASE,
)

_TIME_RANGE = re.compile(
    r"\blast\s+(week|month|quarter|year)\b",
    re.IGNORECASE,
)

def classify_query(text: str) -> str:
    """Return ``'quick'`` or ``'deep'`` based on heuristics.

    Deep signals take priority over quick signals.  A query is classified as
    deep if it contains deep keywords, a time-range phrase, or is longer than
    20 words.  Otherwise it is quick.
    """
    words = text.split()
    if _DEEP_KEYWORDS.search(text):
        return "deep"
    if _TIME_RANGE.search(text):
        return "deep"
    if len(words) > 20:
        return "deep"
    return "quick"

# ---------------------------------------------------------------------------
# ChannelAgent
# ---------------------------------------------------------------------------

_ESCALATION_TEMPLATE = "{preview}...\n\n---\nFull report ready — open in VectorCode:\nvector://research/{session_id}"
_LONG_RESPONSE_THRESHOLD = 500

class ChannelAgent:
    """Bridge between a :class:`BaseChannel` and an agent.

    On each incoming message the agent is invoked in a background thread so
    that :meth:`_handle_message` never blocks the channel's event loop.
    Quick queries with short responses are delivered inline; deep queries or
    long responses trigger a preview + escalation link.

    Parameters
    ----------
    channel:
        A connected :class:`BaseChannel` instance.
    agent:
        Any object that exposes a ``run(input: str) -> AgentResult``-compatible
        method (typically a :class:`~vector.agents._abc.BaseAgent`
        subclass).
    max_workers:
        Size of the background :class:`~concurrent.futures.ThreadPoolExecutor`.
    """

    def __init__(
        self,
        channel: BaseChannel,
        agent: Any,
        *,
        max_workers: int = 2,
    ) -> None:
        # OWNER DECISION: this fully implemented bridge currently has no
        # production caller. Decide whether it should be wired into channel
        # startup or removed; until then its thread-pool lifecycle is dormant.
        self._channel = channel
        self._agent = agent
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        channel.on_message(self._handle_message)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_message(self, msg: ChannelMessage) -> Optional[str]:
        """Submit *msg* to the background pool and return ``None`` immediately."""
        self._pool.submit(self._process_message, msg)
        return None

    def _process_message(self, msg: ChannelMessage) -> None:
        """Classify, run the agent, and reply to the channel."""
        query_type = classify_query(msg.content)
        session_id = msg.session_id or uuid.uuid4().hex[:16]

        try:
            result = self._agent.run(msg.content)
            content = getattr(result, "content", None)
            response_text = str(result) if content is None else str(content)
        except Exception:  # noqa: BLE001
            logger.opt(exception=True).error(
                "[VECTOR][vc_agents.channel_agent] agent processing failed"
            )
            friendly = "Sorry, I ran into an error while processing your request."
            self._channel.send(
                msg.channel,
                friendly,
                conversation_id=msg.conversation_id,
            )
            return

        is_long = len(response_text) > _LONG_RESPONSE_THRESHOLD

        if query_type == "deep" or is_long:
            preview = response_text[:_LONG_RESPONSE_THRESHOLD]
            reply = _ESCALATION_TEMPLATE.format(
                preview=preview,
                session_id=session_id,
            )
        else:
            reply = response_text

        self._channel.send(
            msg.channel,
            reply,
            conversation_id=msg.conversation_id,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Shut down the background thread pool."""
        self._pool.shutdown(wait=True)

__all__ = ["ChannelAgent", "classify_query"]
