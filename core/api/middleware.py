"""Custom middleware for V.E.C.T.O.R. API.

Middleware execution order (FastAPI applies in reverse order):
1. error_handling_middleware (innermost)
2. rate_limiting_middleware
3. timing_middleware
4. logging_middleware
5. auth_middleware (outermost)
"""

import sys

__all__ = [
    "auth_middleware",
    "csrf_middleware",
    "error_handling_middleware",
    "generate_csrf_token",
    "logging_middleware",
    "rate_limiting_middleware",
    "security_headers_middleware",
    "timing_middleware",
    "validate_csrf_token",
]

import os
import hmac
import time
import datetime
from collections import defaultdict
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import uuid
import threading


# ── Configuration ───────────────────────────────────────

# FIX #7: When no API key is set, enforce localhost-only access instead of open access
_REQUIRE_LOCALHOST_WHEN_NO_KEY: bool = True

_RATE_LIMIT_WINDOW: int = 60  # seconds
_RATE_LIMIT_MAX: dict[str, int] = {
    "default": 100,
    "/command": 20,
    "/ws/command": 20,
    "/council": 10,
    "/memory/recent": 50,
}

_RATE_LIMIT_WINDOW_SEC: int = 60
_RATE_LIMIT_MAX_DEFAULT: int = 100

# Thread-safe rate limiting storage
# NOTE (#6): This is per-process. For multi-worker deployments, use Redis-backed
# rate limiting (e.g. slowapi with Redis backend). Acceptable for single-user local system.
_rate_limit_lock = threading.Lock()
_rate_limit_data: dict[str, list[float]] = defaultdict(list)

# Public paths (no auth required)
_PUBLIC_PATHS = {"/", "/status", "/health", "/docs", "/openapi.json", "/redoc",
                 # Wipes this origin's cached pages, service workers and cookies in the visitor's own browser (see
                 # core/api/app.py clear_site_data). Public on purpose: it is how a browser stuck on a removed page
                 # recovers without first being able to load that page, and it exposes no VECTOR data.
                 "/clear-site-data",
                 "/csrf-token",  # CSRF token endpoint is public
                 "/growth/signup",  # public beta-signup form (gated by BetaSignup, not auth/CSRF)
                 # WebAuthn login must be reachable WITHOUT already holding
                 # VECTOR_API_KEY — that's the whole point, it's how you
                 # authenticate without the static key. Registration
                 # (/auth/webauthn/register/*) is deliberately NOT here — it
                 # stays behind the normal auth gate below (localhost-only,
                 # enforced again inside the handler itself) so a remote
                 # caller can't enroll their own fingerprint as trusted.
                 # /auth/webauthn/status is read-only (no secrets) and public
                 # so the HUD login page can show "no passkey enrolled yet"
                 # before any auth exists.
                 "/auth/webauthn/login/options", "/auth/webauthn/login/verify",
                 "/auth/webauthn/status",
                 # Minimal public passkey sign-in shell (core/api/app.py's
                 # login_page). Carries no VECTOR data or district output —
                 # just a button that calls the three public webauthn paths
                 # above. /hud/ itself stays gated; see that route's comment.
                 "/login",
                 # JWT login is public — it's how you GET a token in the first
                 # place. /auth/jwt/refresh, /revoke, /logout, /sessions, /me
                 # stay behind auth (they REQUIRE a valid token).
                 "/auth/jwt/login"}

