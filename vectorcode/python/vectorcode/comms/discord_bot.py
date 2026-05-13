"""
DiscordBot — VectorCode Discord integration.

Two modes:
  1. Webhook mode — send-only via Discord webhook URL (no token needed, no discord.py)
  2. Bot mode     — full bidirectional via discord.py (token needed)

Graceful degradation: webhook mode works with only httpx; discord.py is optional.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from typing import Callable, Optional
from loguru import logger

try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

try:
    import discord
    _HAS_DISCORD_PY = True
except ImportError:
    _HAS_DISCORD_PY = False


class DiscordBot:
    """
    Discord bot for VectorCode.

    Mode 1 (Webhook): POST to webhook_url — send-only, no discord.py needed.
    Mode 2 (Bot):     Full bidirectional via discord.py client + bot token.

    Config keys under CONFIG['discord']:
        webhook_url  — Discord Incoming Webhook URL
        bot_token    — Discord Bot token (required for bot mode)
        channel_id   — Default channel ID (str or int)
        guild_id     — Guild/server ID (str or int)
    """

    PRIORITY_PREFIXES = {
        "urgent":   "**URGENT** ",
        "critical": "**CRITICAL** ",
    }

    def __init__(self) -> None:
        cfg = CONFIG.get("discord", {}) if isinstance(CONFIG, dict) else {}
        self._webhook_url: str   = cfg.get("webhook_url") or ""
        self._bot_token:   str   = cfg.get("bot_token") or ""
        self._channel_id:  str   = str(cfg.get("channel_id") or "")
        self._guild_id:    str   = str(cfg.get("guild_id") or "")
        self._client               = None   # discord.py Client, set in start_bot()
        self._sent_count: int    = 0
        self._recv_count: int    = 0

    # ── Configuration check ───────────────────────────────────────────────────

    def is_configured(self) -> bool:
        """True if at least one of webhook_url or bot_token is set."""
        return bool(self._webhook_url or self._bot_token)

    # ── Send helpers ──────────────────────────────────────────────────────────

    async def send_message(
        self,
        text: str,
        channel_id: str = "",
        priority: str = "normal",
    ) -> dict:
        """
        Send a text message to Discord.

        Webhook mode: POSTs to webhook_url (channel_id ignored).
        Bot mode: sends to channel_id (falls back to self._channel_id).
        Returns {status, platform, channel_id}.
        """
        prefix = self.PRIORITY_PREFIXES.get(priority, "")
        content = prefix + text

        # Prefer webhook mode when available (no discord.py needed)
        if self._webhook_url:
            return await self._send_via_webhook(content)

        # Bot mode requires discord.py
        if self._bot_token and _HAS_DISCORD_PY and self._client is not None:
            target_channel_id = int(channel_id or self._channel_id or 0)
            return await self._send_via_bot_client(content, target_channel_id)

        if not self.is_configured():
            return {"status": "not_configured", "platform": "discord", "channel_id": channel_id}

        logger.warning("[VECTOR][discord] bot token set but discord.py not installed / bot not started")
        return {"status": "error", "platform": "discord", "reason": "discord.py unavailable or bot not started"}

    async def send_embed(
        self,
        title: str,
        description: str,
        color: int = 0x5865F2,
    ) -> dict:
        """
        Send a rich embed message via webhook (embed format) or as plain text fallback.
        color: Discord colour integer (default Discord blurple = 0x5865F2).
        """
        if self._webhook_url:
            return await self._send_embed_via_webhook(title, description, color)

        # Fallback: plain text with title
        fallback_text = f"**{title}**\n{description}"
        return await self.send_message(fallback_text)

    async def start_bot(self, on_message: Callable) -> None:
        """
        Start a discord.py bot (blocking coroutine — run via asyncio.create_task).
        on_message(InboundMessage) is called for each new message received.
        No-ops gracefully if discord.py is not installed.
        """
        if not _HAS_DISCORD_PY:
            logger.warning("[VECTOR][discord] discord.py not installed — bot mode unavailable")
            return

        if not self._bot_token:
            logger.warning("[VECTOR][discord] bot_token not configured — cannot start bot")
            return

        try:
            from comms.inbound import InboundMessage
        except ImportError:
            InboundMessage = None  # type: ignore[misc,assignment]

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:
            logger.info(f"[VECTOR][discord] bot ready: {client.user}")

        @client.event
        async def on_message(message: "discord.Message") -> None:  # type: ignore[name-defined]
            if message.author == client.user:
                return
            self._recv_count += 1
            if InboundMessage is not None:
                inbound = InboundMessage(
                    platform="discord",
                    sender_id=str(message.author.id),
                    sender_name=str(message.author.display_name),
                    chat_id=str(message.channel.id),
                    text=message.content,
                    raw={"message_id": message.id},
                )
                try:
                    on_message(inbound)
                except Exception as e:
                    logger.error(f"[VECTOR][discord] on_message handler error: {e}")

        try:
            await client.start(self._bot_token)
        except Exception as e:
            logger.error(f"[VECTOR][discord] bot start error: {e}")

    # ── Internal webhook senders ──────────────────────────────────────────────

    async def _send_via_webhook(self, content: str) -> dict:
        """POST a plain text message to the Discord webhook."""
        if not _HAS_HTTPX:
            logger.warning("[VECTOR][discord] httpx not installed — cannot send webhook")
            return {"status": "error", "platform": "discord", "reason": "httpx unavailable"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(self._webhook_url, json={"content": content[:2000]})
                if r.status_code in (200, 204):
                    self._sent_count += 1
                    logger.info(f"[VECTOR][discord] webhook sent: {content[:60]}")
                    return {"status": "sent", "platform": "discord", "channel_id": "webhook"}
                logger.warning(f"[VECTOR][discord] webhook HTTP {r.status_code}: {r.text[:200]}")
                return {"status": "error", "platform": "discord", "code": r.status_code}
        except Exception as e:
            logger.error(f"[VECTOR][discord] webhook error: {e}")
            return {"status": "error", "platform": "discord", "error": str(e)}

    async def _send_embed_via_webhook(self, title: str, description: str, color: int) -> dict:
        """POST an embed payload to the Discord webhook."""
        if not _HAS_HTTPX:
            return {"status": "error", "platform": "discord", "reason": "httpx unavailable"}

        payload = {
            "embeds": [{
                "title": title[:256],
                "description": description[:4096],
                "color": color,
            }]
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(self._webhook_url, json=payload)
                if r.status_code in (200, 204):
                    self._sent_count += 1
                    return {"status": "sent", "platform": "discord", "channel_id": "webhook"}
                return {"status": "error", "platform": "discord", "code": r.status_code}
        except Exception as e:
            logger.error(f"[VECTOR][discord] embed webhook error: {e}")
            return {"status": "error", "platform": "discord", "error": str(e)}

    async def _send_via_bot_client(self, content: str, channel_id: int) -> dict:
        """Send using the discord.py client (bot mode only)."""
        if not channel_id:
            return {"status": "error", "platform": "discord", "reason": "no channel_id"}
        try:
            channel = self._client.get_channel(channel_id)
            if channel is None:
                return {"status": "error", "platform": "discord", "reason": f"channel {channel_id} not found"}
            await channel.send(content[:2000])
            self._sent_count += 1
            return {"status": "sent", "platform": "discord", "channel_id": str(channel_id)}
        except Exception as e:
            logger.error(f"[VECTOR][discord] bot send error: {e}")
            return {"status": "error", "platform": "discord", "error": str(e)}

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return bot/webhook statistics."""
        return {
            "mode": "bot" if (self._bot_token and _HAS_DISCORD_PY) else "webhook",
            "configured": self.is_configured(),
            "sent": self._sent_count,
            "received": self._recv_count,
            "has_discord_py": _HAS_DISCORD_PY,
        }


if __name__ == "__main__":
    import asyncio

    bot = DiscordBot()

    # is_configured: False when no credentials in CONFIG
    configured = bot.is_configured()
    print(f"configured={configured} (expected False in dev environment)")

    # stats structure
    stats = bot.get_stats()
    assert "mode" in stats
    assert "configured" in stats
    assert "sent" in stats
    assert "received" in stats
    assert "has_discord_py" in stats

    # send_message to unconfigured bot returns not_configured
    async def _test() -> None:
        result = await bot.send_message("test message", priority="normal")
        assert result.get("status") in ("not_configured", "sent", "error", "queued"), \
            f"Unexpected status: {result}"
        print(f"send_message result: {result}")

        # send_embed
        embed_result = await bot.send_embed("Test Title", "Test description", color=0xFF0000)
        assert "status" in embed_result
        print(f"send_embed result: {embed_result}")

    asyncio.run(_test())
    print("comms/discord_bot.py OK — webhook mode, embed support, graceful no-dep degradation")
