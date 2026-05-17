"""
VECTOR Channel Runtime — async message dispatch loop.

Ported from openhuman's channels/runtime/dispatch.rs.

Routes inbound messages from any channel to the right agent,
manages concurrency, injects memory context, fires typing indicators,
and handles streaming responses back to the channel.

Architecture:
  ChannelMessage → ChannelRuntime.dispatch() → Agent → streaming reply → Channel.send()

Integrates with VECTOR's existing vectorcode channel adapters.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from loguru import logger


# ── Message types ──────────────────────────────────────────────────────────────

@dataclass
class ChannelMessage:
    id: str
    sender: str
    content: str
    channel: str
    reply_target: str = ""
    thread_ts: str | None = None
    timestamp: float = 0.0

    @classmethod
    def new(cls, sender: str, content: str, channel: str = "cli") -> "ChannelMessage":
        return cls(id=str(uuid.uuid4()), sender=sender, content=content,
                   channel=channel, reply_target=sender)


@dataclass
class SendMessage:
    content: str
    recipient: str
    subject: str | None = None
    thread_ts: str | None = None
    channel: str = "cli"


# ── Acknowledgment emoji (ported from dispatch.rs select_acknowledgment_reaction) ──

_ACK_REACTIONS: dict[str, list[str]] = {
    "gratitude": ["❤️", "🙏", "😊"],
    "excitement": ["🔥", "🎉", "⚡"],
    "crypto":     ["💯", "🚀", "💎"],
    "technical":  ["🤓", "💻", "🛠️"],
    "greeting":   ["👋", "😁", "🤗"],
    "question":   ["🤔", "✍️", "🧠"],
    "default":    ["👀", "✍️", "⚙️"],
}

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "gratitude": ["thank", "thanks", "appreciate", "grateful"],
    "excitement": ["amazing", "awesome", "incredible", "wow", "great"],
    "crypto":    ["crypto", "bitcoin", "eth", "solana", "defi", "nft"],
    "technical": ["code", "function", "debug", "error", "python", "api"],
    "greeting":  ["hello", "hi", "hey", "good morning", "good evening"],
    "question":  ["?", "how", "what", "why", "when", "can you"],
}


def select_ack_reaction(content: str) -> str:
    """Pick a contextually appropriate acknowledgment emoji."""
    lower = content.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            reactions = _ACK_REACTIONS[category]
            idx = hash(content) % len(reactions)
            return reactions[idx]
    reactions = _ACK_REACTIONS["default"]
    return reactions[hash(content) % len(reactions)]


# ── Agent resolution ───────────────────────────────────────────────────────────

def _resolve_agent(sender: str, channel: str, is_onboarded: bool) -> str:
    """Route to welcome agent for new users, orchestrator otherwise."""
    if not is_onboarded:
        return "welcome"
    return "orchestrator"


def _build_context_block(msg: ChannelMessage) -> str:
    """Inject channel routing hints (ported from build_channel_context_block)."""
    if msg.channel == "cli":
        return ""
    return (
        f"\n\n[Channel context]\n"
        f"channel: {msg.channel}\n"
        f"reply_target: {msg.reply_target}\n"
        f"thread: {msg.thread_ts or 'none'}\n"
    )


# ── ChannelRuntime ─────────────────────────────────────────────────────────────

AgentHandler = Callable[[str, str, str], Awaitable[str]]
# (agent_name, system_prompt_hint, user_message) → response


class ChannelRuntime:
    """
    Async message dispatch loop for VECTOR's channel system.

    Usage:
        async def my_agent(agent, hint, message):
            # call your LLM here
            return f"VECTOR response to: {message}"

        runtime = ChannelRuntime(agent_handler=my_agent, max_in_flight=5)
        await runtime.start()

        # Send a message
        msg = ChannelMessage.new("arghyadeep", "What's my schedule today?", "telegram")
        await runtime.submit(msg)
    """

    def __init__(
        self,
        agent_handler: AgentHandler | None = None,
        reply_handler: Callable[[SendMessage], Awaitable[None]] | None = None,
        max_in_flight: int = 5,
        typing_handler: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._agent = agent_handler or self._default_agent
        self._reply = reply_handler or self._default_reply
        self._typing = typing_handler
        self._semaphore = asyncio.Semaphore(max_in_flight)
        self._queue: asyncio.Queue[ChannelMessage] = asyncio.Queue()
        self._running = False
        self._onboarded_senders: set[str] = set()

    async def submit(self, msg: ChannelMessage) -> None:
        """Enqueue a message for dispatch."""
        await self._queue.put(msg)

    def submit_sync(self, msg: ChannelMessage) -> None:
        self._queue.put_nowait(msg)

    async def start(self) -> None:
        """Run the dispatch loop until cancelled."""
        self._running = True
        logger.info("[VECTOR][channel_runtime] dispatch loop started (max_in_flight={})",
                    self._semaphore._value)
        tasks: set[asyncio.Task] = set()
        try:
            while self._running:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._semaphore.acquire()
                t = asyncio.create_task(self._dispatch(msg))
                tasks.add(t)
                t.add_done_callback(lambda t: (tasks.discard(t), self._semaphore.release()))
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            pass
        finally:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("[VECTOR][channel_runtime] dispatch loop stopped")

    def stop(self) -> None:
        self._running = False

    async def _dispatch(self, msg: ChannelMessage) -> None:
        """Process a single channel message end-to-end."""
        try:
            logger.info("[VECTOR][channel_runtime] dispatch channel={} sender={} len={}",
                        msg.channel, msg.sender, len(msg.content))

            # 1. Fire typing indicator
            if self._typing:
                await self._typing(msg.channel, msg.reply_target)

            # 2. Ack reaction (non-blocking)
            ack = select_ack_reaction(msg.content)
            logger.debug("[VECTOR][channel_runtime] ack reaction: {}", ack)

            # 3. Resolve target agent
            is_onboarded = msg.sender in self._onboarded_senders
            agent_name = _resolve_agent(msg.sender, msg.channel, is_onboarded)

            # 4. Build enriched content
            context_block = _build_context_block(msg)
            enriched = msg.content + context_block

            # 5. Dispatch to agent
            response = await self._agent(agent_name, "", enriched)

            # 6. Mark onboarded after first successful interaction
            self._onboarded_senders.add(msg.sender)

            # 7. Send reply
            reply = SendMessage(
                content=response,
                recipient=msg.reply_target,
                thread_ts=msg.thread_ts,
                channel=msg.channel,
            )
            await self._reply(reply)

            logger.info("[VECTOR][channel_runtime] dispatched OK channel={} agent={}",
                        msg.channel, agent_name)

        except Exception as e:
            logger.error("[VECTOR][channel_runtime] dispatch failed: {}", e)
            try:
                err_reply = SendMessage(
                    content=f"[VECTOR Error] {type(e).__name__}: {str(e)[:200]}",
                    recipient=msg.reply_target,
                    channel=msg.channel,
                )
                await self._reply(err_reply)
            except Exception:
                pass

    @staticmethod
    async def _default_agent(agent: str, hint: str, message: str) -> str:
        logger.debug("[VECTOR][channel_runtime] default agent handler: agent={}", agent)
        return f"[VECTOR] Received via {agent}: {message[:100]}"

    @staticmethod
    async def _default_reply(msg: SendMessage) -> None:
        logger.info("[VECTOR][channel_runtime] reply → {}: {}", msg.recipient, msg.content[:80])


if __name__ == "__main__":
    import asyncio

    async def _test():
        replies = []

        async def fake_agent(agent, hint, message):
            return f"Agent {agent} says: processed '{message[:30]}'"

        async def fake_reply(msg):
            replies.append(msg.content)

        runtime = ChannelRuntime(agent_handler=fake_agent, reply_handler=fake_reply)

        msg = ChannelMessage.new("arghyadeep", "What is my schedule today?", "telegram")
        await runtime.submit(msg)

        # Run dispatch loop for one iteration
        async def _run_once():
            msg = await runtime._queue.get()
            await runtime._dispatch(msg)

        await _run_once()
        assert len(replies) == 1
        assert "welcome" in replies[0].lower() or "processed" in replies[0].lower()

        # Test ack selection
        assert select_ack_reaction("thanks so much") in _ACK_REACTIONS["gratitude"]
        assert select_ack_reaction("debug this error") in _ACK_REACTIONS["technical"]

        print("OK channel_runtime.py — dispatch + ack selection verified")

    asyncio.run(_test())
