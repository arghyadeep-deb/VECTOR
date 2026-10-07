"""Email router — /email/recent."""

import sys

__all__ = [
    "email_recent",
    "router",
]

from fastapi import APIRouter
from loguru import logger

from core.api.schemas import EmailRecentResponse

router = APIRouter(prefix="/email", tags=["email"])

@router.get("/recent", response_model=EmailRecentResponse)
async def email_recent():
    try:
        from core.email.schema import get_connection
        with get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM emails").fetchone()["c"]
            unread = conn.execute("SELECT COUNT(*) as c FROM emails WHERE read=0").fetchone()["c"]
            rows = conn.execute(
                "SELECT id, subject, sender, date, read FROM emails ORDER BY date DESC LIMIT 10"
            ).fetchall()
            recent = [dict(r) for r in rows]
        return EmailRecentResponse(total=total, unread=unread, recent=recent)
    except Exception as e:
        logger.warning(f"[VECTOR][api][email] recent failed: {e}")
        return EmailRecentResponse(total=0, unread=0, recent=[])

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ email.py OK")
