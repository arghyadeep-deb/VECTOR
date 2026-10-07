"""
VECTOR OAuth Proxy Server — self-hosted, no dependency on tinyhumans.ai.

Runs as a FastAPI server on http://localhost:7788/oauth/
Handles the full OAuth2 authorization code flow for all 20+ providers.

Endpoints:
  GET  /oauth/authorize/{slug}   — redirect to provider login
  GET  /oauth/callback           — receive auth code, exchange for token
  GET  /oauth/status/{slug}      — check if integration is connected
  POST /oauth/revoke/{slug}      — revoke and delete stored token
  GET  /oauth/list               — list all connected integrations
  POST /oauth/api_key/{slug}     — store an API key (non-OAuth providers)

Usage:
  # Start the OAuth server (can run alongside VECTOR core)
  python -m core.engine.oauth.server

  # Or import and mount on existing FastAPI app
  from core.engine.oauth.server import oauth_router
  app.include_router(oauth_router, prefix="/oauth")
"""
from __future__ import annotations

__all__ = [
    "create_app",
    "run_server",
]


import base64
import hashlib
import html
import os
import secrets
from urllib.parse import urlencode, urlparse


from loguru import logger

try:
    import httpx
    from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    import uvicorn
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

from core.config import CONFIG
from core.engine.oauth.flows import OAuthFlowManager, OAuthToken, _expires_at_from_seconds
from core.engine.oauth.providers import get_provider, PROVIDERS, configured_providers
from core.engine.oauth.refresh_scheduler import start_scheduler as _start_oauth_scheduler

_REDIRECT_BASE = CONFIG.get("oauth_redirect_base", "http://localhost:7788")
_CALLBACK_PATH = "/oauth/callback"
_CALLBACK_URL = f"{_REDIRECT_BASE}{_CALLBACK_PATH}"

_flow_manager = OAuthFlowManager()
_state_store: dict[str, str] = {}            # state → slug (in-memory, short-lived)
_pkce_store: dict[str, str] = {}             # state → code_verifier
_oauth1_secrets: dict[str, str] = {}         # oauth_token → oauth_token_secret (OAuth1 step 1→3)


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _success_html(name: str) -> str:
    name = html.escape(name, quote=True)
    return f"""<!DOCTYPE html>
<html><head><title>VECTOR — Connected</title>
<style>
  body {{ background:#020A14; color:#00D4FF; font-family:monospace;
         display:flex; align-items:center; justify-content:center; height:100vh; }}
  .box {{ border:1px solid #00D4FF; padding:40px; text-align:center; }}
  h2 {{ color:#30FF6A; }} p {{ color:#5A8FAA; }}
</style></head><body><div class="box">
  <h2>✓ {name} Connected</h2>
  <p>VECTOR has been granted access.</p>
  <p style="margin-top:20px;font-size:0.8em">You may close this window.</p>
</div></body></html>"""


def _error_html(msg: str) -> str:
    msg = html.escape(msg, quote=True)
    return f"""<!DOCTYPE html>
<html><head><title>VECTOR — OAuth Error</title>
<style>body{{background:#020A14;color:#FF3B30;font-family:monospace;
             display:flex;align-items:center;justify-content:center;height:100vh;}}
.box{{border:1px solid #FF3B30;padding:40px;text-align:center;}}
</style></head><body><div class="box">
  <h2>OAuth Error</h2><p>{msg}</p>
</div></body></html>"""


