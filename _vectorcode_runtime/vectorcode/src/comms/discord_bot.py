"""Discord bot adapter — webhook mode (always works) + bot mode (full features)."""

import sys


from loguru import logger

import asyncio
from typing import Callable, Optional

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False
    logger.warning("[VECTOR][discord] httpx not installed — webhook mode unavailable")

try:
    import discord
    from discord import Intents
    _DISCORD_AVAILABLE = True
except ImportError:
    discord = None  # type: ignore[assignment]
    Intents = None  # type: ignore[assignment]
    _DISCORD_AVAILABLE = False

# ---------------------------------------------------------------------------
# Mode A -- Webhook (no discord.py required)
# ---------------------------------------------------------------------------

class DiscordWebhook:
    """Send messages to Discord via a webhook URL.  No bot token required."""

    def __init__(self, webhook_url: str = "") -> None:
        self.webhook_url = webhook_url

    async def send(
        self,
        content: str,
        *,
        username: str = "VectorCode",
        embed: dict | None = None,
    ) -> dict:
        """POST to the Discord webhook.  Returns the parsed response dict."""
        if not self.webhook_url:
            logger.warning("[VECTOR][discord] Webhook URL not set — send skipped")
            return {"success": False, "error": "webhook_url not configured"}
        if not _HTTPX_AVAILABLE:
            logger.error("[VECTOR][discord] httpx not installed")
            return {"success": False, "error": "httpx not installed"}

        payload: dict = {"username": username}
        if content:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
                logger.debug(f"[VECTOR][discord] Webhook POST -> {resp.status_code}")
                # Discord returns 204 No Content on success
                if resp.status_code == 204:
                    return {"success": True}
                return {"success": True, "data": resp.json()}
        except Exception as exc:
            logger.error(f"[VECTOR][discord] Webhook send failed: {exc}")
            return {"success": False, "error": str(exc)}

    async def send_embed(
        self,
        title: str,
        description: str,
        color: int = 0x5865F2,
        fields: list[dict] | None = None,
    ) -> dict:
        """Send a rich embed message.

        *fields* format: [{"name": "...", "value": "...", "inline": False}]
        """
        embed: dict = {
            "title": title,
            "description": description,
            "color": color,
        }
        if fields:
            embed["fields"] = [
                {
                    "name": f.get("name", ""),
                    "value": f.get("value", ""),
                    "inline": f.get("inline", False),
                }
                for f in fields
            ]
        return await self.send("", embed=embed)

    async def send_code(self, code: str, language: str = "") -> dict:
        """Send a fenced code block.  Splits into multiple messages if > 1 900 chars."""
        fence = f"```{language}\n" if language else "```\n"
        close = "\n```"
        max_inner = 1900 - len(fence) - len(close)

        results: list[dict] = []
        # Chunk at newlines where possible
        chunks = self._split_at_newlines(code, max_inner)
        for chunk in chunks:
            message = f"{fence}{chunk}{close}"
            result = await self.send(message)
            results.append(result)
            if not result.get("success"):
                break

        return results[-1] if results else {"success": False, "error": "empty code"}

    @staticmethod
    def _split_at_newlines(text: str, limit: int) -> list[str]:
        """Split *text* into chunks of at most *limit* chars, preferring newline boundaries."""
        if len(text) <= limit:
            return [text]
        chunks: list[str] = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break
            # find last newline within limit
            cut = text.rfind("\n", 0, limit)
            if cut == -1:
                cut = limit
            else:
                cut += 1  # include the newline in this chunk
            chunks.append(text[:cut])
            text = text[cut:]
        return chunks

# ---------------------------------------------------------------------------
# Mode B -- Bot (requires discord.py)
# ---------------------------------------------------------------------------