# Allowed origins — localhost only (no external origins)
_ALLOWED_ORIGINS = {
    "https://localhost:8000",
    "https://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}

# CSRF tokens are kept purely in-memory (no disk persistence).
# Storing tokens on disk leaks them to any process that can read the filesystem.
# Tokens are short-lived (1h TTL) and regenerated cheaply on each request.
_csrf_tokens: dict[str, float] = {}
_csrf_lock = threading.Lock()
_CSRF_TOKEN_TTL = 3600  # 1 hour

# Security headers
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # microphone/camera=(self) — NOT (): an empty allowlist blocks the page
    # from ever requesting them, even from itself, even with the browser's own
    # permission prompt granted. That silently broke the HUD's own core
    # features — voice input (speech.js/voice_duplex.js getUserMedia) and the
    # webcam widget could NEVER work in any real browser (2026-07-17 browser
    # dogfood: "Permissions policy violation: microphone/camera is not allowed
    # in this document" on every attempt). (self) still blocks third-party
    # iframes from getting mic/camera — only this document's own JS can ask.
    "Permissions-Policy": "geolocation=(), microphone=(self), camera=(self)",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

# ── Rate Limiting ──────────────────────────────────────


def _is_rate_limited(path: str, client_ip: str) -> bool:
    """Check if a client is rate limited for a given path."""
    window = _RATE_LIMIT_WINDOW
    max_requests = _RATE_LIMIT_MAX.get(path, _RATE_LIMIT_MAX_DEFAULT)
    
    now = time.time()
    cutoff = now - window
    
    key = f"{path}:{client_ip}"
    
    with _rate_limit_lock:
        # Clean old entries
        _rate_limit_data[key] = [t for t in _rate_limit_data[key] if t > cutoff]
        
        if len(_rate_limit_data[key]) >= max_requests:
            return True
        
        _rate_limit_data[key].append(now)
        return False


async def rate_limiting_middleware(request: Request, call_next):
    """Rate limit requests per client per endpoint."""
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    
    # Skip rate limiting for public paths and health checks
    if path in _PUBLIC_PATHS or path.startswith("/_next"):
        return await call_next(request)
    
    if _is_rate_limited(path, client_ip):
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(_RATE_LIMIT_WINDOW)},
            content={
                "error": "Rate limit exceeded",
                "detail": f"Too many requests. Retry after {_RATE_LIMIT_WINDOW}s",
                "retry_after": _RATE_LIMIT_WINDOW,
            },
        )
    
    response = await call_next(request)
    
    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = str(
        _RATE_LIMIT_MAX.get(path, _RATE_LIMIT_MAX_DEFAULT)
    )
    response.headers["X-RateLimit-Remaining"] = str(max(
        0,
        _RATE_LIMIT_MAX.get(path, _RATE_LIMIT_MAX_DEFAULT)
        - len(_rate_limit_data.get(f"{path}:{client_ip}", []))
    ))
    
    return response


# ── Authentication ─────────────────────────────────────


def _verify_webauthn_jwt(token: str) -> bool:
    """Accept a passkey-issued session JWT (core/api/routers/webauthn_auth.py's
    /auth/webauthn/login/verify) as an alternative credential to the static
    VECTOR_API_KEY. Lazy import — most requests authenticate via the static
    key and never need this path; keeps this middleware's hot path free of
    the collections-engine import for those requests."""
    if token.count(".") != 2:
        return False  # not JWT-shaped, skip the (slightly) more expensive check
    try:
        from core.collections.auth import JWTManager
        JWTManager().verify(token, expected_type="webauthn_session")
        return True
    except Exception:
        return False


def _verify_jwt_access_token(token: str) -> bool:
    """Accept a JWT access token issued by /auth/jwt/login or /auth/jwt/refresh.
    Checks signature, expiry, type, and revocation blacklist.
    Returns True if the token is valid and not revoked."""
    if token.count(".") != 2:
        return False  # not JWT-shaped
    try:
        from core.collections.auth import JWTManager, AuthError
        from core.security.token_blacklist import get_blacklist

        jwt_mgr = JWTManager()
        claims = jwt_mgr.verify(token, expected_type="access")

        # V1 STAGE 6 CLOSURE: owner API JWTs and collection-scoped JWTs
        # (core/collections/auth.py's JWTManager.issue_pair) share the
        # identical type="access" claim with nothing else previously
        # distinguishing them -- a collection JWT would otherwise
        # authenticate as full owner-equivalent global API access here.
        # Require the owner-only scope explicitly; expected_type="access"
        # alone is exactly the collision being closed. jti is now
        # mandatory (was optional, which let a collection token skip
        # revocation checking entirely).
        jti = claims.get("jti", "")
        if (
            claims.get("token_scope") != "owner_api"
            or claims.get("sub") != "owner"
            or "collection" in claims
            or not jti
        ):
            return False

        # Check revocation
        blacklist = get_blacklist()
        if blacklist.is_globally_revoked():
            return False
        if blacklist.is_revoked(jti):
            return False

        return True
    except Exception:
        return False


