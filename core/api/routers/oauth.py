"""OAuth router — /oauth/integrations."""

import sys
import secrets
import time

__all__ = [
    "oauth_integrations",
    "router",
]


from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/oauth", tags=["oauth"])

_OAUTH_STATE_TTL_SEC = 600
_pending_google_states: dict[str, float] = {}


def _new_google_state() -> str:
    now = time.monotonic()
    expired = [state for state, created in _pending_google_states.items()
               if now - created > _OAUTH_STATE_TTL_SEC]
    for state in expired:
        _pending_google_states.pop(state, None)
    state = secrets.token_urlsafe(32)
    _pending_google_states[state] = now
    return state


def _consume_google_state(state: str) -> bool:
    created = _pending_google_states.pop(state, None)
    return created is not None and time.monotonic() - created <= _OAUTH_STATE_TTL_SEC


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
            "state": _new_google_state(),
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        return {"auth_url": auth_url, "instructions": "Open auth_url in browser, then /oauth/callback/google will receive the code"}
    except Exception as e:
        logger.warning(f"[VECTOR][api][oauth] google-calendar connect failed: {e}")
        return {"error": str(e)}


@router.get("/callback/google")
async def google_calendar_callback(code: str = "", state: str = "", error: str = ""):
    """Exchange Google OAuth code for tokens and store in collections DB."""
    if error:
        return {"error": error}
    if not state or not _consume_google_state(state):
        return {"error": "invalid or expired OAuth state"}
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
        from core.collections.store import CollectionEngine
        _engine = CollectionEngine()
        _record_data = {"token": token_data, "scope": "calendar", "configured_at": __import__("datetime").datetime.utcnow().isoformat()}
        # Try update first (if token already exists), else create
        try:
            existing = _engine.list_records("google_calendar_tokens")
            _items = existing.get("items", []) if isinstance(existing, dict) else existing
            if _items:
                _engine.update_record("google_calendar_tokens", _items[0]["id"], _record_data)
            else:
                _engine.create_record("google_calendar_tokens", _record_data)
        except Exception as _store_err:
            logger.error(f"[VECTOR][oauth] token store failed: {_store_err}")
            return {"error": "Google authorized VECTOR, but token storage failed"}
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