if _FASTAPI_AVAILABLE:
    oauth_router = APIRouter(tags=["oauth"])

    @oauth_router.get("/authorize/{slug}")
    async def authorize(slug: str, redirect_after: str = Query(default="")):
        """Redirect user to provider OAuth login page."""
        provider = get_provider(slug)
        if not provider:
            raise HTTPException(404, f"Unknown integration: {slug}")

        state = secrets.token_urlsafe(16)
        _state_store[state] = slug

        params: dict = {
            "client_id": provider.client_id or "CONFIGURE_IN_ENV",
            "redirect_uri": _CALLBACK_URL,
            "response_type": "code",
            "state": state,
            **provider.extra_params,
        }

        if provider.scopes:
            params["scope"] = " ".join(provider.scopes)

        if provider.pkce:
            verifier, challenge = _generate_pkce()
            _pkce_store[state] = verifier
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"

        url = f"{provider.auth_url}?{urlencode(params)}"
        logger.info("[VECTOR][oauth] authorizing {} → {}", slug, url[:80])
        return RedirectResponse(url)

    @oauth_router.get("/callback")
    async def callback(
        request: Request,
        code: str = Query(default=""),
        state: str = Query(default=""),
        error: str = Query(default=""),
        error_description: str = Query(default=""),
    ):
        """Handle OAuth callback — exchange code for token."""
        if error:
            msg = error_description or error
            logger.error("[VECTOR][oauth] callback error: {}", msg)
            return HTMLResponse(_error_html(msg))

        slug = _state_store.pop(state, None)
        if not slug:
            return HTMLResponse(_error_html("Invalid or expired state parameter."))

        provider = get_provider(slug)
        if not provider:
            return HTMLResponse(_error_html(f"Unknown provider: {slug}"))

        # Exchange code for token
        payload: dict = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _CALLBACK_URL,
            "client_id": provider.client_id,
        }

        if not provider.pkce:
            payload["client_secret"] = provider.client_secret
        else:
            verifier = _pkce_store.pop(state, "")
            if verifier:
                payload["code_verifier"] = verifier

        headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(provider.token_url, data=payload, headers=headers)

            if resp.status_code != 200:
                logger.error("[VECTOR][oauth] token exchange failed {}: {}", resp.status_code, resp.text[:200])
                return HTMLResponse(_error_html(f"Token exchange failed: {resp.status_code}"))

            data = resp.json()
            token = OAuthToken(
                slug=slug,
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token", ""),
                expires_at=_expires_at_from_seconds(data.get("expires_in")),
                scope=data.get("scope", " ".join(provider.scopes)),
                extra={k: v for k, v in data.items()
                       if k not in ("access_token", "refresh_token", "expires_in", "scope")},
            )
            _flow_manager.store_token(slug, token)
            logger.info("[VECTOR][oauth] {} connected successfully", slug)
            return HTMLResponse(_success_html(provider.name))

        except Exception as e:
            logger.error("[VECTOR][oauth] token exchange error: {}", e)
            return HTMLResponse(_error_html(str(e)))

    @oauth_router.get("/status/{slug}")
    async def status(slug: str):
        """Check if an integration is connected."""
        token = _flow_manager.get_token(slug)
        provider = get_provider(slug)
        return JSONResponse({
            "slug": slug,
            "name": provider.name if provider else slug,
            "connected": token is not None,
            "has_refresh": bool(token and token.refresh_token) if token else False,
            "scope": token.scope if token else "",
        })

    @oauth_router.post("/revoke/{slug}")
    async def revoke(slug: str):
        """Revoke and delete stored token."""
        _flow_manager.revoke_token(slug)
        return JSONResponse({"slug": slug, "revoked": True})

    @oauth_router.get("/list")
    async def list_connected():
        """List all connected integrations."""
        connected = _flow_manager.list_connected()
        result = []
        for slug in connected:
            provider = get_provider(slug)
            result.append({
                "slug": slug,
                "name": provider.name if provider else slug,
                "category": provider.category if hasattr(provider, "category") else "unknown",
            })
        return JSONResponse({"connected": result, "count": len(result)})

    @oauth_router.post("/api_key/{slug}")
    async def store_api_key(slug: str, request: Request):
        """Store an API key for non-OAuth integrations."""
        body = await request.json()
        api_key = body.get("api_key", "")
        if not api_key:
            raise HTTPException(400, "api_key is required")
        _flow_manager.store_api_key(slug, api_key)
        return JSONResponse({"slug": slug, "stored": True})

    @oauth_router.get("/providers")
    async def list_providers():
        """List all available providers and their configured status."""
        return JSONResponse({
            "providers": [
                {
                    "slug": p.slug,
                    "name": p.name,
                    "configured": p.load_from_env().is_configured(),
                    "pkce": p.pkce,
                    "scopes": p.scopes,
                }
                for p in PROVIDERS.values()
            ],
            "total": len(PROVIDERS),
            "configured": len(configured_providers()),
        })

    @oauth_router.get("/oauth1/authorize/{slug}")
    async def oauth1_authorize(slug: str, callback_url: str = Query(default="")):
        """OAuth 1.0a step 1 — get a request token and redirect to provider."""
        provider = get_provider(slug)
        if not provider or provider.auth_mode != "oauth1":
            raise HTTPException(400, f"{slug} is not an OAuth 1.0a provider")
        cb = callback_url or f"{_REDIRECT_BASE}/oauth/oauth1/callback/{slug}"
        try:
            result = _flow_manager.get_oauth1_request_token(slug, callback_url=cb)
            _oauth1_secrets[result["oauth_token"]] = result["oauth_token_secret"]
            return RedirectResponse(result["auth_url"])
        except ImportError as e:
            raise HTTPException(501, str(e))
        except Exception as e:
            logger.error("[VECTOR][oauth1] request token failed for {}: {}", slug, e)
            return HTMLResponse(_error_html(str(e)))

    @oauth_router.get("/oauth1/callback/{slug}")
    async def oauth1_callback(
        slug: str,
        oauth_token: str = Query(default=""),
        oauth_verifier: str = Query(default=""),
        denied: str = Query(default=""),
    ):
        """OAuth 1.0a step 3 — exchange verifier for access token."""
        if denied:
            return HTMLResponse(_error_html("OAuth 1.0a authorization was denied."))
        oauth_token_secret = _oauth1_secrets.pop(oauth_token, "")
        if not oauth_token_secret:
            return HTMLResponse(_error_html("Unknown or expired OAuth1 request token."))
        provider = get_provider(slug)
        if not provider:
            return HTMLResponse(_error_html(f"Unknown provider: {slug}"))
        try:
            _flow_manager.complete_oauth1(
                slug=slug,
                oauth_token=oauth_token,
                oauth_token_secret=oauth_token_secret,
                oauth_verifier=oauth_verifier,
            )
            return HTMLResponse(_success_html(provider.name))
        except ImportError as e:
            raise HTTPException(501, str(e))
        except Exception as e:
            logger.error("[VECTOR][oauth1] callback failed for {}: {}", slug, e)
            return HTMLResponse(_error_html(str(e)))

    @oauth_router.get("/refresh/{slug}")
    async def refresh_token(slug: str):
        """Refresh an expired access token using stored refresh_token."""
        token = _flow_manager.get_token(slug)
        if not token or not token.refresh_token:
            raise HTTPException(400, f"No refresh token for {slug}")

        provider = get_provider(slug)
        if not provider:
            raise HTTPException(404, f"Unknown provider: {slug}")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    provider.token_url,
                    data=payload,
                    headers={"Accept": "application/json",
                             "Content-Type": "application/x-www-form-urlencoded"},
                )
            resp.raise_for_status()
            data = resp.json()
            access_token = data.get("access_token")
            if not isinstance(access_token, str) or not access_token.strip():
                raise ValueError("refresh response did not contain a valid access_token")
            new_token = OAuthToken(
                slug=slug,
                access_token=access_token,
                refresh_token=data.get("refresh_token", token.refresh_token),
                expires_at=_expires_at_from_seconds(data.get("expires_in")),
                scope=data.get("scope", token.scope),
            )
            _flow_manager.store_token(slug, new_token)
            logger.info("[VECTOR][oauth] refreshed token for {}", slug)
            return JSONResponse({"slug": slug, "refreshed": True})
        except Exception as e:
            logger.error("[VECTOR][oauth] refresh failed for {}: {}", slug, e)
            raise HTTPException(500, str(e))