async def auth_middleware(request: Request, call_next):
    """Require Bearer token for all non-public endpoints.
    FIX #7: When no API key is set, only allow localhost connections (not any process).
    Uses get_secret() so keyring is checked as fallback (not just env)."""
    from core.security.secrets_manager import get_secret
    api_key = get_secret("VECTOR_API_KEY")
    api_key_enabled = bool(api_key)

    # Skip auth for public paths
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    
    # Skip auth for health check and static assets
    if request.url.path.startswith("/_next") or request.url.path == "/health":
        return await call_next(request)
    
    # When API key not configured: enforce localhost-only access
    if not api_key_enabled:
        if _REQUIRE_LOCALHOST_WHEN_NO_KEY:
            client_ip = request.client.host if request.client else ""
            if client_ip not in ("127.0.0.1", "::1", "localhost"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Remote access requires VECTOR_API_KEY to be configured."},
                )
        return await call_next(request)
    
    # Credential can arrive three ways, in priority order:
    #   1. Authorization: Bearer <key>  — API/WS clients and the HUD's own fetch()
    #   2. ?key=<key> query param        — a browser NAVIGATING to /hud/?key=... ;
    #      it cannot set an Authorization header, so this is the only way the very
    #      first HUD page load can authenticate (e.g. the phone opening the bookmark)
    #   3. vector_key cookie             — set on the first ?key= load so that the
    #      HUD's RELATIVE asset requests (config.js, the prod bundle, CSS) — which
    #      carry neither a Bearer header nor the query param — authenticate too.
    auth = request.headers.get("Authorization", "")
    provided = ""
    via_query = False
    if auth.startswith("Bearer "):
        provided = auth[7:]
    elif request.query_params.get("key"):
        provided = request.query_params.get("key", "")
        via_query = True
    elif request.cookies.get("vector_key"):
        provided = request.cookies.get("vector_key", "")

    # Constant-time comparison — avoids leaking the key via response timing.
    # A request can also authenticate with a passkey-issued session JWT
    # (see /auth/webauthn/login/verify) or a JWT access token (see
    # /auth/jwt/login) instead of the long-lived static key.
    key_matches = bool(provided) and hmac.compare_digest(provided, api_key)
    jwt_valid = bool(provided) and (
        _verify_jwt_access_token(provided) or _verify_webauthn_jwt(provided)
    )
    if not key_matches and not jwt_valid:
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
            content={"detail": "Unauthorized. Valid API key or passkey session required."},
        )

    response = await call_next(request)
    # First HUD load authenticated via the URL key → drop an HttpOnly cookie so the
    # page's relative assets + same-origin API/WS calls authenticate without the key
    # needing to appear in every asset URL. 30-day life; HttpOnly keeps JS from
    # reading it (the HUD uses the query-param key for its own Bearer/WS auth).
    if via_query:
        response.set_cookie(
            "vector_key", provided,
            max_age=60 * 60 * 24 * 30,
            httponly=True, samesite="lax", path="/",
        )
    return response


# ── Logging ────────────────────────────────────────────


async def logging_middleware(request: Request, call_next):
    """Log all incoming requests with timing."""
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()
    
    logger.info(
        f"[VECTOR][api][{request_id}] {request.method} {request.url.path}"
    )
    
    response = await call_next(request)
    
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    log_level = (
        "ERROR"
        if response.status_code >= 500
        else         "WARNING" if response.status_code >= 400 else "INFO"
    )
    logger.log(
        log_level,
        f"[VECTOR][api][{request_id}] {request.method} {request.url.path} "
            f"-> {response.status_code} ({elapsed_ms}ms)",
    )
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
    
    return response


# ── Timing ─────────────────────────────────────────────


async def timing_middleware(request: Request, call_next):
    """Add timing header to all responses."""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = str(int((time.perf_counter() - start) * 1000))
    return response