class DiscordBot:
    """Full Discord bot using discord.py.  Supports message handling and sending."""

    def __init__(self, token: str = "", command_prefix: str = "!vector ") -> None:
        self.token = token
        self.command_prefix = command_prefix
        self._client: Optional["discord.Client"] = None  # type: ignore[name-defined]
        self._on_message_callback: Optional[Callable] = None

    def on_message(self, callback: Callable) -> None:
        """Register an async callback(message_text, channel_id, author_name) -> str | None."""
        self._on_message_callback = callback

    async def start(self) -> None:
        """Start the bot.  Issues a clear warning if discord.py is missing or intents fail."""
        if not _DISCORD_AVAILABLE:
            logger.warning(
                "[VECTOR][discord] discord.py not installed. "
                "Run: pip install discord.py  — bot mode unavailable"
            )
            return
        if not self.token:
            logger.warning("[VECTOR][discord] Bot token not set — start skipped")
            return

        try:
            intents = Intents.default()
            intents.message_content = True
        except Exception as exc:
            logger.warning(
                f"[VECTOR][discord] Failed to configure intents (check discord.py version): {exc}"
            )
            return

        self._client = discord.Client(intents=intents)  # type: ignore[attr-defined]

        @self._client.event  # type: ignore[union-attr]
        async def on_ready() -> None:
            logger.info(
                f"[VECTOR][discord] Bot logged in as {self._client.user}"  # type: ignore[union-attr]
            )

        @self._client.event  # type: ignore[union-attr]
        async def on_message(msg: "discord.Message") -> None:  # type: ignore[name-defined]
            if self._client and msg.author == self._client.user:  # type: ignore[union-attr]
                return
            if self._on_message_callback:
                response = await self._on_message_callback(
                    str(msg.content),
                    msg.channel.id,
                    str(msg.author),
                )
                if response and msg.channel:
                    await self.send(msg.channel.id, response)

        try:
            await self._client.start(self.token)  # type: ignore[union-attr]
        except Exception as exc:
            logger.error(f"[VECTOR][discord] Bot start error: {exc}")

    async def send(self, channel_id: int, content: str) -> None:
        """Send *content* to *channel_id*.  Splits at 2 000 chars when needed."""
        if self._client is None:
            logger.warning("[VECTOR][discord] send called but bot is not running")
            return
        try:
            channel = self._client.get_channel(channel_id)  # type: ignore[union-attr]
            if channel is None:
                logger.warning(f"[VECTOR][discord] Channel {channel_id} not found")
                return
            for chunk in self._split_message(content):
                await channel.send(chunk)
        except Exception as exc:
            logger.error(f"[VECTOR][discord] send error: {exc}")

    async def send_embed(
        self,
        channel_id: int,
        title: str,
        description: str,
        color: int = 0x5865F2,
    ) -> None:
        """Send a rich embed to *channel_id*."""
        if not _DISCORD_AVAILABLE or self._client is None:
            logger.warning("[VECTOR][discord] send_embed skipped — bot not running")
            return
        try:
            channel = self._client.get_channel(channel_id)  # type: ignore[union-attr]
            if channel is None:
                return
            embed = discord.Embed(  # type: ignore[attr-defined]
                title=title, description=description, color=color
            )
            await channel.send(embed=embed)
        except Exception as exc:
            logger.error(f"[VECTOR][discord] send_embed error: {exc}")

    async def stop(self) -> None:
        """Gracefully shut down the bot."""
        if self._client is not None:
            try:
                await self._client.close()  # type: ignore[union-attr]
                logger.info("[VECTOR][discord] Bot stopped")
            except Exception as exc:
                logger.error(f"[VECTOR][discord] stop error: {exc}")
            finally:
                self._client = None

    @staticmethod
    def _split_message(text: str, limit: int = 2000) -> list[str]:
        """Split *text* into chunks of at most *limit* chars, breaking at newlines."""
        if len(text) <= limit:
            return [text]
        chunks: list[str] = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break
            cut = text.rfind("\n", 0, limit)
            if cut == -1:
                cut = limit
            else:
                cut += 1
            chunks.append(text[:cut])
            text = text[cut:]
        return chunks

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_discord_adapter(
    mode: str = "auto",
    token: str = "",
    webhook_url: str = "",
) -> DiscordBot | DiscordWebhook:
    """
    Create and return the appropriate Discord adapter.

    mode="auto"    -> DiscordBot if *token* set, else DiscordWebhook if *webhook_url* set.
                     Falls back to DiscordWebhook with empty URL if neither is set.
    mode="bot"     -> DiscordBot (always)
    mode="webhook" -> DiscordWebhook (always)
    """
    if mode == "bot":
        return DiscordBot(token=token)
    if mode == "webhook":
        return DiscordWebhook(webhook_url=webhook_url)
    # auto
    if token:
        logger.debug("[VECTOR][discord] auto mode -> DiscordBot")
        return DiscordBot(token=token)
    if webhook_url:
        logger.debug("[VECTOR][discord] auto mode -> DiscordWebhook")
        return DiscordWebhook(webhook_url=webhook_url)
    logger.warning("[VECTOR][discord] auto mode: no token or webhook — returning DiscordWebhook (unconfigured)")
    return DiscordWebhook()

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("[VECTOR][discord] Running smoke test…")

    # Test 1: DiscordWebhook with empty URL — no crash on init
    wh = DiscordWebhook()
    assert isinstance(wh, DiscordWebhook)
    assert wh.webhook_url == ""
    logger.info("[VECTOR][discord] DiscordWebhook(empty URL) init ✅")

    # Test 2: DiscordBot with empty token — no crash on init
    bot = DiscordBot()
    assert isinstance(bot, DiscordWebhook) is False
    assert bot.token == ""
    logger.info("[VECTOR][discord] DiscordBot(empty token) init ✅")

    # Test 3: webhook send with empty URL returns success=False without crashing
    async def _test_send() -> None:
        result = await wh.send("Hello")
        assert result["success"] is False, f"Expected success=False, got {result}"
        assert "error" in result
        logger.info(f"[VECTOR][discord] wh.send(empty url) -> {result} ✅")

    asyncio.run(_test_send())

    # Test 4: _split_message correctness
    long_text = "A" * 4500
    chunks = DiscordBot._split_message(long_text, limit=2000)
    assert all(len(c) <= 2000 for c in chunks)
    assert "".join(chunks) == long_text
    logger.info(f"[VECTOR][discord] _split_message chunks={len(chunks)} ✅")

    # Test 5: send_code splitting
    async def _test_code() -> None:
        big_code = "\n".join([f"line {i}" for i in range(200)])
        # Just verify it doesn't crash with empty URL
        result = await wh.send_code(big_code, "python")
        assert "success" in result
        logger.info(f"[VECTOR][discord] send_code(200 lines) -> success={result['success']} ✅")

    asyncio.run(_test_code())

    # Test 6: factory auto mode
    adapter_wh = create_discord_adapter(mode="auto", webhook_url="http://fake")
    assert isinstance(adapter_wh, DiscordWebhook)
    adapter_bot = create_discord_adapter(mode="auto", token="fake_token")
    assert isinstance(adapter_bot, DiscordBot)
    adapter_explicit_wh = create_discord_adapter(mode="webhook")
    assert isinstance(adapter_explicit_wh, DiscordWebhook)
    adapter_explicit_bot = create_discord_adapter(mode="bot")
    assert isinstance(adapter_explicit_bot, DiscordBot)
    logger.info("[VECTOR][discord] create_discord_adapter factory ✅")

    logger.info("[VECTOR][discord] All smoke tests passed")
    sys.stdout.buffer.write(b"[OK] discord_bot.py OK\n")
