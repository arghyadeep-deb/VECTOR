"""VECTOR Twitch Channel Adapter — live streaming chat."""
from __future__ import annotations
import asyncio
from loguru import logger


def _irc_value(value: str) -> str:
    """Reject values that could inject additional IRC protocol commands."""
    if "\r" in value or "\n" in value:
        raise ValueError("IRC values must not contain CR or LF")
    return value

class TwitchAdapter:
    """
    Twitch chat adapter for VECTOR via IRC over WebSocket.
    Requires: pip install twitchio
    Env: TWITCH_TOKEN, TWITCH_CHANNEL, TWITCH_BOT_NAME
    """
    def __init__(self):
        import os
        self.token = os.environ.get("TWITCH_TOKEN","")
        self.channel = os.environ.get("TWITCH_CHANNEL","")
        self.bot_name = os.environ.get("TWITCH_BOT_NAME","vectorbot")

    async def send_message(self, message: str) -> bool:
        try:
            import websockets, json
            token = _irc_value(self.token)
            bot_name = _irc_value(self.bot_name)
            channel = _irc_value(self.channel)
            message = _irc_value(message)
            async with websockets.connect("wss://irc-ws.chat.twitch.tv:443") as ws:
                await ws.send(f"PASS {token}")
                await ws.send(f"NICK {bot_name}")
                await ws.send(f"JOIN #{channel}")
                await ws.send(f"PRIVMSG #{channel} :{message}")
                logger.info("[VECTOR][twitch] sent: {}", message[:50])
                return True
        except Exception as e:
            logger.error("[VECTOR][twitch] send failed: {}", e)
            return False

    async def listen(self, callback, timeout_secs: float = 60.0):
        """Listen for chat messages and call callback(author, message) for each."""
        try:
            import websockets
            token = _irc_value(self.token)
            bot_name = _irc_value(self.bot_name)
            channel = _irc_value(self.channel)
            async with websockets.connect("wss://irc-ws.chat.twitch.tv:443") as ws:
                await ws.send(f"PASS {token}")
                await ws.send(f"NICK {bot_name}")
                await ws.send(f"JOIN #{channel}")
                deadline = asyncio.get_event_loop().time() + timeout_secs
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        line = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        if "PRIVMSG" in line:
                            parts = line.split(":", 2)
                            if len(parts) >= 3:
                                author = parts[1].split("!")[0]
                                msg = parts[2].strip()
                                await callback(author, msg)
                    except asyncio.TimeoutError as _e:
                        logger.debug("[VECTOR] suppressed exception: {}", _e)
        except Exception as e:
            logger.error("[VECTOR][twitch] listen failed: {}", e)
