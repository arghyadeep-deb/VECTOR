"""Standalone owner-notification helper (Pushover).

Extracted so call sites outside PermissionGateway (which owns the
approval-flow notify methods) can send a real owner notification without
importing gateway internals. Same wire format as
PermissionGateway._notify().
"""
from __future__ import annotations

import httpx
from loguru import logger

from core.config import CONFIG


async def pushover(message: str, priority: int = 0) -> None:
    token = CONFIG["api_keys"].get("pushover_token", "")
    user = CONFIG["api_keys"].get("pushover_user", "")
    if not token or not user:
        logger.info(f"[VECTOR][notify] (no Pushover configured) {message}")
        return
    try:
        payload: dict = {"token": token, "user": user, "message": message, "priority": priority}
        if priority == 2:
            payload.setdefault("retry", 60)
            payload.setdefault("expire", 300)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.pushover.net/1/messages.json", data=payload, timeout=5
            )
            if resp.status_code != 200:
                logger.warning(f"[VECTOR][notify] Pushover rejected: {resp.status_code} {resp.text[:300]}")
    except Exception as e:
        logger.warning(f"[VECTOR][notify] Pushover failed: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(pushover("core/notify.py smoke test"))
    print("OK: core/notify.py")
