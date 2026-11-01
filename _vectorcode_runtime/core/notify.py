"""Standalone owner-notification helper (Telegram).

Extracted so call sites outside PermissionGateway (which owns the
approval-flow notify methods) can send a real owner notification without
importing gateway internals. Same wire format as
PermissionGateway._notify().

Replaces Pushover (2026-10-30, owner decision — Pushover is a paid
service). Telegram has no native priority levels, so priority maps to a
text prefix instead; it also has no Pushover-style "emergency" repeat/
retry-until-acknowledged delivery, so priority=2 is a one-shot alert, not
a repeated page. `url`/`url_title` map to an inline keyboard URL button —
tapping it opens the link exactly like Pushover's clickable notification
did, no new infrastructure (webhook, polling) required.
"""
from __future__ import annotations

import json

import httpx
from loguru import logger

from core.config import CONFIG

_PRIORITY_PREFIX = {2: "\U0001F534 ", 1: "\U0001F7E1 "}  # red/yellow circle


async def send_telegram(message: str, priority: int = 0, url: str = "", url_title: str = "") -> bool:
    """Returns True if the message was actually sent, False otherwise
    (never raises — same fail-silent-but-logged contract pushover() had)."""
    token = CONFIG["api_keys"].get("telegram_bot_token", "")
    chat_id = CONFIG["api_keys"].get("telegram_chat_id", "")
    if not token or not chat_id:
        logger.info(f"[VECTOR][notify] (no Telegram configured) {message}")
        return False
    try:
        text = _PRIORITY_PREFIX.get(priority, "") + message
        payload: dict = {"chat_id": chat_id, "text": text}
        if url:
            payload["reply_markup"] = json.dumps({
                "inline_keyboard": [[{"text": url_title or "Open", "url": url}]]
            })
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage", data=payload, timeout=5
            )
            if resp.status_code != 200:
                logger.warning(f"[VECTOR][notify] Telegram rejected: {resp.status_code} {resp.text[:300]}")
                return False
            return True
    except Exception as e:
        logger.warning(f"[VECTOR][notify] Telegram failed: {e}")
        return False


if __name__ == "__main__":
    import asyncio
    asyncio.run(send_telegram("core/notify.py smoke test"))
    print("OK: core/notify.py")
