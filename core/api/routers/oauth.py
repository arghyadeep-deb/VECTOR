"""OAuth router — /oauth/integrations."""

import sys

__all__ = [
    "oauth_integrations",
    "router",
]


from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get("/connect/google-calendar")
async def google_calendar_connect():
    """Return the Google OAuth authorization URL. Open in browser to begin auth flow."""
    try:
        from core.config import CONFIG
        client_id = CONFIG.get("oauth_google_client_id", "")
        redirect_uri = CONFIG.get("oauth_google_redirect_uri", "http://localhost:8000/oauth/callback/google")
        if not client_id:
            return {"error": "OAUTH_GOOGLE_CLIENT_ID not configured in .env"}
        import urllib.parse
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events",
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        return {"auth_url": auth_url, "instructions": "Open auth_url in browser, then /oauth/callback/google will receive the code"}
    except Exception as e:
        logger.warning(f"[VECTOR][api][oauth] google-calendar connect failed: {e}")
        return {"error": str(e)}


@router.get("/callback/google")
async def google_calendar_callback(code: str = "", error: str = ""):
    """Exchange Google OAuth code for tokens and store in collections DB."""
    if error:
        return {"error": error}
    if not code:
        return {"error": "no code provided"}
    try:
        import httpx
        from core.config import CONFIG
        client_id = CONFIG.get("oauth_google_client_id", "")
        client_secret = CONFIG.get("oauth_google_client_secret", "")
        redirect_uri = CONFIG.get("oauth_google_redirect_uri", "http://localhost:8000/oauth/callback/google")
        if not client_id or not client_secret:
            return {"error": "OAUTH_GOOGLE_CLIENT_ID / OAUTH_GOOGLE_CLIENT_SECRET not configured"}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        # Store tokens in collections DB under google_calendar_tokens
        from core.collections.store import CollectionStore
        store = CollectionStore("google_calendar_tokens")
        store.upsert_record(
            {"token": token_data, "scope": "calendar", "configured_at": __import__("datetime").datetime.utcnow().isoformat()},
            record_id="primary",
        )
        logger.info("[VECTOR][oauth] Google Calendar tokens stored in collections DB")
        return {"status": "ok", "message": "Google Calendar connected. VECTOR can now read/write your calendar."}
    except Exception as e:
        logger.warning(f"[VECTOR][api][oauth] google callback failed: {e}")
        return {"error": str(e)}


@router.get("/integrations")
async def oauth_integrations():
    """Get OAuth integration registry stats."""
    try:
        from core.engine.oauth.registry import OAuthRegistry
        reg = OAuthRegistry()
        categories = {}
        for cat in reg.categories():
            categories[cat] = len(reg.list_by_category(cat))
        return {
            "total_integrations": reg.count(),
            "categories": categories,
            "available": len(reg.available()),
        }
    except Exception as e:
        logger.warning(f"[VECTOR][api][oauth] integrations failed: {e}")
        return {"total_integrations": 0, "categories": {}, "available": 0}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ oauth.py OK")
