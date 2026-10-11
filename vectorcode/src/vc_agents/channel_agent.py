# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb

"""Async bridge between messaging channels and governed VECTOR agents."""

from __future__ import annotations

import asyncio
import inspect
import re
from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger

from vectorcode.src.channels._abc import BaseChannel, ChannelMessage
from vectorcode.src.vc_agents._abc import AgentResult

_DEEP_KEYWORDS = re.compile(
    r"\b(summarize|research|context|compare|analyze|overview|timeline|history)\b",
    re.IGNORECASE,
)
_TIME_RANGE = re.compile(r"\blast\s+(week|month|quarter|year)\b", re.IGNORECASE)
_AGENT_COMMAND = re.compile(
    r"^/agent\s+(?P<target>\S+)\s+(?P<task_type>\S+)\s+(?P<query>.+)$",
    re.DOTALL,
)
_AGENT_USAGE = "Usage: /agent <agent-id-or-name> <task-type> <request>"
# FL-027: this used to promise a "vector://research/{session_id}" URI with
# no producer, store, or consumer anywhere in the repo -- a dead-end link.
# Truncate truthfully instead of claiming a retrievable full report exists.
_ESCALATION_TEMPLATE = (
    "{preview}...\n\n"
    "[Response truncated -- the full report isn't retrievable through "
    "this channel yet.]"
)
_LONG_RESPONSE_THRESHOLD = 500


def classify_query(text: str) -> str:
    """Return ``quick`` or ``deep`` using the established heuristics."""
    if _DEEP_KEYWORDS.search(text) or _TIME_RANGE.search(text):
        return "deep"
    if len(text.split()) > 20:
        return "deep"
    return "quick"


@dataclass(frozen=True, slots=True)
class AgentCommand:
    target: str
    task_type: str
    query: str


def parse_agent_command(text: str) -> AgentCommand | None:
    """Parse the explicit production trigger, returning ``None`` if unmatched."""
    match = _AGENT_COMMAND.fullmatch((text or "").strip())
    if match is None:
        return None
    return AgentCommand(**{key: value.strip() for key, value in match.groupdict().items()})


class GovernedAgentInvoker:
    """Resolve a named city agent and deliver only through A2A → Governor."""

    async def run(self, content: str) -> AgentResult:
        command = parse_agent_command(content)
        if command is None:
            return AgentResult(content=_AGENT_USAGE)

        from core.city.a2a_bus import get_bus

        reply = await get_bus().ask(
            "owner_channel",
            command.task_type,
            {"query": command.query, "content": command.query},
            to=command.target,
            origin="external",
        )
        if reply.delivered:
            result = reply.result
            response = result.get("response") or result.get("content")
            if response is None:
                response = str(result)
        else:
            response = reply.refused or reply.error or reply.status
        return AgentResult(content=str(response), metadata={"a2a": reply.to_dict()})


class ChannelAgent:
    """Bridge channel messages to an agent using asyncio-owned tasks.

    ``channel`` may be ``None`` for gateways that return the response through
    their own delivery pipeline. Traditional ``BaseChannel`` instances keep
    the original callback registration shape.
    """

    def __init__(
        self,
        channel: BaseChannel | None,
        agent: Any,
        *,
        max_workers: int = 2,
    ) -> None:
        # ``max_workers`` remains accepted for source compatibility. Asyncio
        # task ownership replaces the old private ThreadPoolExecutor.
        del max_workers
        self._channel = channel
        self._agent = agent
        self._tasks: set[asyncio.Task[str]] = set()
        if channel is not None:
            channel.on_message(self._handle_message)

    @property
    def pending_tasks(self) -> tuple[asyncio.Task[str], ...]:
        return tuple(self._tasks)

    def _handle_message(self, msg: ChannelMessage) -> Optional[str]:
        """Schedule a callback-delivered message and return immediately."""
        self.submit_message(msg)
        return None

    def submit_text(self, content: str) -> asyncio.Task[str]:
        """Schedule text on the running event loop and return the owned task."""
        return self.submit_message(ChannelMessage("chat", "owner", content))

    def submit_message(self, msg: ChannelMessage) -> asyncio.Task[str]:
        task = asyncio.get_running_loop().create_task(self._process_message(msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def process_text(self, content: str) -> str:
        """Run one message inline for an asyncio-native caller such as GatewayRunner."""
        return await self._process_message(ChannelMessage("chat", "owner", content), send=False)

    async def _process_message(self, msg: ChannelMessage, *, send: bool = True) -> str:
        """Classify, await the agent if needed, and optionally reply."""
        query_type = classify_query(msg.content)

        try:
            result = self._agent.run(msg.content)
            if inspect.isawaitable(result):
                result = await result
            content = getattr(result, "content", None)
            response_text = str(result) if content is None else str(content)
        except Exception:  # noqa: BLE001
            logger.opt(exception=True).error(
                "[VECTOR][vc_agents.channel_agent] agent processing failed"
            )
            response_text = "Sorry, I ran into an error while processing your request."
            query_type = "quick"

        if query_type == "deep" or len(response_text) > _LONG_RESPONSE_THRESHOLD:
            response_text = _ESCALATION_TEMPLATE.format(
                preview=response_text[:_LONG_RESPONSE_THRESHOLD],
            )

        if send and self._channel is not None:
            sent = self._channel.send(
                msg.channel,
                response_text,
                conversation_id=msg.conversation_id,
            )
            if inspect.isawaitable(sent):
                await sent
        return response_text

    async def shutdown(self) -> None:
        """Cancel and await all asyncio tasks owned by this bridge."""
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


__all__ = [
    "AgentCommand",
    "ChannelAgent",
    "GovernedAgentInvoker",
    "classify_query",
    "parse_agent_command",
]


if __name__ == "__main__":
    async def _smoke() -> bool:
        class _Agent:
            async def run(self, content: str) -> str:
                return content

        bridge = ChannelAgent(None, _Agent())
        return await bridge.process_text("hello") == "hello"

    raise SystemExit(0 if asyncio.run(_smoke()) else 1)
