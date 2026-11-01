"""Telegram network utilities — MTProto helpers, proxy, and connection management."""

from typing import Optional

from loguru import logger

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

TELEGRAM_API = "https://api.telegram.org"

async def get_bot_info(token: str) -> Optional[dict]:
    """Get bot information from Telegram API."""
    if not _HTTPX: return None
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{TELEGRAM_API}/bot{token}/getMe")
        return r.json().get("result") if r.status_code == 200 else None

async def set_webhook(token: str, url: str) -> bool:
    """Set a webhook URL for the Telegram bot."""
    if not _HTTPX: return False
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{TELEGRAM_API}/bot{token}/setWebhook", json={"url": url})
        return r.status_code == 200