def create_app() -> "FastAPI":
    """Create standalone FastAPI app with OAuth router mounted."""
    if not _FASTAPI_AVAILABLE:
        raise ImportError("Run: pip install fastapi uvicorn httpx")
    app = FastAPI(title="VECTOR OAuth Server", version="1.0.0")
    app.include_router(oauth_router, prefix="/oauth")

    @app.on_event("startup")
    async def _on_startup() -> None:
        _start_oauth_scheduler(interval_minutes=30)

    @app.on_event("shutdown")
    async def _on_shutdown() -> None:
        from core.engine.oauth.refresh_scheduler import stop_scheduler
        stop_scheduler()

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "VECTOR OAuth Server"}

    return app


def run_server(host: str = "127.0.0.1", port: int = 7788) -> None:
    """Start the OAuth server standalone."""
    if not _FASTAPI_AVAILABLE:
        raise ImportError("Run: pip install fastapi uvicorn httpx")
    logger.info("[VECTOR][oauth] server starting on {}:{}", host, port)
    logger.info("[VECTOR][oauth] callback URL: {}", _CALLBACK_URL)
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    # Verify imports and basic structure
    assert len(PROVIDERS) >= 20
    assert _CALLBACK_URL.endswith("/oauth/callback")
    if _FASTAPI_AVAILABLE:
        app = create_app()
        assert app.title == "VECTOR OAuth Server"
        routes = [r.path for r in app.routes]
        assert "/oauth/authorize/{slug}" in routes
        assert "/oauth/callback" in routes
        print(f"OK oauth/server.py — {len(PROVIDERS)} providers, {len(routes)} routes")
    else:
        print("OK oauth/server.py — FastAPI not installed (pip install fastapi uvicorn httpx)")