# ── Error Handling ─────────────────────────────────────


async def error_handling_middleware(request: Request, call_next):
    """Catch and format unhandled exceptions. Only expose details to localhost."""
    try:
        return await call_next(request)
    except HTTPException:
        raise  # Re-raise FastAPI HTTP exceptions
    except Exception as e:
        logger.error(f"[VECTOR][api] Unhandled exception: {e}")
        # FIX #16: Only expose error details to localhost clients, never remote
        client_ip = request.client.host if request.client else ""
        is_local = client_ip in ("127.0.0.1", "::1", "localhost")
        show_detail = is_local and os.environ.get("VECTOR_DEBUG")
        return JSONResponse(
            status_code=500,
            headers={
                "X-Error-Type": type(e).__name__,
                "X-Error-Timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            content={
                "error": "Internal server error",
                "detail": str(e) if show_detail else "An error occurred",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )


# ── Security Headers ───────────────────────────────────


async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value

    # Strict CSP — only allow same-origin, no inline scripts from external sources
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "  # unsafe-inline needed for React
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' wss://localhost:8000 ws://localhost:8000; "
        "img-src 'self' data:; "
        # audio.js._speakKokoro() plays VECTOR's real voice via
        # URL.createObjectURL(wavBlob) + new Audio(blobUrl) — that's a `blob:`
        # media source. No media-src directive meant it fell back to
        # default-src 'self', which does NOT cover blob: — every Kokoro reply
        # was silently blocked by CSP and the HUD fell back to the robotic
        # browser voice the owner explicitly banned (2026-07-17 browser
        # dogfood: 'Loading media from blob:... violates CSP directive').
        "media-src 'self' blob:; "
        # Local sidecar widgets (comfyui:8188, librechat:3080, open-webui:8080)
        # embed their UI in an iframe. Without an explicit frame-src these fell
        # back to default-src 'self' and were ALWAYS blocked — those three
        # widgets could never work, even with the sidecar running (2026-07-17
        # browser dogfood). Loopback only: never the public internet.
        "frame-src 'self' http://127.0.0.1:* http://localhost:*; "
        "frame-ancestors 'none';"
    )

    from core.config import CONFIG
    response.headers["X-System-Version"] = CONFIG.get("version", "unknown")

    return response


def generate_csrf_token() -> str:
    """Generate a new CSRF token and store it in-memory."""
    token = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char hex
    with _csrf_lock:
        # Clean expired tokens
        now = time.time()
        expired = [k for k, v in _csrf_tokens.items() if now - v > _CSRF_TOKEN_TTL]
        for k in expired:
            del _csrf_tokens[k]
        _csrf_tokens[token] = now
    return token


def validate_csrf_token(token: str) -> bool:
    """Validate a CSRF token. Returns True if valid."""
    if not token:
        return False
    with _csrf_lock:
        issued_at = _csrf_tokens.get(token)
        if issued_at is None:
            return False
        if time.time() - issued_at > _CSRF_TOKEN_TTL:
            del _csrf_tokens[token]
            return False
    return True


async def csrf_middleware(request: Request, call_next):
    """
    Validate CSRF token on state-changing requests (POST/PUT/DELETE/PATCH).
    GET requests are safe and don't need CSRF protection.
    The dashboard fetches a token from /csrf-token and includes it as X-CSRF-Token header.
    """
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Public endpoints (e.g. the beta-signup form) have no session/cookie to
        # protect and define their own anti-abuse — exempt from CSRF.
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        # Skip CSRF for API key authenticated requests (non-browser clients)
        from core.security.secrets_manager import get_secret
        if get_secret("VECTOR_API_KEY") and request.headers.get("Authorization", "").startswith("Bearer "):
            return await call_next(request)

        # Skip CSRF for WebSocket upgrades
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        csrf_token = request.headers.get("X-CSRF-Token", "")
        if not validate_csrf_token(csrf_token):
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid or missing CSRF token", "detail": "Include X-CSRF-Token header"},
            )

    return await call_next(request)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ middleware.py OK")
