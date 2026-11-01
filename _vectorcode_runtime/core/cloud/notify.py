"""Owner notification for core/cloud/*.

Thin wrapper over core.notify.send_telegram() -- kept as its own module
because core/memory/db_guardian.py (and possibly other cloud/security-
adjacent call sites) expects this exact import path.
"""
from __future__ import annotations

from core.notify import send_telegram


async def notify_owner(msg: str, priority: int = 0) -> None:
    await send_telegram(msg, priority=priority)


if __name__ == "__main__":
    import asyncio
    asyncio.run(notify_owner("core/cloud/notify.py smoke test"))
    print("OK: core/cloud/notify.py")
