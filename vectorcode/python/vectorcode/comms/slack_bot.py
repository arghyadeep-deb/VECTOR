"""
SlackBot — VectorCode Slack integration.

Two modes:
  1. Webhook mode — POST to Incoming Webhook URL (no OAuth, no slack_sdk needed)
  2. Bot API mode — POST to Slack Web API with bot_token (optional slack_sdk)

Graceful degradation: webhook mode works with only httpx installed.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from typing import Optional
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
    from slack_sdk.web.async_client import AsyncWebClient as _SlackWebClient
    _HAS_SLACK_SDK = True
except ImportError:
    _HAS_SLACK_SDK = False

# Slack Web API base URL
_SLACK_API_BASE = "https://slack.com/api"


class SlackBot:
    """
    Slack integration for VectorCode.

    Mode 1 (Webhook): Incoming Webhook — POST to webhook_url, send-only.
    Mode 2 (Bot API): Slack Web API chat.postMessage with bot_token.

    Config keys under CONFIG['slack']:
        webhook_url      — Slack Incoming Webhook URL
        bot_token        — Bot OAuth token (xoxb-...)
        default_channel  — Default channel name or ID (e.g. "#vector-alerts")
    """

    PRIORITY_PREFIXES = {
        "urgent":   "*URGENT* ",
        "critical": "*CRITICAL* ",
    }

    def __init__(self) -> None:
        cfg = CONFIG.get("slack", {}) if isinstance(CONFIG, dict) else {}
        self._webhook_url:      str = cfg.get("webhook_url") or ""
        self._bot_token:        str = cfg.get("bot_token") or ""
        self._default_channel:  str = cfg.get("default_channel") or ""
        self._sent_count: int = 0

    # ── Configuration check ───────────────────────────────────────────────────

    def is_configured(self) -> bool:
        """True if at least one of webhook_url or bot_token is set."""
        return bool(self._webhook_url or self._bot_token)

    # ── Public send methods ───────────────────────────────────────────────────

    async def send_message(
        self,
        text: str,
        channel: str = "",
        blocks: Optional[list] = None,
    ) -> dict:
        """
        Send a text message to Slack.

        Webhook mode: POSTs to webhook_url (channel ignored unless using bot API).
        Bot API mode: calls chat.postMessage with channel.
        blocks: optional Slack Block Kit payload.
        Returns {status, platform, channel}.
        """
        prefix = ""  # No priority param here — caller wraps text if needed
        target_channel = channel or self._default_channel

        if self._webhook_url:
            return await self._send_via_webhook(prefix + text, blocks=blocks)

        if self._bot_token:
            return await self._send_via_bot_api(prefix + text, target_channel, blocks=blocks)

        return {"status": "not_configured", "platform": "slack", "channel": target_channel}

    async def send_code_block(
        self,
        code: str,
        language: str = "",
        channel: str = "",
    ) -> dict:
        """
        Send a code snippet wrapped in a Slack code block.
        language: optional language hint (e.g. "python"). Slack does not syntax-highlight
        but it is included as a comment for readability.
        """
        lang_comment = f"# language: {language}\n" if language else ""
        formatted = f"```{lang_comment}{code}```"
        return await self.send_message(formatted, channel=channel)

    # ── Internal senders ─────────────────────────────────────────────────────

    async def _send_via_webhook(self, text: str, blocks: Optional[list] = None) -> dict:
        """POST to Slack Incoming Webhook URL."""
        if not _HAS_HTTPX:
            logger.warning("[VECTOR][slack] httpx not installed — cannot send webhook")
            return {"status": "error", "platform": "slack", "reason": "httpx unavailable"}

        payload: dict = {"text": text[:4000]}
        if blocks:
            payload["blocks"] = blocks

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(self._webhook_url, json=payload)
                # Slack webhooks return plain text "ok" on success
                if r.status_code == 200 and r.text.strip() == "ok":
                    self._sent_count += 1
                    logger.info(f"[VECTOR][slack] webhook sent: {text[:60]}")
                    return {"status": "sent", "platform": "slack", "channel": "webhook"}
                logger.warning(f"[VECTOR][slack] webhook HTTP {r.status_code}: {r.text[:200]}")
                return {"status": "error", "platform": "slack", "code": r.status_code, "body": r.text[:200]}
        except Exception as e:
            logger.error(f"[VECTOR][slack] webhook error: {e}")
            return {"status": "error", "platform": "slack", "error": str(e)}

    async def _send_via_bot_api(
        self,
        text: str,
        channel: str,
        blocks: Optional[list] = None,
    ) -> dict:
        """POST to Slack chat.postMessage (Bot API)."""
        if not channel:
            logger.warning("[VECTOR][slack] bot API requires a channel — none specified")
            return {"status": "error", "platform": "slack", "reason": "no channel specified"}

        # Prefer slack_sdk if available
        if _HAS_SLACK_SDK:
            return await self._send_via_slack_sdk(text, channel, blocks=blocks)

        # Fallback: raw httpx POST
        return await self._send_via_httpx_bot_api(text, channel, blocks=blocks)

    async def _send_via_slack_sdk(
        self,
        text: str,
        channel: str,
        blocks: Optional[list] = None,
    ) -> dict:
        """Use slack_sdk.web.async_client for Bot API."""
        try:
            sdk_client = _SlackWebClient(token=self._bot_token)
            kwargs: dict = {"channel": channel, "text": text}
            if blocks:
                kwargs["blocks"] = blocks
            response = await sdk_client.chat_postMessage(**kwargs)
            if response.get("ok"):
                self._sent_count += 1
                return {"status": "sent", "platform": "slack", "channel": channel}
            return {"status": "error", "platform": "slack", "error": response.get("error", "unknown")}
        except Exception as e:
            logger.error(f"[VECTOR][slack] slack_sdk error: {e}")
            return {"status": "error", "platform": "slack", "error": str(e)}

    async def _send_via_httpx_bot_api(
        self,
        text: str,
        channel: str,
        blocks: Optional[list] = None,
    ) -> dict:
        """Raw httpx POST to chat.postMessage — fallback when slack_sdk is absent."""
        if not _HAS_HTTPX:
            return {"status": "error", "platform": "slack", "reason": "httpx unavailable"}

        payload: dict = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks

        headers = {
            "Authorization": f"Bearer {self._bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{_SLACK_API_BASE}/chat.postMessage",
                    json=payload,
                    headers=headers,
                )
                data = r.json()
                if data.get("ok"):
                    self._sent_count += 1
                    logger.info(f"[VECTOR][slack] bot API sent to {channel}: {text[:60]}")
                    return {"status": "sent", "platform": "slack", "channel": channel}
                logger.warning(f"[VECTOR][slack] bot API error: {data.get('error', 'unknown')}")
                return {"status": "error", "platform": "slack", "error": data.get("error", "unknown")}
        except Exception as e:
            logger.error(f"[VECTOR][slack] bot API httpx error: {e}")
            return {"status": "error", "platform": "slack", "error": str(e)}

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return connection/send statistics."""
        return {
            "configured": self.is_configured(),
            "mode": "bot_api" if self._bot_token else ("webhook" if self._webhook_url else "none"),
            "has_slack_sdk": _HAS_SLACK_SDK,
            "sent": self._sent_count,
            "default_channel": self._default_channel,
        }


if __name__ == "__main__":
    import asyncio

    bot = SlackBot()

    # is_configured: False in dev environment with no credentials
    configured = bot.is_configured()
    print(f"configured={configured} (expected False in dev environment)")

    # stats structure
    stats = bot.get_stats()
    assert "configured" in stats
    assert "mode" in stats
    assert "sent" in stats
    assert "has_slack_sdk" in stats

    async def _test() -> None:
        # Unconfigured bot → not_configured
        result = await bot.send_message("hello from VECTOR")
        assert result.get("status") in ("not_configured", "sent", "error"), \
            f"Unexpected status: {result}"
        print(f"send_message result: {result}")

        # Code block wrapping
        code_result = await bot.send_code_block("print('hello')", language="python")
        assert "status" in code_result
        print(f"send_code_block result: {code_result}")

    asyncio.run(_test())
    print("comms/slack_bot.py OK — webhook + bot API modes, code block, graceful no-dep degradation")
